#!/usr/bin/env python3
"""Findet den Ball selbst im Video, statt Veos Ballposition zu übernehmen.

Veos Ballspur ist grob und hinkt nach; im Viewer lag der Ball deshalb oft neben dem Spieler, der ihn führt.
Hier wird der Ball in jedem Bild beider Linsen gesucht (YOLO, Klasse „sports ball“, auch unsichere Treffer),
ohne Veo-Daten: Das spätere eigene Kamerasystem liefert nur Video. Im Panorama ist der Ball nur 5 bis 8 Pixel
groß, entsprechend gibt es Fehltreffer:

  - Dinge, die über mehr als 2 Sekunden verteilt immer wieder am selben Pixel erscheinen (Reservebälle,
    Hütchen), zählen nicht. Ein Spielball, der so lange still liegt (Standard), ginge dabei verloren.
  - Treffer werden zu Stücken verbunden, die eine mögliche Ballbewegung sind; aus den Stücken wird die
    zeitliche Kette mit der höchsten Sicherheit gewählt, in der der Ball jeden Weg mit höchstens 35 m/s
    schafft. Es gibt nur einen Ball.

Wo der Ball nicht zu sehen ist (am Fuß verdeckt, unscharf im Flug), füllt tools/veo_scene.py die Lücke.

Die Lage am Boden kommt aus dem Mittelpunkt des Balls im Bild, angenommen auf Ballhöhe über dem Rasen. Ein
hoher Ball erscheint dadurch zu weit von der Kamera entfernt; Flughöhen werden noch nicht bestimmt.

Aufruf (schreibt DETEKTIONEN.json.ball.npz; tools/veo_scene.py liest es, wenn vorhanden):
    .venv/bin/python tools/veo_ball.py SZENENVIDEO DETEKTIONEN.json KAMERA.json [BASIS_SPIEL START_S]
BASIS_SPIEL und START_S nur zum Vergleich mit Veos Ballspur.
"""
import json
import sys
from array import array
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import veo_camera  # noqa: E402

LENSES = ("left", "right")
BALL_CLASS = 32
MIN_CONF = 0.08
RADIUS = 0.11            # m
STATIC_PX, STATIC_S, STATIC_HITS = 3.0, 2.0, 6   # so oft über so lange am selben Pixel (auch mit Pausen): kein Spielball
MAX_SPEED = 35.0         # m/s
LINK_GAP = 0.25          # s: so lange darf ein Ballstück ohne Treffer bleiben
PIECE_COST = 0.35        # Grundbetrag je Stück: einzelne Treffer unter dieser Sicherheit zählen allein nicht


def detect(video):
    from ultralytics import YOLO
    model = YOLO("models/yolo11m.pt")
    cap = cv2.VideoCapture(str(video))
    half = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) // 2
    out = []
    while True:
        ok, image = cap.read()
        if not ok:
            break
        res = model.predict([image[:half], image[half:]], classes=[BALL_CLASS], conf=MIN_CONF, imgsz=2048, verbose=False)
        out.append([[li, (b[0] + b[2]) / 2, (b[1] + b[3]) / 2, b[4]] for li, r in enumerate(res) for b in r.boxes.data.tolist()])
        if len(out) % 150 == 0:
            print(f"  {len(out)} Bilder", flush=True)
    return out


def drop_static(cands, fps):
    """Entfernt Kandidaten, die über STATIC_S fast am selben Pixel liegen."""
    span = int(STATIC_S * fps)
    keyed = {}
    for f, cs in enumerate(cands):
        for c in cs:
            keyed.setdefault((c[0], round(c[1] / STATIC_PX), round(c[2] / STATIC_PX)), []).append(f)
    static = set()
    for key, frames in keyed.items():
        frames = np.array(sorted(set(frames)))
        if len(frames) >= STATIC_HITS and frames[-1] - frames[0] >= span:   # immer wieder am selben Pixel, auch mit Pausen
            static.add(key)

    def near_static(c):
        return any((c[0], round(c[1] / STATIC_PX) + dx, round(c[2] / STATIC_PX) + dy) in static for dx in (-1, 0, 1) for dy in (-1, 0, 1))
    return [[c for c in cs if not near_static(c)] for cs in cands], len(static)


def tracklets(ground, fps):
    """Verbindet Kandidaten über die Zeit zu Stücken, die eine mögliche Ballbewegung sind (höchstens MAX_SPEED,
    Lücken bis LINK_GAP). Rückgabe: Liste von Stücken, je Liste von (Bild, Lage, Sicherheit, Linse, u, v)."""
    open_, done = [], []
    gap = max(1, int(LINK_GAP * fps))
    for f, g in enumerate(ground):
        still = []
        for tr in open_:
            if f - tr[-1][0] > gap:
                done.append(tr)
            else:
                still.append(tr)
        open_ = still
        taken = set()
        for c in sorted(g, key=lambda c: -c[1]):
            best, best_d = None, None
            for k, tr in enumerate(open_):
                if k in taken:
                    continue
                f0, p0 = tr[-1][0], tr[-1][1]
                guess = p0
                if len(tr) >= 2 and tr[-1][0] > tr[-2][0]:   # mit der letzten Geschwindigkeit weiter
                    guess = p0 + (p0 - tr[-2][1]) / (tr[-1][0] - tr[-2][0]) * (f - f0)
                d = np.linalg.norm(c[0] - guess)
                if d <= MAX_SPEED * (f - f0) / fps * 0.5 + 0.7 and (best_d is None or d < best_d):
                    best, best_d = k, d
            item = (f, c[0], c[1], c[2], c[3], c[4])
            if best is None:
                open_.append([item])
                taken.add(len(open_) - 1)
            else:
                open_[best].append(item)
                taken.add(best)
    return done + open_


