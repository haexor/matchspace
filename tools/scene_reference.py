#!/usr/bin/env python3
"""Schneidet aus dem Originalvideo einen Vergleichsausschnitt zu einer fertigen Szene (für die Anzeige unter der Szene im Viewer).

Der Ausschnitt ist für die ganze Szene fest (kein Wackeln beim Vergleichen), deckt alle Spieler und den Ball der Szene ab und hat das
Seitenverhältnis 16:9. Die Bilder folgen dem Takt der Szene (25 Hz), damit Bild n des Videos zu Bild n der Szene gehört. Das Video
bleibt lokal neben den Szenendaten (web/data/ ist nicht im Repository); in meta.json steht `reference` mit Dateiname und Zeitbezug.

Aufruf:
    .venv/bin/python tools/scene_reference.py SZENE_ORDNER KAMERA.json VIDEO [--breite 1280] [--rand 90]
VIDEO ist der Szenenabschnitt (Beginn = Szenenbeginn).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import veo_camera  # noqa: E402
from scene_overlay import LENSES, VIDEO_FPS, load_scene  # noqa: E402

ASPECT = 16 / 9
MIN_WIDTH = 720        # Pixel: kleiner wird der Ausschnitt nicht (sonst nur ein Spieler riesig)
HEAD = 2.0             # m: Höhe, bis zu der die Spieler in den Ausschnitt passen
LENS_W, LENS_H = 2048, 1024


def region(meta, tracks, cam, margin):
    """(Linse, x0, y0, Breite, Höhe) in Linsenpixeln: fester Ausschnitt, der alle Spieler und den Ball der Szene enthält."""
    pts = {0: [], 1: []}
    for e in range(tracks.shape[1]):
        for f in range(0, len(tracks), 5):
            p = tracks[f, e]
            if np.isnan(p[0]):
                continue
            for z in (0.0, HEAD):
                for li, name in enumerate(LENSES):
                    uv = veo_camera.project(cam, name, [[p[0], p[1], z]])[0]
                    if not np.isnan(uv).any() and 0 <= uv[0] < LENS_W and 0 <= uv[1] < LENS_H:
                        pts[li].append(uv)
                        break
    lens = 0 if len(pts[0]) >= len(pts[1]) else 1
    uv = np.array(pts[lens])
    lo, hi = uv.min(axis=0) - margin, uv.max(axis=0) + margin
    cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    w = max(hi[0] - lo[0], (hi[1] - lo[1]) * ASPECT, MIN_WIDTH)
    w = min(w, LENS_W, LENS_H * ASPECT)
    h = w / ASPECT
    x0, y0 = float(np.clip(cx - w / 2, 0, LENS_W - w)), float(np.clip(cy - h / 2, 0, LENS_H - h))
    return lens, int(x0), int(y0), int(w), int(h)


def render(video, out, lens, box, frames, width):
    x0, y0, w, h = box
    height = int(round(width / ASPECT / 2)) * 2
    cap = cv2.VideoCapture(str(video))
    images = []
    while True:
        ok, image = cap.read()
        if not ok:
            break
        half = image.shape[0] // 2
        images.append((image[:half], image[half:])[lens][y0:y0 + h, x0:x0 + w])
    if not images:
        raise SystemExit(f"keine Bilder in {video}")
    ratio = VIDEO_FPS / 25
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}", "-r", "25",
                           "-i", "-", "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-pix_fmt", "yuv420p", "-an",
                           "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE)
    for f in range(frames):
        src = images[min(len(images) - 1, int(round(f * ratio)))]
        ff.stdin.write(cv2.resize(src, (width, height), interpolation=cv2.INTER_CUBIC).tobytes())
    ff.stdin.close()
    if ff.wait() != 0:
        raise SystemExit("ffmpeg fehlgeschlagen")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene")
    ap.add_argument("camera")
    ap.add_argument("video")
    ap.add_argument("--breite", type=int, default=1280)
    ap.add_argument("--rand", type=int, default=90)
    a = ap.parse_args()
    scene = Path(a.scene)
    meta, tracks = load_scene(scene)
    cam = veo_camera.load(a.camera)
    lens, x0, y0, w, h = region(meta, tracks, cam, a.rand)
    out = scene / "original.mp4"
    render(a.video, out, lens, (x0, y0, w, h), meta["frames"], a.breite)
    meta["reference"] = {"file": out.name, "startFrame": 0, "fps": meta["fps"],
                         "note": "Originalausschnitt, nur lokal; Bild n gehört zu Szenenbild n"}
    (scene / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    print(f"-> {out} (Linse {LENSES[lens]}, Ausschnitt {w}x{h} bei {x0},{y0})")


if __name__ == "__main__":
    main()
