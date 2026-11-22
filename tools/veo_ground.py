#!/usr/bin/env python3
"""Rechnet aus dem Veo-Panorama ein Luftbild des Platzes (Rasen, Linien, Umgebung am Boden).

Jeder Punkt des Bodens wird über das Kameramodell (tools/veo_camera.py) im Video
nachgeschlagen. Über viele Bilder wird je Punkt der Median genommen, dadurch verschwinden
Spieler und Ball. Alles, was nicht am Boden liegt (Tore, Banden, Zuschauer), erscheint
verzerrt umgeklappt; deshalb wird nur ein schmaler Rand um das Feld mitgenommen: bis etwa zum
Zaun, an dem die Kulisse aus tools/veo_backdrop.py steht. Auf der Gegenseite ist das Bild
unscharf, weil die Kamera dort nur wenige Pixel pro Meter liefert.

Aufruf:
    .venv/bin/python tools/veo_ground.py KAMERA.json VIDEO SPIELORDNER [SPIELORDNER ...]

Schreibt SPIELORDNER/ground.jpg und trägt das Bild in meta.json unter pitch.texture ein
(margin: Rand je Seite in Metern; left/right sind die Platzenden, far die Gegengerade, near die Kameraseite).
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import veo_camera  # noqa: E402

MARGIN = {"left": 3.5, "right": 3.5, "far": 2.0, "near": 1.6}  # Meter Rand um das Feld, je Seite
PX_PER_M = 28
SAMPLES = 31      # Bilder, über die der Median läuft


def sharpen_lines(ground, inside):
    """Macht die weißen Linien des Luftbilds schmaler und heller, ohne sie zu verschieben.

    Auf der Gegenseite sind die Linien einen halben Meter breit verwischt und entsprechend blass. Hier wird
    je Pixel der Weißanteil bestimmt (hell in allen Farbkanälen, gegenüber dem Rasen ringsum) und sein
    Querschnitt zugespitzt: Anteil im Verhältnis zum Höchstwert der Umgebung, hoch gamma, und der Höchstwert
    selbst angehoben. Die Linie bleibt, wo das Video sie zeigt; bewusst kein Neuzeichnen aus Normmaßen, denn
    die Spieler stehen relativ zu den Linien des Videos. Gelbe Kleinfeldlinien bleiben unberührt.
    inside: Maske der Fläche, in der Linien bearbeitet werden."""
    gamma, peak = 4.0, 0.9
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(1.6 * PX_PER_M) | 1,) * 2)
    grass = cv2.morphologyEx(ground, cv2.MORPH_OPEN, kernel).astype(np.float32)   # Bild ohne schmale helle Bänder
    span = np.maximum(235.0 - grass, 1.0)
    share = np.clip(((ground - grass) / span).min(axis=2), 0, 1)                   # Weißanteil je Pixel
    share[~inside] = 0
    share = cv2.GaussianBlur(share, (0, 0), 0.11 * PX_PER_M)   # glättet das Perlen entlang der Linie
    top = cv2.dilate(share, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (int(0.7 * PX_PER_M) | 1,) * 2))
    top = cv2.GaussianBlur(top, (0, 0), 0.15 * PX_PER_M)
    is_line = np.clip((top - 0.08) / 0.08, 0, 1)                                    # schwaches Rauschen bleibt, wie es ist
    with np.errstate(divide="ignore", invalid="ignore"):
        thin = np.where(top > 1e-3, np.clip(share / top, 0, 1) ** gamma, 0) * np.maximum(top, peak)
    new = share + (thin - share) * is_line
    return np.clip(ground + (new - share)[..., None] * span, 0, 255).astype(np.uint8)


def main(camera_path, video, *match_dirs):
    cam = veo_camera.load(camera_path)
    size, L, W = cam["lensSize"], cam["pitch"]["length"], cam["pitch"]["width"]
    xs = np.arange(-L / 2 - MARGIN["left"], L / 2 + MARGIN["right"], 1 / PX_PER_M) + 0.5 / PX_PER_M
    ys = np.arange(W / 2 + MARGIN["far"], -W / 2 - MARGIN["near"], -1 / PX_PER_M) - 0.5 / PX_PER_M  # Zeile 0 = Gegenseite
    gx, gy = np.meshgrid(xs, ys)
    grid = np.column_stack([gx.ravel(), gy.ravel(), np.zeros(gx.size)])
    maps, edge = [], []
    for li, lens in enumerate(("left", "right")):
        uv = np.nan_to_num(veo_camera.project(cam, lens, grid), nan=-1e4).reshape(len(ys), len(xs), 2)
        inside = (uv[..., 0] >= 0) & (uv[..., 0] <= size[0] - 1) & (uv[..., 1] >= 0) & (uv[..., 1] <= size[1] - 1)
        # Abstand zum Bildrand der Linse: entscheidet in der Überlappung, welche Linse gewinnt
        dist = np.minimum.reduce([uv[..., 0], size[0] - 1 - uv[..., 0], uv[..., 1], size[1] - 1 - uv[..., 1]])
        edge.append(np.where(inside, dist, -1))
        maps.append((uv[..., 0].astype(np.float32), (uv[..., 1] + li * size[1]).astype(np.float32)))
    weight = np.clip(np.stack(edge), 0, 120).astype(np.float32)
    covered = weight.sum(axis=0) > 0
    weight /= np.maximum(weight.sum(axis=0), 1e-6)

    cap = cv2.VideoCapture(video)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    stack = []
    for k in range(SAMPLES):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int((k + 0.5) * total / SAMPLES))
        ok, image = cap.read()
        if not ok:
            continue
        warped = sum(cv2.remap(image, mx, my, cv2.INTER_LINEAR).astype(np.float32) * weight[i][..., None]
                     for i, (mx, my) in enumerate(maps))
        stack.append(warped.astype(np.uint8))
        print(f"{k + 1}/{SAMPLES}", end="\r", flush=True)
    ground = np.median(np.stack(stack), axis=0).astype(np.uint8)
    # Unabgedeckte Stellen: mittlere Rasenfarbe
    ground[~covered] = np.median(ground[covered].reshape(-1, 3), axis=0)
    print(f"\n{covered.mean():.0%} der Fläche vom Video abgedeckt, Bild {ground.shape[1]}×{ground.shape[0]}")
    inside = (np.abs(gx) < L / 2 + 0.3) & (np.abs(gy) < W / 2 + 0.3)
    ground = sharpen_lines(ground, inside)
    for match_dir in match_dirs:
        match_dir = Path(match_dir)
        cv2.imwrite(str(match_dir / "ground.jpg"), ground, [cv2.IMWRITE_JPEG_QUALITY, 88])
        meta = json.loads((match_dir / "meta.json").read_text())
        fade = (meta["pitch"].get("texture") or {}).get("fade")  # von tools/veo_backdrop.py gesetzt
        meta["pitch"]["texture"] = {"file": "ground.jpg", "margin": MARGIN,
                                    "note": "Luftbild aus dem Veo-Panorama, Median über die Zeit (tools/veo_ground.py)"}
        if fade:
            meta["pitch"]["texture"]["fade"] = fade
        (match_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
        print(f"-> {match_dir / 'ground.jpg'}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