def main(video, det_path, camera_path, base_dir=None, start=None):
    cam = veo_camera.load(camera_path)
    det = json.loads(Path(det_path).read_text())
    fps = det["fps"]
    L, W = cam["pitch"]["length"], cam["pitch"]["width"]

    cache = Path(f"{det_path}.ballcands.json")   # Rohtreffer: die Suche dauert Minuten, die Auswahl Sekunden
    if cache.exists():
        cands = json.loads(cache.read_text())
    else:
        print("Suche den Ball in jedem Bild ...", flush=True)
        cands = detect(video)
        cache.write_text(json.dumps(cands))
    n = len(cands)
    cands, static = drop_static(cands, fps)
    # Kandidaten am Boden, auf dem Platz (bis 2 m daneben)
    ground = []
    for f, cs in enumerate(cands):
        g = []
        for li, u, v, conf in cs:
            p, _ = veo_camera.to_ground(cam, LENSES[li], [[u, v]], RADIUS)
            if not np.isnan(p[0, 0]) and abs(p[0, 0]) < L / 2 + 2 and abs(p[0, 1]) < W / 2 + 2:
                g.append((p[0], conf, li, u, v))
        ground.append(g)
    # Stücke bilden und die beste zeitliche Kette wählen: jedes Stück zählt mit der Summe seiner Sicherheiten
    # (abzüglich eines Grundbetrags, damit einzelne unsichere Treffer allein nicht reichen); zwischen zwei Stücken
    # muss der Ball den Weg mit höchstens MAX_SPEED schaffen können.
    pieces = sorted(tracklets(ground, fps), key=lambda tr: tr[0][0])
    score = [sum(it[2] for it in tr) - PIECE_COST for tr in pieces]
    best, prev = list(score), [-1] * len(pieces)
    for j, tr in enumerate(pieces):
        for i in range(j):
            a = pieces[i]
            dt = (tr[0][0] - a[-1][0]) / fps
            if dt <= 0 or np.linalg.norm(tr[0][1] - a[-1][1]) > MAX_SPEED * dt + 0.7:
                continue
            if best[i] + score[j] > best[j]:
                best[j], prev[j] = best[i] + score[j], i
    pos = np.full((n, 2), np.nan)
    pix = np.full((n, 3), np.nan)
    j = int(np.argmax(best)) if pieces else -1
    chosen = 0
    while j >= 0:
        for f, p, _, li, u, v in pieces[j]:
            pos[f], pix[f] = p, (li, u, v)
        chosen += 1
        j = prev[j]
    seen = ~np.isnan(pos[:, 0])
    print(f"Ball in {seen.sum()} von {n} Bildern selbst gefunden ({seen.mean():.0%}), aus {chosen} Stücken; "
          f"{static} feste Fehltreffer ausgeschlossen")
    if base_dir is not None:   # nur zum Vergleich: Abstand zu Veos Ballspur
        compare_veo(pos, fps, base_dir, float(start))
    np.savez_compressed(f"{det_path}.ball.npz", pos=pos, pixel=pix, fps=fps)
    print(f"-> {det_path}.ball.npz")


def compare_veo(pos, fps, base_dir, start):
    base_dir = Path(base_dir)
    base = json.loads((base_dir / "meta.json").read_text())
    E = len(base["entities"])
    ball = next(i for i, e in enumerate(base["entities"]) if e["kind"] == "ball")
    period = next(p for p in base["periods"] if p["videoStartS"] <= start <= p["videoStartS"] + (p["endFrame"] - p["startFrame"]) / base["fps"])
    first = period["startFrame"] + round((start - period["videoStartS"]) * base["fps"])
    total = int(len(pos) / fps * base["fps"]) + 2
    data = array("h")
    with open(base_dir / base["tracks"]["file"], "rb") as f:
        f.seek(first * E * 3 * 2)
        data.fromfile(f, total * E * 3)
    veo = np.array(data, float).reshape(-1, E, 3)[:, ball, :2]
    veo = np.where(veo == base["tracks"]["missing"], np.nan, veo * base["tracks"]["scale"])
    t = np.arange(len(veo)) / base["fps"]
    ok = ~np.isnan(veo[:, 0])
    ref = np.column_stack([np.interp(np.arange(len(pos)) / fps, t[ok], veo[ok, a]) for a in range(2)])
    d = np.linalg.norm(pos - ref, axis=1)
    print(f"Vergleich mit Veos Ballspur: Abstand im Median {np.nanmedian(d):.2f} m, 90 % unter {np.nanpercentile(d, 90):.2f} m, "
          f"mehr als 3 m in {int((d > 3).sum())} Bildern")


if __name__ == "__main__":
    if len(sys.argv) not in (4, 6):
        sys.exit(__doc__)
    main(*sys.argv[1:])
