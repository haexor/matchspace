#!/usr/bin/env python3
"""Baut aus dem Veo-Panorama eine Kulisse: die echte Umgebung des Platzes als Fotos auf senkrechten Flächen.

Hinter der Gegengeraden und hinter den Toren stehen im Video Zaun, Bäume und Gebäude. Der Viewer
kennt nur den Boden; alles Aufrechte fehlt ihm. Dieses Werkzeug rechnet das Hintergrundbild (Median
über die Zeit, also ohne Spieler) über das Kameramodell (tools/veo_camera.py) auf drei senkrechte
Flächen am Rand des Luftbilds: Gegengerade, linkes und rechtes Platzende. Vom Standort der Kamera
aus stimmt das Bild genau. Von anderen Standorten ist es eine flache Kulisse: Was vor der Fläche
steht (Tore, Flutlichtmasten), ist auf sie aufgemalt und verschiebt sich nicht mit. Die Kameraseite
sieht die Kamera nicht, dort gibt es keine Kulisse.

Aufruf:
    .venv/bin/python tools/veo_backdrop.py KAMERA.json VIDEO_ODER_HINTERGRUNDBILD SPIELORDNER [SPIELORDNER ...]

Der Spielordner braucht schon das Luftbild (tools/veo_ground.py): Die Flächen stehen an dessen Rand.
Schreibt SPIELORDNER/backdrop_far.webp, backdrop_left.webp, backdrop_right.webp (mit Transparenz:
Himmel ist durchsichtig) und trägt sie in meta.json unter pitch.backdrop ein:
    {"sky": "#rrggbb", "walls": [{"file", "from": [x, y], "to": [x, y], "base": z, "height": h, "open": "from"|"to"}, ...]}
from/to in Feldkoordinaten (Meter), vom Platz aus gesehen von links nach rechts; das Bild läuft
waagerecht von from nach to, senkrecht von base bis base + height. open nennt ein Ende, an dem
die Kulisse frei endet (zur Kameraseite hin); der Viewer blendet sie dort aus.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import veo_camera  # noqa: E402

HEIGHT = 24.0     # Meter, so hoch reicht die Kulisse höchstens
PX_PER_M = 16
FADE = {"left": 0.4, "right": 0.4, "far": 0.4, "near": 0.9}  # Übergang des Luftbilds in die Umgebung (Meter)


def sky_colour(image):
    """Mittlere Farbe des Himmels: helle, wenig gesättigte Pixel im oberen Bilddrittel."""
    top = image[:image.shape[0] // 3]
    hsv = cv2.cvtColor(top, cv2.COLOR_BGR2HSV)
    sky = top[(hsv[..., 2] > 170) & (hsv[..., 1] < 70)]
    if len(sky) < 500:
        return None
    return np.median(sky, axis=0)


def goal_patch(cam, start, end, w, h, side):
    """Maske der Stelle, an der das Tor dieser Platzseite auf die Fläche gemalt ist (side: -1 links, 1 rechts).

    Der Viewer stellt das Tor selbst räumlich dar; das aufgemalte stünde sonst als zweites Tor dahinter."""
    L = cam["pitch"]["length"]
    eye = cam["position"]
    x_wall = start[0]
    corners = np.array([[side * (L / 2 + dx), y, z] for dx in (0.0, 2.2) for y in (-4.1, 4.1) for z in (0.0, 2.9)])
    t = (x_wall - eye[0]) / (corners[:, 0] - eye[0])            # Strahl Kamera -> Ecke bis zur Fläche verlängern
    hit = eye[None] + (corners - eye[None]) * t[:, None]
    u = (hit[:, 1] - start[1]) / (end[1] - start[1]) * w
    v = (1 - hit[:, 2] / HEIGHT) * h
    mask = np.zeros((h, w), np.uint8)
    cv2.fillConvexPoly(mask, cv2.convexHull(np.column_stack([u, v]).astype(np.int32)), 255)
    return mask


def wall_image(cam, background, start, end, sky, goal=0):
    """Bild einer senkrechten Fläche von start nach end. Rückgabe: Bild und seine Höhe in Metern."""
    size = cam["lensSize"]
    start, end = np.asarray(start, float), np.asarray(end, float)
    w = int(round(np.linalg.norm(end - start) * PX_PER_M))
    h = int(round(HEIGHT * PX_PER_M))
    along = (np.arange(w) + 0.5) / w
    up = HEIGHT * (1 - (np.arange(h) + 0.5) / h)
    xy = start[None] + (end - start)[None] * along[:, None]
    grid = np.column_stack([np.tile(xy, (h, 1)), np.repeat(up, w)])
    toward = grid - cam["position"][None]
    toward /= np.linalg.norm(toward, axis=1, keepdims=True)
    out = np.zeros((h, w, 3), np.float32)
    total = np.zeros((h, w), np.float32)
    for li, lens in enumerate(veo_camera.LENSES):
        uv = np.nan_to_num(veo_camera.project(cam, lens, grid), nan=-1e4)
        inside = (uv[:, 0] >= 0) & (uv[:, 0] <= size[0] - 1) & (uv[:, 1] >= 0) & (uv[:, 1] <= size[1] - 1)
        # Gegenprobe: Am Rand des Bildfelds liefert das Kameramodell Pixel, die in Wahrheit woandershin blicken.
        back = veo_camera.rays(cam, lens, uv[inside])
        back /= np.linalg.norm(back, axis=1, keepdims=True)
        inside[inside] = (back * toward[inside]).sum(axis=1) > np.cos(np.radians(1.0))
        uv, inside = uv.reshape(h, w, 2), inside.reshape(h, w)
        dist = np.minimum.reduce([uv[..., 0], size[0] - 1 - uv[..., 0], uv[..., 1], size[1] - 1 - uv[..., 1]])
        weight = np.clip(np.where(inside, dist, 0), 0, 120).astype(np.float32)
        lens_image = background[li * size[1]:(li + 1) * size[1]]
        out += cv2.remap(lens_image, uv[..., 0].astype(np.float32), uv[..., 1].astype(np.float32), cv2.INTER_LINEAR).astype(np.float32) * weight[..., None]
        total += weight
    covered = total > 0
    out = (out / np.maximum(total, 1e-6)[..., None]).astype(np.uint8)
    if goal:
        out = cv2.inpaint(out, goal_patch(cam, start, end, w, h, goal) & (covered * 255).astype(np.uint8), 5, cv2.INPAINT_TELEA)
    # Oberhalb dessen, was die Kamera sieht, ist nichts bekannt: Die Fläche endet knapp darüber. In dem
    # Streifen läuft die oberste gesehene Zeile verwischt aus (der Viewer blendet ihn in den Himmel).
    rows = np.flatnonzero(covered.mean(axis=1) >= 0.5)
    top = rows[0] if len(rows) else 0
    first = np.argmax(covered, axis=0)                       # je Spalte die oberste gesehene Zeile
    first[~covered.any(axis=0)] = h - 1
    fill = out[np.minimum(first + 2, h - 1), np.arange(w)]
    smear = cv2.blur(np.repeat(fill[None], h, axis=0), (41, 1))
    soft = cv2.GaussianBlur(covered.astype(np.float32), (0, 0), 2.5)[..., None]
    out = (out * soft + smear * (1 - soft)).astype(np.uint8)
    # Himmel durchsichtig: helle, farbarme Flächen, die mit dem oberen Bildrand zusammenhängen. So steht nur die
    # Silhouette von Bäumen und Häusern vor dem Himmel des Viewers.
    hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV)
    bright = (((hsv[..., 2] > 150) & (hsv[..., 1] < 75)) | ((hsv[..., 0] > 90) & (hsv[..., 0] < 130) & (hsv[..., 2] > 150))).astype(np.uint8)  # weiß oder himmelblau
    bright[~covered] = 1
    count, label = cv2.connectedComponents(bright, connectivity=4)
    above = np.unique(label[0][bright[0] > 0])
    sky_mask = np.isin(label, above) & (bright > 0)
    alpha = cv2.GaussianBlur((~sky_mask).astype(np.float32), (0, 0), 0.8)
    extra = int((h - top) * 0.28)
    crop = max(0, top - extra)
    return np.dstack([out, (alpha * 255).astype(np.uint8)])[crop:], HEIGHT * (h - crop) / h


def main(camera_path, source, *match_dirs):
    cam = veo_camera.load(camera_path)
    L, W = cam["pitch"]["length"], cam["pitch"]["width"]
    background = cv2.imread(source) if Path(source).suffix.lower() in (".png", ".jpg", ".jpeg") else veo_camera.background(source)
    size = cam["lensSize"]
    sky = sky_colour(background[:size[1]])
    if sky is None:
        sky = sky_colour(background[size[1]:])
    if sky is None:
        sky = np.array([235.0, 225.0, 215.0])
    for match_dir in match_dirs:
        match_dir = Path(match_dir)
        meta = json.loads((match_dir / "meta.json").read_text())
        texture = meta["pitch"].get("texture")
        if not texture:
            sys.exit(f"{match_dir}: erst das Luftbild rechnen (tools/veo_ground.py)")
        m = texture["margin"]
        m = m if isinstance(m, dict) else {k: m for k in ("left", "right", "near", "far")}
        x0, x1, y0, y1 = -L / 2 - m["left"], L / 2 + m["right"], -W / 2 - m["near"], W / 2 + m["far"]
        walls = []
        for name, start, end, goal, opening in (("left", (x0, y0), (x0, y1), -1, "from"), ("far", (x0, y1), (x1, y1), 0, None), ("right", (x1, y1), (x1, y0), 1, "to")):
            image, height = wall_image(cam, background, start, end, sky, goal)
            file = f"backdrop_{name}.webp"
            cv2.imwrite(str(match_dir / file), image, [cv2.IMWRITE_WEBP_QUALITY, 88])
            (match_dir / f"backdrop_{name}.jpg").unlink(missing_ok=True)  # Stand vor der Umstellung auf WebP
            walls.append({"file": file, "from": [round(v, 3) for v in start], "to": [round(v, 3) for v in end], "base": 0.0, "height": round(height, 2)})
            if opening:
                walls[-1]["open"] = opening
            print(f"{match_dir / file}: {image.shape[1]}×{image.shape[0]}, {height:.1f} m hoch")
        meta["pitch"]["backdrop"] = {
            "sky": "#%02x%02x%02x" % tuple(int(round(c)) for c in sky[::-1]),
            "walls": walls,
            "note": "Umgebung aus dem Veo-Panorama auf senkrechten Flächen am Rand des Luftbilds (tools/veo_backdrop.py); "
                    "nur vom Kamerastandort aus genau, sonst flache Kulisse",
        }
        meta["pitch"]["texture"]["fade"] = FADE
        (match_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
