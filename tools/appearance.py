#!/usr/bin/env python3
"""Aussehen der Spieler aus dem Video: Bildmerkmale und Größe je Erkennung, nur innerhalb einer Szene.

Die Bildmerkmale kommen aus einem allgemeinen Bildmodell (DINOv2-small, Apache-2.0), das lokal unter
models/hf liegt; Bilder verlassen den Rechner nicht. Gespeichert werden nur Merkmalsvektoren und Größen je
Erkennung, keine Bilder ({det}.appearance.npz, specs/002-spieler-identitaet/contracts/appearance-cache.md).
Bei rund 55 Pixeln Spielerhöhe ist das Aussehen ein schwaches Merkmal (research.md R1): Es entscheidet beim
Verbinden nur mit, nie allein.

Aufruf (Zwischenspeicher anlegen):
    .venv/bin/python tools/appearance.py SZENENVIDEO DETEKTIONEN.json
"""
import argparse
import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parent.parent
os.environ.setdefault("HF_HOME", str(REPO / "models" / "hf"))   # Modell nur lokal, nicht eingecheckt

MODEL_ID = "facebook/dinov2-small"
WIDTH = 768                 # Pooler-Ausgabe (384) und Mittel der Bildteile (384)
CROP_W, CROP_H = 112, 224   # Ausschnitt der Box, Seitenverhältnis einer stehenden Person
EVERY = 2                   # jedes wievielte Bild
MIN_BOX_H = 20              # px: kleinere Boxen tragen kein Aussehen
MIN_CONF = 0.3              # Mindestsicherheit von Schultern und Knöcheln für die Größe
BATCH = 256
CACHE_FORMAT = 1.0
LENSES = ("left", "right")
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


@dataclass
class SceneLooks:
    """Merkmale je Erkennung: Bild, Linse, Boxnummer in der Linse, Merkmalsvektor (Länge 1), Größe in px."""
    frame: np.ndarray
    lens: np.ndarray
    box: np.ndarray
    embedding: np.ndarray
    height: np.ndarray

    def index(self) -> dict[tuple[int, int, int], int]:
        return {(int(f), int(li), int(j)): i for i, (f, li, j) in enumerate(zip(self.frame, self.lens, self.box))}


def _model_dir() -> Path:
    return Path(os.environ["HF_HOME"]) / "hub" / ("models--" + MODEL_ID.replace("/", "--"))


def load_net():
    """DINOv2-small aus dem lokalen Ordner; ohne Modell oder bei einem Fehler None (dann ohne Aussehen)."""
    try:
        import torch
        from transformers import AutoModel
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        net = AutoModel.from_pretrained(MODEL_ID, local_files_only=True).to(device).eval()
        return net, device
    except Exception as error:   # Modell fehlt, Grafikkarte belegt …: weiter nur mit Weg und Nummer
        print(f"Hinweis: kein Bildmodell für das Aussehen ({MODEL_ID} unter {_model_dir().relative_to(REPO)}): {error}. "
              "Trennen und Verbinden nur mit Laufweg und Rückennummer.", flush=True)
        return None


def describe(crops: np.ndarray, net, device) -> np.ndarray:
    """Ausschnitte (n, CROP_H, CROP_W, 3) RGB uint8 -> Merkmale (n, WIDTH), je Zeile Länge 1."""
    import torch
    out = [np.zeros((0, WIDTH), np.float32)]
    mean = torch.tensor(MEAN, device=device).view(1, 3, 1, 1)
    std = torch.tensor(STD, device=device).view(1, 3, 1, 1)
    with torch.no_grad():
        for a in range(0, len(crops), BATCH):
            x = torch.from_numpy(np.ascontiguousarray(crops[a:a + BATCH])).to(device).permute(0, 3, 1, 2).float() / 255
            y = net(pixel_values=(x - mean) / std)
            e = torch.cat([y.pooler_output, y.last_hidden_state[:, 1:].mean(1)], 1)
            out.append(torch.nn.functional.normalize(e, dim=1).cpu().numpy().astype(np.float32))
    return np.concatenate(out)


def body_height(kp: np.ndarray) -> float:
    """Schulter bis Knöchel in px (senkrecht), NaN wenn die Punkte unsicher sind."""
    if (kp[[5, 6, 15, 16], 2] < MIN_CONF).any():
        return float("nan")
    return float(kp[[15, 16], 1].mean() - kp[[5, 6], 1].mean())


def _stamp(video, det_path) -> np.ndarray:
    model = _model_dir()
    return np.array([Path(video).stat().st_mtime, Path(det_path).stat().st_mtime,
                     model.stat().st_mtime if model.exists() else 0.0, CACHE_FORMAT])


