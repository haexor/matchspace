#!/usr/bin/env python3
"""Eigenes Spielertracking aus dem Video, ohne Veo-Daten.

Eingang sind die Personenboxen je Bild und Linse (tools/veo_detect.py) mit Trikotfarbe (tools/veo_colors.py)
und die Kamerakalibrierung. Verfolgt wird am Boden in Metern, beide Linsen zusammen:

  1. Fußpunkt jeder Box auf den Rasen rechnen; nur Personen auf dem Platz (bis 2 m daneben). Wer im
     Überlappungsbereich in beiden Linsen erscheint, zählt einmal.
  2. Je Spur eine Vorhersage aus Lage und Tempo (Kalman-Filter). In Blickrichtung ist der Fußpunkt viel
     ungenauer als quer dazu (ein Pixel sind dort rund 0,3 m); das Filter rechnet damit.
  3. Je Bild Erkennungen und Spuren einander zuordnen (kleinster Gesamtabstand, gemessen in der
     Unsicherheit der Vorhersage); eine andere Trikotfarbe kostet viel. Spuren ohne Erkennung laufen bis
     MAX_COAST weiter, dann enden sie. Neue Spuren gelten erst nach einigen Treffern.
  4. Danach Stücke verbinden, die zusammengehören (Ende des einen, Anfang des anderen: gleiche Farbe,
     erreichbar mit höchstens 7 m/s), damit ein verdeckter Spieler seine Spur behält.

Rückennummern kennt das Tracking nicht; die Spuren heißen nach Mannschaft und laufender Nummer.

Aufruf (zum Prüfen; tools/veo_scene.py nutzt track()):
    .venv/bin/python tools/track_players.py DETEKTIONEN.json KAMERA.json [VEO_ORDNER VEO_ALIGN.json START_S]
Mit Veo-Angaben wird nur verglichen: Abdeckung der Veo-Spieler und Vertauschungen.
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

sys.path.insert(0, str(Path(__file__).parent))
import veo_camera  # noqa: E402

LENSES = ("left", "right")
MARGIN = 2.0          # m neben dem Platz, bis zu dem Personen verfolgt werden
INSIDE = 0.7          # Anteil einer Box, der in einer größeren liegt, ab dem sie nicht zählt
SAME_PERSON = 1.3     # m: Erkennungen beider Linsen näher als das (gleiche oder unbekannte Farbe) sind dieselbe Person
SIGMA_ACROSS, SIGMA_DEPTH = 0.12, 0.35   # m: Messunsicherheit quer zur Blickrichtung und in Blickrichtung
ACCEL = 6.0           # m/s²: Unsicherheit der Bewegung (Antritt, Abstoppen)
GATE = 3.5            # Mahalanobis-Abstand, bis zu dem eine Erkennung zur Spur passen kann
COLOUR_COST = 4.0     # Zusatzkosten für eine andere Trikotfarbe
CONFIRM = 5           # Treffer, ab denen eine Spur gilt; sie müssen in den ersten CONFIRM_WITHIN Bildern liegen
CONFIRM_WITHIN = 8
DUPLICATE = 0.6       # m: zwei Spuren, die so dicht über DUPLICATE_S laufen, folgen derselben Person
DUPLICATE_S = 0.5
MAX_COAST = 1.0       # s ohne Erkennung, bis eine Spur endet
STITCH_GAP = 3.0      # s: so lange Lücken zwischen zwei Stücken werden noch verbunden
STITCH_SPEED = 5.0    # m/s: so schnell dürfte der Spieler die Lücke im Mittel überbrücken
MIN_TRACK = 1.0       # s: kürzere Spuren werden verworfen


def detections(det, cam):
    """Je Bild ein Feld (k, 9): Boden x, y, Farbe, Linse, x1, y1, x2, y2, Nummer der Box in der Linse."""
    L, W = cam["pitch"]["length"], cam["pitch"]["width"]
    out = []
    for fr in det["frames"]:
        rows = []
        for li, lens in enumerate(LENSES):
            b = np.array(fr[lens], float).reshape(-1, 6)
            if not len(b):
                continue
            g, _ = veo_camera.to_ground(cam, lens, np.column_stack([(b[:, 0] + b[:, 2]) / 2, b[:, 3]]))
            for j in range(len(b)):
                if np.isnan(g[j, 0]) or abs(g[j, 0]) > L / 2 + MARGIN or abs(g[j, 1]) > W / 2 + MARGIN:
                    continue
                rows.append([g[j, 0], g[j, 1], b[j, 5], li, *b[j, :4], j])
        rows = np.array(rows).reshape(-1, 9)
        # Box in der Box (ein Körperteil oder ein zweiter Treffer derselben Person): nur die große zählt
        inner = np.zeros(len(rows), bool)
        for a in range(len(rows)):
            for c in range(len(rows)):
                if a == c or rows[a, 3] != rows[c, 3]:
                    continue
                ax1, ay1, ax2, ay2 = rows[a, 4:8]
                cx1, cy1, cx2, cy2 = rows[c, 4:8]
                inter = max(0, min(ax2, cx2) - max(ax1, cx1)) * max(0, min(ay2, cy2) - max(ay1, cy1))
                area_a, area_c = (ax2 - ax1) * (ay2 - ay1), (cx2 - cx1) * (cy2 - cy1)
                if area_a < area_c and inter > INSIDE * area_a:
                    inner[a] = True
        rows = rows[~inner]
        # dieselbe Person in beiden Linsen: die größere Box behalten
        keep = np.ones(len(rows), bool)
        for a in range(len(rows)):
            for c in range(a + 1, len(rows)):
                same_colour = rows[a, 2] == rows[c, 2] or rows[a, 2] < 0 or rows[c, 2] < 0
                if keep[a] and keep[c] and rows[a, 3] != rows[c, 3] and same_colour \
                        and np.hypot(*(rows[a, :2] - rows[c, :2])) < SAME_PERSON:
                    small = a if (rows[a, 7] - rows[a, 5]) < (rows[c, 7] - rows[c, 5]) else c
                    keep[small] = False
        out.append(rows[keep])
    return out


class Track:
    def __init__(self, z, colour, frame, R):
        self.x = np.array([z[0], z[1], 0.0, 0.0])
        self.P = np.diag([R[0, 0], R[1, 1], 4.0, 4.0])
        self.colours = {colour: 1}
        self.hits, self.last, self.first = 1, frame, frame
        self.items = {frame: None}

    def colour(self):
        known = {c: k for c, k in self.colours.items() if c >= 0}
        return max(known, key=known.get) if known else -1


def measurement_noise(cam, z):
    """Kovarianz (2, 2) des Fußpunkts: in Blickrichtung ungenauer als quer dazu."""
    view = z - np.asarray(cam["position"][:2])
    view = view / max(np.linalg.norm(view), 1e-6)
    across = np.array([-view[1], view[0]])
    return SIGMA_DEPTH ** 2 * np.outer(view, view) + SIGMA_ACROSS ** 2 * np.outer(across, across)


def track(det, cam):
    """Spuren aus den Erkennungen. Rückgabe: Liste von {"colour", "frames": {bild: Zeile aus detections()}}."""
    fps = det["fps"]
    dt = 1.0 / fps
    F = np.eye(4)
    F[0, 2] = F[1, 3] = dt
    G = np.array([[dt * dt / 2, 0], [0, dt * dt / 2], [dt, 0], [0, dt]])
    Q = G @ G.T * ACCEL ** 2
    H = np.eye(2, 4)
    dets = detections(det, cam)
    live, done = [], []
    for fi, rows in enumerate(dets):
        for t in live:   # vorhersagen
            t.x = F @ t.x
            t.P = F @ t.P @ F.T + Q
        cost = np.full((len(live), len(rows)), 1e6)
        for i, t in enumerate(live):
            S_base = H @ t.P @ H.T
            for j, r in enumerate(rows):
                S = S_base + measurement_noise(cam, r[:2])
                d = r[:2] - t.x[:2]
                m = float(np.sqrt(d @ np.linalg.solve(S, d)))
                if m > GATE:
                    continue
                c = t.colour()
                cost[i, j] = m + (COLOUR_COST if c >= 0 and r[2] >= 0 and r[2] != c else 0.0)
        used = set()
        if len(live) and len(rows):
            ri, ci = linear_sum_assignment(cost)
            for i, j in zip(ri, ci):
                if cost[i, j] >= 1e5:
                    continue
                t, r = live[i], rows[j]
                R = measurement_noise(cam, r[:2])
                S = H @ t.P @ H.T + R
                K = t.P @ H.T @ np.linalg.inv(S)
                t.x = t.x + K @ (r[:2] - t.x[:2])
                t.P = (np.eye(4) - K @ H) @ t.P
                t.hits += 1
                t.last = fi
                t.items[fi] = r
                t.colours[int(r[2])] = t.colours.get(int(r[2]), 0) + 1
                used.add(j)
        for j, r in enumerate(rows):
            if j not in used:
                t = Track(r[:2], int(r[2]), fi, measurement_noise(cam, r[:2]))
                t.items[fi] = r
                live.append(t)
        still = []
        for t in live:
            tentative = t.hits < CONFIRM
            if tentative and fi - t.first >= CONFIRM_WITHIN:
                continue                       # nicht bestätigt: verwerfen
            if fi - t.last > (2 if tentative else MAX_COAST * fps):
                if not tentative:
                    done.append(t)
                continue
            still.append(t)
        live = still
        # doppelte Spuren derselben Person: die jüngere geht in der älteren auf
        for t in live:
            t.near = getattr(t, "near", {})
        drop = set()
        for a in range(len(live)):
            for b in range(a + 1, len(live)):
                ta, tb = live[a], live[b]
                if ta.hits < CONFIRM or tb.hits < CONFIRM or id(ta) in drop or id(tb) in drop:
                    continue
                if np.hypot(*(ta.x[:2] - tb.x[:2])) < DUPLICATE and (ta.colour() == tb.colour() or min(ta.colour(), tb.colour()) < 0):
                    key = id(tb)
                    ta.near[key] = ta.near.get(key, 0) + 1
                    if ta.near[key] >= DUPLICATE_S * fps:
                        old, young = (ta, tb) if ta.first <= tb.first else (tb, ta)
                        for f, r in young.items.items():
                            if r is not None and old.items.get(f) is None:
                                old.items[f] = r
                        old.hits += young.hits
                        drop.add(id(young))
                else:
                    ta.near.pop(id(tb), None)
        live = [t for t in live if id(t) not in drop]
    done += live
    pieces = [t for t in done if t.hits >= CONFIRM]
    pieces = stitch(pieces, fps)
    return [{"colour": p["colour"], "frames": p["frames"]} for p in pieces if (max(p["frames"]) - min(p["frames"])) / fps >= MIN_TRACK]


def stitch(tracks, fps):
    """Verbindet Stücke derselben Person über Lücken (gleiche Farbe, erreichbar), immer das beste Paar zuerst."""
    pieces = [{"colour": t.colour(), "frames": {f: r for f, r in t.items.items() if r is not None}} for t in tracks]
    pieces = [p for p in pieces if p["frames"]]
    while True:
        best = None
        for a, p in enumerate(pieces):
            fa = max(p["frames"])
            end = p["frames"][fa][:2]
            for b, q in enumerate(pieces):
                if a == b or q["colour"] != p["colour"] or p["colour"] < 0:
                    continue
                fb = min(q["frames"])
                gap = (fb - fa) / fps
                if not 0 < gap <= STITCH_GAP:
                    continue
                dist = float(np.hypot(*(q["frames"][fb][:2] - end)))
                if dist > STITCH_SPEED * gap + 1.0:
                    continue
                score = dist / (STITCH_SPEED * gap + 1.0) + gap / STITCH_GAP
                if best is None or score < best[0]:
                    best = (score, a, b)
        if best is None:
            return pieces
        _, a, b = best
        pieces[a]["frames"].update(pieces[b]["frames"])
        del pieces[b]


def track_hues(video, result, samples=24):
    """Mittlerer Farbton des Oberkörpers je Spur (OpenCV-Farbton, Rot um 0 herum vorzeichenbehaftet), aus bis zu
    samples Bildern je Spur. Trennt zum Beispiel rote Trikots von orangen Leibchen."""
    import cv2
    want = {}
    for k, tr in enumerate(result):
        fs = sorted(tr["frames"])
        for f in fs[::max(1, len(fs) // samples)][:samples]:
            want.setdefault(f, []).append((k, tr["frames"][f]))
    hues = [[] for _ in result]
    cap = cv2.VideoCapture(str(video))
    half = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) // 2
    f = 0
    while want:
        ok, image = cap.read()
        if not ok:
            break
        for k, r in want.pop(f, []):
            li = int(r[3])
            x1, y1, x2, y2 = r[4:8]
            w, h = x2 - x1, y2 - y1
            crop = image[li * half:(li + 1) * half][int(y1 + 0.18 * h):int(y1 + 0.5 * h) + 1, int(x1 + 0.25 * w):int(x2 - 0.25 * w) + 1]
            if crop.size == 0:
                continue
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3)
            vivid = hsv[(hsv[:, 1] > 110) & (hsv[:, 2] > 70)][:, 0].astype(float)
            if len(vivid) >= 5:
                hues[k].append(float(np.median(np.where(vivid > 90, vivid - 180, vivid))))
        f += 1
    return [float(np.median(h)) if h else np.nan for h in hues]


def split_bibs(result, hues, fps, apart=3.5, clear=0.6):
    """Je Farbklasse: Zerfallen die Spuren im Farbton in zwei deutlich getrennte Gruppen (beste Teilung nach Otsu,
    gewichtet mit den gemessenen Bildern; Mittelwerte mehr als apart auseinander und die Teilung erklärt mehr als
    clear der Streuung), ist die Gruppe mit weniger gemessenen Bildern keine Mannschaft (Leibchen der
    Auswechselspieler). Rückgabe: Maske „gehört dazu“."""
    keep = np.ones(len(result), bool)
    for colour in {t["colour"] for t in result if t["colour"] >= 0}:
        idx = [k for k, t in enumerate(result) if t["colour"] == colour and not np.isnan(hues[k])]
        if len(idx) < 4:
            continue
        h = np.array([hues[k] for k in idx])
        w = np.array([len(result[k]["frames"]) for k in idx], float)
        inlier = np.abs(h - np.median(h)) < 12          # einzelne Fehlfarben nicht mitteilen
        idx, h, w = [k for k, ok in zip(idx, inlier) if ok], h[inlier], w[inlier]
        order = np.argsort(h)
        h, w, idx = h[order], w[order], [idx[i] for i in order]
        mean = (h * w).sum() / w.sum()
        total = (w * (h - mean) ** 2).sum()
        best = None
        for cut in range(1, len(h)):
            w0, w1 = w[:cut].sum(), w[cut:].sum()
            m0, m1 = (h[:cut] * w[:cut]).sum() / w0, (h[cut:] * w[cut:]).sum() / w1
            between = w0 * w1 / w.sum() * (m1 - m0) ** 2
            if best is None or between > best[0]:
                best = (between, cut, m1 - m0, w0, w1)
        if best is None or total <= 0:
            continue
        between, cut, diff, w0, w1 = best
        if diff <= apart or between / total <= clear:
            continue
        for k in (idx[cut:] if w0 >= w1 else idx[:cut]):
            keep[k] = False
    return keep


def compare_veo(result, det, veo_dir, align_path, start):
    """Nur zum Prüfen: Welche Veo-Identität steckt in jeder Spur, wie viel der Veo-Spieler ist abgedeckt?"""
    import veo_tracks
    align = json.loads(Path(align_path).read_text())
    tracks = veo_tracks.build_tracks(veo_tracks.load_export(veo_dir), align["H"])
    n = len(det["frames"])
    truth = []
    for fr in det["frames"]:
        people = veo_tracks.positions_at(tracks, float(start) + fr["t"] + align["timeOffsetS"])
        truth.append({(tracks[t]["team"], tracks[t]["jersey"]): p for t, p in people if tracks[t]["jersey"] >= 0})
    switches, purity, covered = 0, [], {}
    for tr in result:
        seq = []
        for f in sorted(tr["frames"]):
            p = tr["frames"][f][:2]
            near = [(np.hypot(*(p - q)), k) for k, q in truth[f].items()]
            k = min(near)[1] if near and min(near)[0] < 1.5 else None
            seq.append(k)
            if k is not None:
                covered.setdefault(k, set()).add(f)
        known = [k for k in seq if k is not None]
        if not known:
            continue
        # Wechsel der Identität, die mindestens 1 s anhält
        runs, cur, length = [], None, 0
        for k in known:
            if k == cur:
                length += 1
            else:
                if cur is not None:
                    runs.append((cur, length))
                cur, length = k, 1
        runs.append((cur, length))
        stable = [k for k, ln in runs if ln >= det["fps"]]
        switches += sum(1 for a, b in zip(stable, stable[1:]) if a != b)
        main = max(set(known), key=known.count)
        purity.append(known.count(main) / len(known))
    present = {k: sum(1 for f in range(n) if k in truth[f]) for k in {k for t in truth for k in t}}
    cover = np.mean([len(covered.get(k, ())) / v for k, v in present.items() if v > det["fps"]])
    print(f"Vergleich mit Veo: {len(present)} Veo-Spieler; Abdeckung im Mittel {cover:.0%} ihrer Bilder; "
          f"Reinheit der Spuren im Mittel {np.mean(purity):.0%}; Identitätswechsel (je mindestens 1 s): {switches}")


def main(det_path, camera_path, veo_dir=None, align_path=None, start=None):
    det = json.loads(Path(det_path).read_text())
    cam = veo_camera.load(camera_path)
    result = track(det, cam)
    fps = det["fps"]
    lengths = sorted(((max(t["frames"]) - min(t["frames"])) / fps for t in result), reverse=True)
    by_colour = {}
    for t in result:
        by_colour[t["colour"]] = by_colour.get(t["colour"], 0) + 1
    print(f"{len(result)} Spuren (Farbe: Anzahl {dict(sorted(by_colour.items()))}); Länge in s: "
          f"{[round(x, 1) for x in lengths[:30]]}")
    if veo_dir:
        compare_veo(result, det, veo_dir, align_path, start)


if __name__ == "__main__":
    if len(sys.argv) not in (3, 6):
        sys.exit(__doc__)
    main(*sys.argv[1:])
