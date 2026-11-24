#!/usr/bin/env python3
"""Legt Skelett und Ball einer fertigen Szene über das Video, zum Prüfen ohne Viewer.

Zeigt je gewählter Zeit einen Ausschnitt um den Ball (oder um einen Spieler): Gelenkpunkte der Figuren in Kamerasicht (Knochen), der Ball
mit seiner Höhe (Kreis am Boden, Linie zum Ball). Stimmen Skelett und Video nicht überein, sieht man es hier sofort; das ist die
Sichtprüfung für Haltung (Arme, Beine, Füße am Ball) und Ballbahn.

Aufruf:
    .venv/bin/python tools/scene_overlay.py SZENE_ORDNER KAMERA.json VIDEO AUSGABE.jpg ZEIT_S [ZEIT_S ...] [--spieler KENNUNG] [--ausschnitt 560]
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import veo_camera  # noqa: E402
from synth_poses import BONES, JOINTS, NAMES  # noqa: E402

LENSES = ("left", "right")
VIDEO_FPS = 30000 / 1001


def load_scene(scene_dir):
    scene_dir = Path(scene_dir)
    meta = json.loads((scene_dir / "meta.json").read_text())
    E, T = len(meta["entities"]), meta["frames"]
    tracks = np.fromfile(scene_dir / meta["tracks"]["file"], "<i2").reshape(T, E, 3).astype(float)
    tracks = np.where(tracks == meta["tracks"]["missing"], np.nan, tracks * meta["tracks"]["scale"])
    return meta, tracks


def pose_at(scene_dir, meta, frame, slot, n_slots):
    """Gelenke (20, 3) relativ zur Spielerposition in Metern oder None."""
    p = meta["poses"]
    chunk, i = divmod(frame, p["chunkFrames"])
    data = np.fromfile(Path(scene_dir) / p["path"].format(chunk=f"{chunk:03d}"), "<i2")
    J = len(p["skeleton"]["joints"])
    block = data.reshape(-1, n_slots, J, 3)[i, slot].astype(float)
    if (block == p["missing"]).any():
        return None
    return block * p["scale"]


def lens_for(cam, point):
    for li, name in enumerate(LENSES):
        uv = veo_camera.project(cam, name, [point])[0]
        if not np.isnan(uv).any() and 0 <= uv[0] < 2048 and 0 <= uv[1] < 1024:
            return li, uv
    return None, None


def draw(scene_dir, meta, tracks, cam, video, t, focus, size):
    ratio = VIDEO_FPS / 25
    f_out = min(int(round(t * 25)), meta["frames"] - 1)
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(f_out * ratio)))
    ok, image = cap.read()
    half = image.shape[0] // 2
    ents = meta["entities"]
    slots = [i for i, e in enumerate(ents) if e["kind"] == "player"]
    ball = next(i for i, e in enumerate(ents) if e["kind"] == "ball")
    centre = tracks[f_out, focus if focus is not None else ball]
    li, uv = lens_for(cam, [centre[0], centre[1], 0.5])
    if li is None:
        return None
    lens = (image[:half], image[half:])[li].copy()
    scale = 3
    x0, y0 = int(np.clip(uv[0] - size / 2, 0, 2048 - size)), int(np.clip(uv[1] - size / 2, 0, half - size))
    crop = cv2.resize(lens[y0:y0 + size, x0:x0 + size], None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    def px(points):
        q = veo_camera.project(cam, LENSES[li], points)
        return (q - [x0, y0]) * scale

    for slot, ent in enumerate(slots):
        pos = tracks[f_out, ent]
        if np.isnan(pos[0]) or np.hypot(*(pos[:2] - centre[:2])) > 14:
            continue
        pose = pose_at(scene_dir, meta, f_out, slot, len(slots))
        if pose is None:
            continue
        world = pose + [pos[0], pos[1], 0.0]
        q = px(world)
        for a, b, _, part in BONES:
            pa, pb = q[NAMES.index(a)], q[NAMES.index(b)]
            if not (np.isnan(pa).any() or np.isnan(pb).any()):
                cv2.line(crop, tuple(pa.astype(int)), tuple(pb.astype(int)), (0, 255, 255), 2, cv2.LINE_AA)
        for k in range(len(JOINTS)):
            if not np.isnan(q[k]).any():
                cv2.circle(crop, tuple(q[k].astype(int)), 3, (0, 0, 255), -1, cv2.LINE_AA)
    bp = tracks[f_out, ball]
    if not np.isnan(bp[0]):
        foot, top = px([[bp[0], bp[1], 0.0], [bp[0], bp[1], bp[2] + 0.11]])
        cv2.circle(crop, tuple(foot.astype(int)), 10, (255, 255, 0), 1, cv2.LINE_AA)
        cv2.line(crop, tuple(foot.astype(int)), tuple(top.astype(int)), (255, 255, 0), 1, cv2.LINE_AA)
        cv2.circle(crop, tuple(top.astype(int)), 6, (0, 255, 0), 2, cv2.LINE_AA)
        cv2.putText(crop, f"Ball z={bp[2]:.2f} m", (8, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.putText(crop, f"{t:.2f} s", (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    return crop


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene")
    ap.add_argument("camera")
    ap.add_argument("video")
    ap.add_argument("out")
    ap.add_argument("times", type=float, nargs="+")
    ap.add_argument("--spieler", default=None)
    ap.add_argument("--ausschnitt", type=int, default=560)
    a = ap.parse_args()
    meta, tracks = load_scene(a.scene)
    cam = veo_camera.load(a.camera)
    focus = next((i for i, e in enumerate(meta["entities"]) if e["id"] == a.spieler), None) if a.spieler else None
    tiles = [t for t in (draw(a.scene, meta, tracks, cam, a.video, t, focus, a.ausschnitt) for t in a.times) if t is not None]
    cols = min(2, len(tiles))
    rows = [np.hstack(tiles[i:i + cols] + [np.zeros_like(tiles[0])] * (cols - len(tiles[i:i + cols]))) for i in range(0, len(tiles), cols)]
    cv2.imwrite(a.out, np.vstack(rows))
    print(f"-> {a.out}")


if __name__ == "__main__":
    main()
