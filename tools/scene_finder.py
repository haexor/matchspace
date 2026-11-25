#!/usr/bin/env python3
"""Findet die besten Szenen eines Spiels: dort, wo sich das Geschehen nah vor der Kamera abspielt.

Spieler sind im Panorama nur 45 bis 125 Pixel hoch, der Ball 4 bis 9 Pixel; Fußkontakt, Schusstechnik und Zweikampf sind
nur in der Nahzone zu lesen (Streifen an der Kamera-Seitenlinie, ohne die Naht der beiden Linsenbilder). Zwei Stufen:

  vorauswahl   aus dem Basisspiel (Veos Positionen, nur als grobe Vorauswahl der Zeitfenster; Veos Ball ist geglättet und
               sagt über Kontakte nichts) die Fenster mit Ball in der Nahzone und Spielern am Ball. Nur davon werden
               Videoabschnitte geholt.
  bewerten     je geholtem Abschnitt eigene Messungen (Personenerkennung und eigene Ballsuche, tools/veo_detect.py und
               tools/veo_ball.py): Ballanteil, Nähe, Höhe des Ballführers in Pixeln, Beteiligte, Kontakte. Daraus Punkte und
               eine Rangliste.

Aufruf:
    .venv/bin/python tools/scene_finder.py vorauswahl BASIS_SPIEL [ANZAHL]
    .venv/bin/python tools/scene_finder.py bewerten KAMERA.json AUSGABE.json ABSCHNITT_DET.json [...]
(neben jeder DET.json liegt die .ball.npz; der Szenenname steht im Namen der Detektionsdatei)
"""
import json
import sys
from array import array
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import veo_camera  # noqa: E402
from scene_boxes import LENSES  # noqa: E402

NEAR_X = (5.0, 24.0)       # m: Betrag der Platz-x; darunter liegt die Naht zwischen den Linsenbildern, darüber wird es klein
NEAR_Y = (-27.5, -9.0)     # m: Streifen an der Kamera-Seitenlinie
SEAM_PX = 12               # Pixel: Boxen so nah am Rand eines Linsenbilds sind an der Naht geschnitten
FULL_HEIGHT_PX = 125.0     # Spielerhöhe in der besten Zone; darüber gibt es nichts mehr zu gewinnen
CARRIER_PX = 90.0          # Pixel: so nah am Ball (im Bild) gilt eine Box als der Ballführer
NEAR_BALL_M = 3.0          # m: Spieler so nah am Ball gelten als beteiligt
KICK_MS = 6.0              # m/s: Tempoänderung binnen KICK_S, die als möglicher Kontakt zählt
KICK_S = 0.2
WINDOW_S = 15.0            # s: eine Szene ist kurz; bewertet wird das beste Fenster dieser Länge im Abschnitt


def in_zone(p) -> np.ndarray:
    """Maske: Lage (..., 2) in der Nahzone (NaN zählt nicht)."""
    p = np.asarray(p, float)
    return (np.abs(p[..., 0]) >= NEAR_X[0]) & (np.abs(p[..., 0]) <= NEAR_X[1]) & (p[..., 1] >= NEAR_Y[0]) & (p[..., 1] <= NEAR_Y[1])


def merge(rows: list, min_gap: float) -> list:
    """rows: (Punkte, Start_s, ...) absteigend nach Punkten; behält je Geschehen nur das beste Fenster (Abstand >= min_gap)."""
    kept = []
    for row in sorted(rows, key=lambda r: -r[0]):
        if all(abs(row[1] - k[1]) >= min_gap for k in kept):
            kept.append(row)
    return kept


