#!/usr/bin/env python3
"""Erkennt Personen in einem Veo-Panorama (zwei Linsenbilder übereinander).

Aufruf:
    .venv/bin/python tools/veo_detect.py VIDEO AUSGABE.json [BILDER_PRO_SEKUNDE]

Ausgabe: je ausgewertetem Bild die Zeit im Clip und die Boxen je Linse
(x1, y1, x2, y2, Sicherheit) in Pixeln des jeweiligen Linsenbilds.
"""
import json
import sys

import cv2
from ultralytics import YOLO


def main(video, out, rate="1"):
    model = YOLO("models/yolo11m.pt")
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    step = max(1, round(fps / float(rate)))
    half = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) // 2
    frames, index = [], 0
    while True:
        ok, image = cap.read()
        if not ok:
            break
        if index % step == 0:
            lenses = [image[:half], image[half:]]
            results = model.predict(lenses, classes=[0], conf=0.2, imgsz=2048, verbose=False)
            frames.append({
                "frame": index,
                "t": index / fps,
                "left": [[round(v, 1) for v in box] for box in results[0].boxes.data[:, :5].tolist()],
                "right": [[round(v, 1) for v in box] for box in results[1].boxes.data[:, :5].tolist()],
            })
            if len(frames) % 20 == 0:
                print(f"{len(frames)} Bilder, t={index / fps:.0f}s", flush=True)
        index += 1
    json.dump({"video": video, "fps": fps, "lensSize": [int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), half], "frames": frames}, open(out, "w"))
    print(f"{len(frames)} Bilder -> {out}")


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    main(*sys.argv[1:])
