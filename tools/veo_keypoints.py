#!/usr/bin/env python3
"""Schätzt 2D-Gelenkpunkte für jede erkannte Person einer Szene (ViTPose, 17 COCO-Punkte).

Die Spieler sind im Veo-Panorama nur rund 55 Pixel hoch. ViTPose arbeitet je Person auf einem
vergrößerten Ausschnitt und liefert dort deutlich vollständigere Punkte als ein Modell, das
das ganze Bild auf einmal ansieht. Das Ergebnis hängt nur an den Boxen aus tools/veo_detect.py,
nicht an der Zuordnung zu Spielern, und wird deshalb einmal je Szene gerechnet.

Mit --kamera werden nur Personen gerechnet, deren Fußpunkt auf dem Platz oder höchstens --rand
Meter daneben liegt (Zuschauer und Bank fallen weg, das ist rund die Hälfte aller Boxen). Die
übrigen Boxen bekommen leere Punkte. Ausschnitte und Auswertung der Heatmaps laufen auf der
Grafikkarte und über mehrere Bilder gebündelt.

Aufruf:
    .venv/bin/python tools/veo_keypoints.py VIDEO DETEKTIONEN.json [--kamera KAMERA.json] [--rand 2.0]
                                            [--modell models/vitpose-plus-base] [--ausgabe DATEI.npz]

Ausgabe (Standard: DETEKTIONEN.json.keypoints.npz):
    kp      (N, 17, 3)  x, y in Pixeln der Linse, Sicherheit 0..1; alles 0 bei ausgelassenen Boxen
    colour  (N,)        Farbklasse des Rumpfs wie tools/veo_colors.py, -1 keine, -2 nicht bestimmbar
    index   (Bilder, 2, 2)  je Bild und Linse: erste und letzte+1 Zeile in kp, Reihenfolge wie die Boxen
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
from veo_colors import RANGES  # noqa: E402

MODEL_DIR = "models/vitpose-plus-base"   # usyd-community/vitpose-plus-base, Apache-2.0; rund fünfmal langsamer und kaum anders: vitpose-plus-huge
LENSES = ("left", "right")
TORSO_CONF = 0.3
BATCH = 96            # Personen je Durchlauf des Netzes
INPUT = (192, 256)    # Breite, Höhe des Ausschnitts, den das Netz sieht
PADDING = 1.25        # Rand um die Box


def torso_colour(image, kp):
    """Farbklasse des Trikots aus dem Viereck Schultern-Hüften; None, wenn nicht bestimmbar.

    image: Bild (BGR), kp: (17, 3) Gelenkpunkte in Koordinaten dieses Bilds."""
    if (kp[[5, 6, 11, 12], 2] < TORSO_CONF).any():
        return None
    quad = kp[[5, 6, 12, 11], :2]
    x0, y0 = np.floor(quad.min(axis=0)).astype(int) - 1
    x1, y1 = np.ceil(quad.max(axis=0)).astype(int) + 2
    x0, y0 = max(x0, 0), max(y0, 0)
    patch = image[y0:y1, x0:x1]
    if patch.size == 0:
        return None
    mask = np.zeros(patch.shape[:2], np.uint8)
    cv2.fillConvexPoly(mask, cv2.convexHull((quad - [x0, y0]).astype(np.int32)), 1)
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)[mask > 0]
    if len(hsv) < 12:
        return None
    vivid = hsv[(hsv[:, 1] > 110) & (hsv[:, 2] > 70)]
    share = {c: sum(((vivid[:, 0] >= lo) & (vivid[:, 0] <= hi)).sum() for lo, hi in rs) / len(hsv) for c, rs in RANGES.items()}
    best = max(share, key=share.get)
    return best if share[best] > 0.2 else -1


class Estimator:
    """ViTPose auf Boxen eines Bilds; boxes: (n, 4) x1, y1, x2, y2. Rückgabe (n, 17, 3).

    Rechnet wie die Vor- und Nachverarbeitung von transformers (Ausschnitt ohne Versatz nach
    Huang et al., Lage im Heatmap nach Zhang et al.), aber auf der Grafikkarte."""

    def __init__(self, model_dir=None):
        import torch
        from transformers import VitPoseForPoseEstimation
        self.torch = torch
        self.model = VitPoseForPoseEstimation.from_pretrained(model_dir or MODEL_DIR, torch_dtype=torch.float16).cuda().eval()
        self.mean = torch.tensor([0.485, 0.456, 0.406], device="cuda").view(1, 3, 1, 1) * 255
        self.std = torch.tensor([0.229, 0.224, 0.225], device="cuda").view(1, 3, 1, 1) * 255
        taps = torch.exp(-torch.arange(-5, 6, device="cuda", dtype=torch.float32) ** 2 / (2 * 0.8**2))
        self.taps = taps / taps.sum()

    def regions(self, boxes):
        """Mitte und Größe des Ausschnitts je Box: Seitenverhältnis des Netzes, dazu Rand."""
        boxes = np.asarray(boxes, np.float32).reshape(-1, 4)
        centre = (boxes[:, :2] + boxes[:, 2:]) / 2
        w, h = boxes[:, 2] - boxes[:, 0], boxes[:, 3] - boxes[:, 1]
        aspect = INPUT[0] / INPUT[1]
        size = np.column_stack([np.maximum(w, h * aspect), np.maximum(h, w / aspect)]) * PADDING
        return centre, size

    def crops(self, image, centre, size):
        """image: (H, W, 3) uint8 BGR auf der Grafikkarte -> normierte Ausschnitte (n, 3, 256, 192)."""
        torch = self.torch
        h, w = image.shape[:2]
        c, s = torch.as_tensor(centre, device="cuda"), torch.as_tensor(size, device="cuda")
        tx = torch.linspace(0, 1, INPUT[0], device="cuda")
        ty = torch.linspace(0, 1, INPUT[1], device="cuda")
        x = c[:, 0, None] - s[:, 0, None] / 2 + tx[None] * s[:, 0, None]
        y = c[:, 1, None] - s[:, 1, None] / 2 + ty[None] * s[:, 1, None]
        grid = torch.stack([(2 * x / (w - 1) - 1)[:, None, :].expand(-1, INPUT[1], -1), (2 * y / (h - 1) - 1)[:, :, None].expand(-1, -1, INPUT[0])], dim=-1)
        rgb = image.permute(2, 0, 1).flip(0).float()[None].expand(len(c), -1, -1, -1)
        out = torch.nn.functional.grid_sample(rgb, grid, mode="bilinear", padding_mode="zeros", align_corners=True)
        return ((out - self.mean) / self.std).half()

    def locate(self, heat, centre, size):
        """Heatmaps (n, 17, H, W) -> Punkte im Bild (n, 17, 3)."""
        torch = self.torch
        n, k, h, w = heat.shape
        heat = heat.float()
        score, idx = heat.flatten(2).max(dim=2)
        px, py = (idx % w), (idx // w)
        pad = torch.nn.functional.pad(heat.reshape(n * k, 1, h, w), (5, 5, 5, 5), mode="replicate")
        blur = torch.nn.functional.conv2d(torch.nn.functional.conv2d(pad, self.taps.view(1, 1, 1, -1)), self.taps.view(1, 1, -1, 1))
        logs = torch.nn.functional.pad(torch.log(blur.clamp(0.001, 50)), (1, 1, 1, 1), mode="replicate").reshape(n, k, -1)
        base = (px + 1) + (py + 1) * (w + 2)

        def at(dx, dy):
            return logs.gather(2, (base + dx + dy * (w + 2))[..., None])[..., 0]
        i, x1, x0, y1, y0 = at(0, 0), at(1, 0), at(-1, 0), at(0, 1), at(0, -1)
        dx, dy = 0.5 * (x1 - x0), 0.5 * (y1 - y0)
        dxx, dyy = x1 - 2 * i + x0, y1 - 2 * i + y0
        dxy = 0.5 * (at(1, 1) - x1 - y1 + 2 * i - x0 - y0 + at(-1, -1))
        hess = torch.stack([torch.stack([dxx, dxy], -1), torch.stack([dxy, dyy], -1)], -2) + torch.finfo(torch.float32).eps * torch.eye(2, device="cuda")
        step = torch.linalg.solve(hess, torch.stack([dx, dy], -1)[..., None])[..., 0]
        fine = torch.stack([px, py], -1).float() - torch.nan_to_num(step, nan=0.0, posinf=0.0, neginf=0.0).clamp(-2, 2)
        c, s = torch.as_tensor(centre, device="cuda")[:, None], torch.as_tensor(size, device="cuda")[:, None]
        xy = c - s / 2 + fine * s / torch.tensor([w - 1.0, h - 1.0], device="cuda")
        return torch.cat([xy, score[..., None]], dim=-1).cpu().numpy().astype(np.float32)

    def run(self, crops, centre, size):
        torch = self.torch
        with torch.no_grad():
            heat = self.model(pixel_values=crops, dataset_index=torch.zeros(len(crops), dtype=torch.long, device="cuda")).heatmaps  # 0 = COCO
            return self.locate(heat, centre, size)

    def __call__(self, image_bgr, boxes):
        boxes = np.asarray(boxes, float).reshape(-1, 4)
        if not len(boxes):
            return np.zeros((0, 17, 3), np.float32)
        centre, size = self.regions(boxes)
        out = []
        with self.torch.no_grad():
            image = self.torch.as_tensor(image_bgr, device="cuda")
            for a in range(0, len(boxes), BATCH):
                out.append(self.run(self.crops(image, centre[a:a + BATCH], size[a:a + BATCH]), centre[a:a + BATCH], size[a:a + BATCH]))
        return np.concatenate(out)


def on_pitch(cam, lens, boxes, margin):
    """Liegt der Fußpunkt der Box auf dem Platz oder höchstens margin Meter daneben?"""
    if cam is None or not len(boxes):
        return np.ones(len(boxes), bool)
    ground, _ = veo_camera.to_ground(cam, lens, np.column_stack([(boxes[:, 0] + boxes[:, 2]) / 2, boxes[:, 3]]))
    with np.errstate(invalid="ignore"):
        return (np.abs(ground[:, 0]) < cam["pitch"]["length"] / 2 + margin) & (np.abs(ground[:, 1]) < cam["pitch"]["width"] / 2 + margin)


def main(video, det_path, camera_path=None, margin=2.0, model_dir=None, out_path=None):
    import torch
    det = json.loads(Path(det_path).read_text())
    frames = det["frames"]
    out_path = out_path or str(det_path) + ".keypoints.npz"
    cam = veo_camera.load(camera_path) if camera_path else None
    estimate = Estimator(model_dir)
    cap = cv2.VideoCapture(video)
    index = np.zeros((len(frames), 2, 2), np.int64)
    total = sum(len(fr[lens]) for fr in frames for lens in LENSES)
    kp, colour = np.zeros((total, 17, 3), np.float32), np.full(total, -2, np.int8)
    pending, waiting, count, done, began = [], 0, 0, 0, time.time()   # pending: (Zeilen in kp, Ausschnitte, Mitte, Größe, Bild)

    def flush():
        nonlocal pending, waiting, done
        if not pending:
            return
        centre, size = np.concatenate([p[2] for p in pending]), np.concatenate([p[3] for p in pending])
        found = estimate.run(torch.cat([p[1] for p in pending]), centre, size)
        a = 0
        for rows, _, _, _, image in pending:
            kp[rows] = found[a:a + len(rows)]
            for row, q in zip(rows, found[a:a + len(rows)]):
                c = torso_colour(image, q)
                colour[row] = -2 if c is None else c
            a += len(rows)
        done += len(found)
        pending, waiting = [], 0

    for fi, fr in enumerate(frames):
        ok, image = cap.read()
        if not ok:
            index[fi:] = count
            break
        h = image.shape[0] // 2
        for li, lens in enumerate(LENSES):
            boxes = np.array(fr[lens], float).reshape(-1, 6)[:, :4]
            index[fi, li] = (count, count + len(boxes))
            rows = count + np.flatnonzero(on_pitch(cam, lens, boxes, margin))
            count += len(boxes)
            if len(rows):
                lens_image = image[li * h:(li + 1) * h]
                centre, size = estimate.regions(boxes[rows - index[fi, li, 0]])
                with torch.no_grad():
                    pending.append((rows, estimate.crops(torch.as_tensor(lens_image, device="cuda"), centre, size), centre, size, lens_image))
                waiting += len(rows)
        if waiting >= BATCH:
            flush()
        if fi % 25 == 0:
            print(f"{fi + 1}/{len(frames)} Bilder, {done} Personen", end="\r", flush=True)
    flush()
    np.savez_compressed(out_path, kp=kp[:count], colour=colour[:count], index=index)
    seconds = time.time() - began
    print(f"\n{done} von {count} Personen in {len(frames)} Bildern gerechnet ({seconds:.0f} s, {done / max(seconds, 1e-9):.0f} Personen/s) -> {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video")
    parser.add_argument("detektionen")
    parser.add_argument("--kamera", help="Kameradatei aus veo_camera.py: nur Personen auf dem Platz rechnen")
    parser.add_argument("--rand", type=float, default=2.0, help="so viele Meter neben dem Platz zählen noch dazu")
    parser.add_argument("--modell", help=f"Ordner mit den ViTPose-Gewichten (Standard {MODEL_DIR})")
    parser.add_argument("--ausgabe")
    args = parser.parse_args()
    main(args.video, args.detektionen, args.kamera, args.rand, args.modell, args.ausgabe)