def read_base(base_dir) -> tuple:
    """Ball (T, 2), Spieler (T, N, 2) in Metern aus dem Basisspiel, dazu fps und die Halbzeiten."""
    base_dir = Path(base_dir)
    meta = json.loads((base_dir / "meta.json").read_text())
    E, T = len(meta["entities"]), meta["frames"]
    raw = array("h")
    with open(base_dir / meta["tracks"]["file"], "rb") as f:
        raw.fromfile(f, T * E * 3)
    x = np.array(raw, float).reshape(T, E, 3)
    x = np.where(x == meta["tracks"]["missing"], np.nan, x * meta["tracks"]["scale"])[:, :, :2]
    ball = next(i for i, e in enumerate(meta["entities"]) if e["kind"] == "ball")
    players = [i for i, e in enumerate(meta["entities"]) if e["kind"] == "player"]
    return x[:, ball], x[:, players], meta["fps"], meta["periods"]


def preselect(base_dir, count: int = 15, window_s: float = 15.0, step_s: float = 5.0, min_gap_s: float = 20.0) -> list:
    """Beste Fenster aus dem Basisspiel: [(Punkte, Videosekunde, Anteil in der Zone, Anteil mit Zweikampf, Anteil nah am Ball)]."""
    ball, players, fps, periods = read_base(base_dir)
    T = len(ball)
    seen = ~np.isnan(ball[:, 0])
    close = (np.linalg.norm(players - ball[:, None, :], axis=2) < NEAR_BALL_M).sum(axis=1)
    zone = in_zone(ball) & seen
    rows = []
    w, step = int(window_s * fps), int(step_s * fps)
    for s in range(0, T - w + 1, step):
        sl = slice(s, s + w)
        if seen[sl].mean() < 0.7:
            continue
        z, duel, dribble = zone[sl].mean(), ((close[sl] >= 2) & seen[sl]).mean(), ((close[sl] >= 1) & seen[sl]).mean()
        rows.append((float(z * (0.4 + 0.8 * duel + 0.4 * dribble)), video_second(periods, s, fps), float(z), float(duel), float(dribble)))
    return merge(rows, min_gap_s)[:count]


def video_second(periods: list, frame: int, fps: float) -> float:
    """Videosekunde eines Bildes des Basisspiels (Halbzeitbeginn im Video plus Zeit seit Halbzeitbeginn)."""
    p = next(q for q in periods if q["startFrame"] <= frame <= q["endFrame"])
    return p["videoStartS"] + (frame - p["startFrame"]) / fps


def kicks(pos: np.ndarray, fps: float) -> int:
    """Anzahl möglicher Kontakte: Tempoänderungen des Balls (m/s) von mehr als KICK_MS binnen KICK_S, je Ereignis einmal."""
    step = max(1, round(KICK_S * fps))
    ok = ~np.isnan(pos[:, 0])
    velocity = np.full(len(pos), np.nan)
    velocity[1:] = np.linalg.norm(np.diff(pos, axis=0), axis=1) * fps
    velocity[1:][~(ok[1:] & ok[:-1])] = np.nan
    change = np.abs(velocity[step:] - velocity[:-step])
    hits = np.flatnonzero(np.nan_to_num(change) > KICK_MS)
    return int(1 + (np.diff(hits) > step).sum()) if len(hits) else 0


