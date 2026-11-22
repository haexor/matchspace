#!/usr/bin/env python3
"""Ergänzt jede erkannte Person um eine Trikotfarbe (Farbton des Oberkörpers).
Damit lassen sich Erkennungen der richtigen Mannschaft zuordnen und Zuschauer aussortieren.

Aufruf:
    .venv/bin/python tools/veo_colors.py VIDEO DETEKTIONEN.json

Schreibt je Box einen sechsten Wert: 0 rot, 1 grün, 2 gelb, -1 sonstiges.
"""
import json
import sys

import cv2
import numpy as np

RANGES = {0: [(0, 9), (171, 180)], 1: [(40, 88)], 2: [(18, 34)]}  # OpenCV-Farbton 0..180


def classify(image, box):
    x1, y1, x2, y2 = box[:4]
    w, h = x2 - x1, y2 - y1
    crop = image[int(y1 + 0.18 * h):int(y1 + 0.5 * h) + 1, int(x1 + 0.25 * w):int(x2 - 0.25 * w) + 1]
    if crop.size == 0:
        return -1
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV).reshape(-1, 3)
    vivid = hsv[(hsv[:, 1] > 110) & (hsv[:, 2] > 70)]
    if len(vivid) < 0.2 * len(hsv):
        return -1
    share = {c: sum(((vivid[:, 0] >= lo) & (vivid[:, 0] <= hi)).sum() for lo, hi in rs) / len(hsv) for c, rs in RANGES.items()}
    best = max(share, key=share.get)
    return best if share[best] > 0.2 else -1


def main(video, det_path):
    det = json.load(open(det_path))
    cap = cv2.VideoCapture(video)
    half = det["lensSize"][1]
    wanted = {fr["frame"]: fr for fr in det["frames"]}
    index, counts = 0, {}
    while wanted:
        ok, image = cap.read()
        if not ok:
            break
        fr = wanted.pop(index, None)
        if fr:
            for lens, oy in (("left", 0), ("right", half)):
                part = image[oy:oy + half]
                for box in fr[lens]:
                    del box[5:]
                    box.append(classify(part, box))
                    counts[box[5]] = counts.get(box[5], 0) + 1
        index += 1
    json.dump(det, open(det_path, "w"))
    print("Boxen je Farbe (0 rot, 1 grün, 2 gelb, -1 sonst):", dict(sorted(counts.items())))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