def _crop(lens_image: np.ndarray, box) -> np.ndarray | None:
    h, w = lens_image.shape[:2]
    x1, y1, x2, y2 = (int(round(v)) for v in box[:4])
    x1, y1, x2, y2 = max(x1, 0), max(y1, 0), min(x2, w), min(y2, h)
    if y2 - y1 < MIN_BOX_H or x2 <= x1:
        return None
    crop = cv2.resize(lens_image[y1:y2, x1:x2], (CROP_W, CROP_H), interpolation=cv2.INTER_CUBIC)
    return crop[:, :, ::-1]   # BGR -> RGB


def read_scene(video: str | Path, det_path: str | Path) -> SceneLooks | None:
    """Merkmale aller Erkennungen (jedes EVERY-te Bild, beide Linsen); Zwischenspeicher {det}.appearance.npz.

    Liest das Video einmal. Ohne Bildmodell None."""
    cache = Path(f"{det_path}.appearance.npz")
    stamp = _stamp(video, det_path)
    if cache.exists():
        with np.load(cache) as c:
            if np.array_equal(c["stamp"], stamp):
                return SceneLooks(c["frame"], c["lens"], c["box"], c["embedding"], c["height"])
    model = load_net()
    if model is None:
        return None
    det = json.loads(Path(det_path).read_text())
    with np.load(f"{det_path}.keypoints.npz") as k:
        kp, index = k["kp"], k["index"]
    crops, meta = [], []
    cap = cv2.VideoCapture(str(video))
    half = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) // 2
    f = 0
    while f < len(det["frames"]):
        ok, image = cap.read()
        if not ok:
            break
        if f % EVERY == 0:
            for li, name in enumerate(LENSES):
                lens_image = image[li * half:(li + 1) * half]
                a = index[f, li, 0]
                for j, box in enumerate(det["frames"][f][name]):
                    crop = _crop(lens_image, box)
                    if crop is not None:
                        crops.append(crop)
                        meta.append((f, li, j, body_height(kp[a + j])))
        f += 1
    cap.release()
    net, device = model
    embedding = describe(np.array(crops, np.uint8).reshape(-1, CROP_H, CROP_W, 3), net, device)
    m = np.array(meta, np.float64).reshape(-1, 4)
    out = SceneLooks(m[:, 0].astype(np.int32), m[:, 1].astype(np.int8), m[:, 2].astype(np.int32),
                     embedding.astype(np.float16), m[:, 3].astype(np.float32))
    np.savez_compressed(cache, frame=out.frame, lens=out.lens, box=out.box, embedding=out.embedding,
                        height=out.height, stamp=stamp)
    return out


def metres_per_pixel(cam, lens: int, ground: np.ndarray) -> np.ndarray:
    """Meter je Pixel in der Senkrechten an Bodenpunkten (n, 2) einer Linse."""
    name = LENSES[lens]
    foot = np.column_stack([ground, np.zeros(len(ground))])
    import veo_camera
    dv = np.abs(veo_camera.project(cam, name, foot + [0, 0, 1.0])[:, 1] - veo_camera.project(cam, name, foot)[:, 1])
    return 1.0 / np.where(dv > 0, dv, np.nan)


def piece_features(scene: SceneLooks, where: Mapping[tuple[int, int, int], int], frames: Mapping[int, np.ndarray],
                   cam, lo: int | None = None, hi: int | None = None) -> tuple[np.ndarray | None, int, float]:
    """Gemittelte Merkmale (Länge 1), Zahl der Erkennungen und Größe Schulter–Knöchel in m (Median) eines
    Spurstücks; nur Bilder lo <= f < hi. Zeilen wie aus track_players: Lage r[:2], Linse r[3], Boxnummer r[8]."""
    rows, ground, lens = [], [], []
    for f, r in frames.items():
        if (lo is not None and f < lo) or (hi is not None and f >= hi):
            continue
        i = where.get((int(f), int(r[3]), int(r[8])))
        if i is not None:
            rows.append(i)
            ground.append(r[:2])
            lens.append(int(r[3]))
    if not rows:
        return None, 0, float("nan")
    rows, ground, lens = np.array(rows), np.array(ground, float), np.array(lens)
    mean = scene.embedding[rows].astype(np.float32).mean(0)
    mean /= max(float(np.linalg.norm(mean)), 1e-9)
    metres = np.full(len(rows), np.nan)
    for li in (0, 1):
        m = lens == li
        if m.any() and cam is not None:
            metres[m] = scene.height[rows[m]] * metres_per_pixel(cam, li, ground[m])
    height = float(np.nanmedian(metres)) if np.isfinite(metres).any() else float("nan")
    return mean, len(rows), height


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video")
    ap.add_argument("det")
    args = ap.parse_args(argv)
    scene = read_scene(args.video, args.det)
    if scene is not None:
        print(f"{len(scene.frame)} Erkennungen beschrieben, Größe bei {np.isfinite(scene.height).mean():.0%} sicher")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    main()