def score_clip(det: dict, ball: dict, cam: dict) -> dict:
    """Eigene Einzelwerte und Punkte eines Abschnitts. det: Erkennungen je Bild (tools/veo_detect.py); ball: pos (n, 2) am
    Boden, pixel (n, 3) = Linse, u, v (tools/veo_ball.py)."""
    fps = float(ball["fps"])
    n_all = min(len(det["frames"]), len(ball["pos"]))
    overall = float((~np.isnan(ball["pos"][:n_all, 0])).mean()) if n_all else 0.0
    # bestes Fenster: dort, wo der Ball am häufigsten gefunden wurde
    w = min(n_all, int(WINDOW_S * fps))
    cum = np.concatenate([[0], np.cumsum(~np.isnan(ball["pos"][:n_all, 0]))])
    s0 = int(np.argmax(cum[w:] - cum[:n_all - w + 1])) if w else 0
    frames, pos, pix = det["frames"][s0:s0 + w], ball["pos"][s0:s0 + w], ball["pixel"][s0:s0 + w]
    n = min(len(frames), len(pos))
    found = ~np.isnan(pos[:n, 0])
    heights, seam, involved = [], [], []
    for i in np.flatnonzero(found):
        li = int(pix[i, 0])
        rows = frames[i][LENSES[li]]
        if not rows:
            continue
        boxes = np.array([r[:4] for r in rows], float)
        centre = np.column_stack([(boxes[:, 0] + boxes[:, 2]) / 2, boxes[:, 3]])
        near = np.linalg.norm(centre - pix[i, 1:3], axis=1)
        k = int(np.argmin(near))
        if near[k] > CARRIER_PX:
            continue
        heights.append(boxes[k, 3] - boxes[k, 1])
        seam.append(boxes[k, 2] > 2048 - SEAM_PX if li == 0 else boxes[k, 0] < SEAM_PX)
        feet = np.array([veo_camera.to_ground(cam, LENSES[li], [[c[0], c[1]]], 0.0)[0][0] for c in centre])
        involved.append(int((np.linalg.norm(feet - pos[i], axis=1) < NEAR_BALL_M).sum()))
    share = float(found.mean()) if n else 0.0
    zone = float(in_zone(pos[:n])[found].mean()) if found.any() else 0.0
    carrier = float(np.median(heights)) if heights else 0.0
    cut = float(np.mean(seam)) if seam else 0.0
    people = float(np.median(involved)) if involved else 0.0
    contacts = kicks(pos[:n], fps)
    # Nähe (Spielerhöhe des Ballführers) und Ballanteil gehen multiplikativ ein: ohne Ball oder ohne Auflösung gibt es nichts zu messen
    points = share * min(carrier / FULL_HEIGHT_PX, 1.0) * (1.0 - 0.5 * cut) * (0.5 + 0.15 * min(people, 3) + 0.05 * min(contacts, 6))
    return {"punkte": round(points, 3), "fensterStartS": round(s0 / fps, 1), "fensterS": round(n / fps, 1),
            "ballanteilGesamt": round(overall, 3), "ballanteil": round(share, 3), "zone": round(zone, 3), "ballfuehrerHoehePx": round(carrier, 1),
            "nahtanteil": round(cut, 3), "beteiligte": round(people, 1), "moeglicheKontakte": contacts, "bilder": n}


def rank(cam_path, out_path, det_paths) -> list:
    cam = veo_camera.load(cam_path)
    rows = []
    for path in det_paths:
        det = json.loads(Path(path).read_text())
        ball = dict(np.load(f"{path}.ball.npz"))
        name = Path(path).name.removesuffix(".det.json")
        rows.append({"szene": name, **score_clip(det, ball, cam)})
    rows.sort(key=lambda r: -r["punkte"])
    Path(out_path).write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    return rows


def main(argv: list) -> None:
    if len(argv) >= 2 and argv[0] == "vorauswahl":
        for points, second, zone, duel, dribble in preselect(argv[1], int(argv[2]) if len(argv) > 2 else 15):
            print(f"Video {second:7.0f} s  Punkte {points:.2f}  Zone {zone:.2f}  Zweikampf {duel:.2f}  Ball bei Spieler {dribble:.2f}")
    elif len(argv) >= 4 and argv[0] == "bewerten":
        for r in rank(argv[1], argv[2], argv[3:]):
            print(f"{r['szene']:>14}  Punkte {r['punkte']:.2f}  Ball {r['ballanteil']:.0%} (Abschnitt {r['ballanteilGesamt']:.0%}, ab {r['fensterStartS']:.0f} s)  Zone {r['zone']:.0%}  "
                  f"Ballführer {r['ballfuehrerHoehePx']:.0f} px  Naht {r['nahtanteil']:.0%}  beteiligt {r['beteiligte']:.1f}  Kontakte {r['moeglicheKontakte']}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
