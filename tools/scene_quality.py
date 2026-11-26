#!/usr/bin/env python3
"""Nähe einer Szene zur Veo-Kamera: Wie groß (in Pixeln) ist der Spieler am Ball im Panoramabild?

Alle Messgenauigkeit hängt an der Auflösung: Der Ball ist nur wenige Pixel groß, ein Spieler weit weg unter 60 Pixel hoch. Dort sind Ball und
Haltung nicht zuverlässig (der Ball rauscht in der Tiefe um Meter, Gelenke sind zu klein). Der Viewer lädt eine Szene darum nur, wenn sie
nah ist und der Ball nicht springt (meta.json: `quality.ok`); mit `&ferne=1` lässt sie sich trotzdem öffnen.

Gemessen wird aus der fertigen Szene (Bahnen und Kamera): je Bild mit Ball der nächste Spieler (höchstens NEAR_BALL_M weit); seine Kopf-/Fußhöhe
(1,7 m und 0 m über seiner Lage) wird in das Panorama projiziert, die Höhe in Pixeln gemittelt (Median). Ab NEAR_PX gilt die Szene als nah
(die Wurf-Szene liegt bei rund 85, die beste Nahszene bei über 110; die Rangliste in tools/scene_finder.py misst dasselbe aus den Boxen).

Aufruf:  .venv/bin/python tools/scene_quality.py SZENE_ORDNER KAMERA.json   (schreibt `quality` in meta.json)
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import veo_camera  # noqa: E402

NEAR_PX = 80.0             # Pixel: ab dieser Spielerhöhe am Ball gilt eine Szene als nah
NEAR_BALL_M = 3.0          # m: so nah am Ball steht der Spieler, dessen Höhe gemessen wird
PLAYER_M = 1.7             # m: angenommene Körperhöhe für die Projektion
BALL_JUMP_MS = 25.0        # m/s: schneller bewegt sich der Ball im Jugendfußball nicht; Bilder darüber sind Sprünge der Spur (Gewehrkugel)
IMAGE = (2048, 1024)       # Pixel eines Linsenbilds


def pixel_height(cam, xy: np.ndarray) -> float | None:
    """Höhe eines Spielers in Pixeln, der bei xy (Meter) steht, in der Linse, in der er im Bild liegt; None, wenn er in keiner liegt."""
    best = None
    for lens in veo_camera.LENSES:
        foot = veo_camera.project(cam, lens, [[xy[0], xy[1], 0.0]])[0]
        head = veo_camera.project(cam, lens, [[xy[0], xy[1], PLAYER_M]])[0]
        if np.isnan(foot).any() or np.isnan(head).any():
            continue
        if 0 <= foot[0] < IMAGE[0] and 0 <= foot[1] < IMAGE[1]:
            h = float(np.linalg.norm(foot - head))
            best = h if best is None else max(best, h)
    return best


def lead_height(cam, xy: np.ndarray, kinds: list, ball: int) -> float | None:
    """Mittlere Höhe (Median, Pixel) des Spielers am Ball über alle Bilder, in denen der Ball da ist und ein Spieler höchstens NEAR_BALL_M entfernt steht."""
    players = [i for i, k in enumerate(kinds) if k == "player"]
    heights = []
    for f in range(len(xy)):
        b = xy[f, ball]
        if np.isnan(b).any():
            continue
        d = np.linalg.norm(xy[f, players] - b, axis=1)
        d = np.where(np.isnan(d), np.inf, d)
        k = int(np.argmin(d))
        if d[k] > NEAR_BALL_M:
            continue
        h = pixel_height(cam, xy[f, players[k]])
        if h is not None:
            heights.append(h)
    return float(np.median(heights)) if heights else None


def ball_jumps(xy: np.ndarray, ball: int, fps: float) -> int:
    """Bilder, in denen der Ball (Lage am Boden) sich schneller als BALL_JUMP_MS bewegt, ohne dass er in einem der beiden Bilder fehlt."""
    step = np.linalg.norm(np.diff(xy[:, ball], axis=0), axis=1) * fps
    return int(np.nansum(step > BALL_JUMP_MS))


def quality(meta: dict, xy: np.ndarray, cam) -> dict:
    kinds = [e["kind"] for e in meta["entities"]]
    ball = kinds.index("ball") if "ball" in kinds else None
    px = lead_height(cam, xy, kinds, ball) if ball is not None else None
    jumps = ball_jumps(xy, ball, float(meta["fps"])) if ball is not None else 0
    return {"leadHeightPx": None if px is None else round(px, 1), "minPx": NEAR_PX, "near": bool(px is not None and px >= NEAR_PX),
            "ballJumps": jumps, "ok": bool(px is not None and px >= NEAR_PX and jumps == 0)}


def main(scene_dir, camera_path) -> dict:
    import game_analysis
    scene = game_analysis.load(scene_dir)
    q = quality(scene.meta, scene.xy, veo_camera.load(camera_path))
    path = Path(scene_dir) / "meta.json"
    meta = json.loads(path.read_text())
    meta["quality"] = q
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    print(f"{scene_dir}: Spieler am Ball {q['leadHeightPx']} px hoch -> {'nah' if q['near'] else 'FERN'}, Ballsprünge {q['ballJumps']} -> {'ok' if q['ok'] else 'Viewer lädt nur mit &ferne=1'}")
    return q


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
