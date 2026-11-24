#!/usr/bin/env python3
"""Liest Füße im Video: große und kleine Zehe und Ferse beider Füße je Person (RTMPose, Halpe26, 26 Punkte).

ViTPose (tools/veo_keypoints.py) liefert nur 17 COCO-Punkte und endet am Knöchel. Wo die Fußspitze hinzeigt und wo die Sohle liegt, wurde bisher
aus der Laufrichtung geschätzt und lag oft quer zum echten Schuh. Hier werden die Fußpunkte aus dem Bild gelesen. Halpe26 enthält die 17 COCO-Punkte
(0 bis 16), dazu Kopf 17, Hals 18, Becken 19, große Zehe links 20 und rechts 21, kleine Zehe links 22 und rechts 23, Ferse links 24 und rechts 25.

Modell: RTMPose-x Halpe26 (Apache-2.0, OpenMMLab), läuft über rtmlib und onnxruntime auf dem Prozessor; die Gewichte werden beim ersten
Aufruf geladen und liegen danach im Zwischenspeicher von rtmlib. Es gehen keine Bilder oder Daten hinaus.

Aufruf:
    .venv/bin/python tools/veo_feet.py VIDEO DETEKTIONEN.json [--kamera KAMERA.json] [--min-hoehe 60] [--von N --bis M] [--ausgabe DATEI.npz]

Ausgabe (Standard: DETEKTIONEN.json.feet.npz), Zeilen wie in DETEKTIONEN.json.keypoints.npz (gleiche Reihenfolge der Boxen):
    kp26   (N, 26, 3)  x, y in Pixeln der Linse, Sicherheit; alles 0 bei ausgelassenen Boxen
    index  (Bilder, 2, 2)
"""
import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import veo_camera  # noqa: E402
from veo_keypoints import on_pitch  # noqa: E402

LENSES = ("left", "right")
MODEL_URL = ("https://download.openmmlab.com/mmpose/v1/projects/rtmposev1/onnx_sdk/"
             "rtmpose-x_simcc-body7_pt-body7-halpe26_700e-384x288-7fb6e239_20230606.zip")
INPUT = (288, 384)       # Breite, Höhe
MIN_HEIGHT = 60          # Pixel Boxhöhe: darunter sind Füße im Bild nur wenige Pixel groß, das Ergebnis taugt nicht
FEET = {"lBigToe": 20, "rBigToe": 21, "lSmallToe": 22, "rSmallToe": 23, "lHeel": 24, "rHeel": 25}


def load_model(device="cpu"):
    from rtmlib.tools.pose_estimation import RTMPose
    return RTMPose(MODEL_URL, model_input_size=INPUT, to_openpose=False, backend="onnxruntime", device=device)


def main(video, det_path, camera_path=None, min_height=MIN_HEIGHT, first=0, last=None, out_path=None):
    det = json.loads(Path(det_path).read_text())
    frames = det["frames"]
    last = len(frames) if last is None else min(last, len(frames))
    out_path = out_path or str(det_path) + ".feet.npz"
    cam = veo_camera.load(camera_path) if camera_path else None
    model = load_model()
    cap = cv2.VideoCapture(video)
    index = np.zeros((len(frames), 2, 2), np.int64)
    total = sum(len(fr[lens]) for fr in frames for lens in LENSES)
    kp = np.zeros((total, 26, 3), np.float32)
    count = done = 0
    began = time.time()
    for fi, fr in enumerate(frames):
        ok, image = cap.read()
        if not ok:
            index[fi:] = count
            break
        h = image.shape[0] // 2
        for li, lens in enumerate(LENSES):
            boxes = np.array([r[:4] for r in fr[lens]], float).reshape(-1, 4)
            index[fi, li] = (count, count + len(boxes))
            if first <= fi < last and len(boxes):
                keep = on_pitch(cam, lens, boxes, 2.0) & ((boxes[:, 3] - boxes[:, 1]) >= min_height)
                lens_image = image[li * h:(li + 1) * h]
                for b in np.flatnonzero(keep):
                    xy, score = model(lens_image, [boxes[b].tolist()])
                    kp[count + b, :, :2], kp[count + b, :, 2] = xy[0], score[0]
                    done += 1
            count += len(boxes)
        if fi % 10 == 0:
            print(f"{fi + 1}/{len(frames)} Bilder, {done} Personen, {time.time() - began:.0f} s", end="\r", flush=True)
    np.savez_compressed(out_path, kp26=kp[:count], index=index)
    print(f"\n{done} Personen in {last - first} Bildern gerechnet ({time.time() - began:.0f} s) -> {out_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("detektionen")
    ap.add_argument("--kamera")
    ap.add_argument("--min-hoehe", type=int, default=MIN_HEIGHT)
    ap.add_argument("--von", type=int, default=0)
    ap.add_argument("--bis", type=int, default=None)
    ap.add_argument("--ausgabe")
    a = ap.parse_args()
    main(a.video, a.detektionen, a.kamera, a.min_hoehe, a.von, a.bis, a.ausgabe)
