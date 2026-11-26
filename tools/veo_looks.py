#!/usr/bin/env python3
"""Echtes Aussehen je Spieler aus dem Video: eine Textur für Trikot, Hose, Stutzen, Schuhe, Haut und Haare.

Jeder Punkt der Körperoberfläche hat eine feste Stelle in einer Kachel (128 × 128 Texel) je Spieler. Die
Oberfläche ist in Körperteile zerlegt (Rumpf, Kopf, Ober- und Unterarme, Ober- und Unterschenkel, Füße); in
jedem Teil zählt die Lage entlang der Achse (t) und der Winkel um sie herum (0 = vorn, +90° = links).

Für jedes Bild der Szene wird jede Stelle mit der gerechneten Haltung ins kalibrierte Kamerabild gelegt.
Sichtbar ist sie, wenn sie zur Kamera zeigt und kein Körper (der eigene oder ein anderer) davor liegt
(Tiefenpuffer aus allen Spielern). Damit Rasen nicht ins Trikot gerät, wird jedes Körperteil je Bild um den
Versatz zu seinen erkannten Gelenkpunkten nachgeschoben, und Bildpunkte, die wie der leere Platz
aussehen (auch Rasen im Schatten eines Spielers), zählen nicht. Gemittelt wird über alle Bilder in zwei Durchgängen (im zweiten ohne Ausreißer; mit --ausrichtung schiebt jeder weitere Durchgang jedes
Körperteil je Bild auf das bisherige Mittel, mit --guete zählen je Stelle die nahsten, frontalsten Bilder mehr);
dreht sich der Spieler, füllt sich nach und nach auch die Rückseite. Was nie zu sehen war, kommt von der
gespiegelten Seite, dann (nur Rumpf, Hose, Stutzen) vom Mittel der Mannschaft an dieser Stelle, sonst vom Mittel der Zeile des Spielers (Torwart und Schiedsrichter für sich).
Spieler, die im Video nicht zu sehen waren, tragen die Mittelkachel ihrer Mannschaft.

Grenzen: Spieler sind im Video rund 50 bis 120 Pixel hoch, die Textur ist entsprechend grob; Gesichter und
Rückennummern sind nicht zu erkennen. Licht und Schatten des Spieltags stecken in den Farben.

Aufruf (nach tools/veo_scene.py, das DETEKTIONEN.json.players.npz schreibt):
    .venv/bin/python tools/veo_looks.py SZENENVIDEO DETEKTIONEN.json KAMERA.json HINTERGRUND.png SZENENORDNER [PRÜFBILD.jpg] [--guete P] [--ausrichtung N] [--maske] [--ansichten N]

Schreibt SZENENORDNER/looks.png und den Eintrag "looks" in meta.json. web/avatar.js rechnet für jeden Punkt
des Körpermodells dieselben Koordinaten aus der Grundhaltung und liest dort die Farbe.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import check_motion  # noqa: E402
import avatar_mesh  # noqa: E402
import veo_camera  # noqa: E402

LENSES = ("left", "right")
TILE, COLUMNS = 128, 8
REF_HEIGHT = 1.70
HEAD_SHARE = 0.176       # Schulterhöhe bis Scheitel als Anteil der Körpergröße
# Körperteil: Kachelbereich (x, y, Breite = Winkel, Höhe = Achse), Bereich von t, Querschnitt (t, Halbbreite, Halbtiefe) in m bei 1,70 m
SEGMENTS = [
    ("torso", (0, 0, 64, 64), (-0.45, 1.25),
     ((-0.45, 0.13, 0.09), (-0.2, 0.16, 0.10), (0.0, 0.165, 0.10), (0.3, 0.14, 0.095), (0.6, 0.14, 0.10), (0.9, 0.16, 0.105),
      (1.05, 0.17, 0.09), (1.2, 0.09, 0.06), (1.25, 0.06, 0.05))),
    ("head", (64, 64, 64, 64), (0.0, 1.0),
     ((0.0, 0.055, 0.055), (0.25, 0.055, 0.055), (0.4, 0.075, 0.08), (0.55, 0.085, 0.095), (0.7, 0.085, 0.1), (0.85, 0.075, 0.09),
      (0.95, 0.05, 0.06), (1.0, 0.02, 0.02))),
    ("upperarm_l", (96, 0, 16, 32), (-0.1, 1.0), ((-0.1, 0.05, 0.05), (1.0, 0.04, 0.04))),
    ("upperarm_r", (112, 0, 16, 32), (-0.1, 1.0), ((-0.1, 0.05, 0.05), (1.0, 0.04, 0.04))),
    ("thigh_l", (64, 32, 16, 32), (-0.15, 1.0), ((-0.15, 0.085, 0.085), (0.0, 0.08, 0.08), (1.0, 0.055, 0.055))),
    ("thigh_r", (80, 32, 16, 32), (-0.15, 1.0), ((-0.15, 0.085, 0.085), (0.0, 0.08, 0.08), (1.0, 0.055, 0.055))),
    ("calf_l", (96, 32, 16, 32), (0.0, 1.05), ((0.0, 0.05, 0.05), (0.3, 0.055, 0.055), (1.05, 0.035, 0.035))),
    ("calf_r", (112, 32, 16, 32), (0.0, 1.05), ((0.0, 0.05, 0.05), (0.3, 0.055, 0.055), (1.05, 0.035, 0.035))),
    ("lowerarm_l", (0, 64, 16, 32), (0.0, 1.45), ((0.0, 0.04, 0.04), (1.0, 0.03, 0.03), (1.45, 0.025, 0.02))),
    ("lowerarm_r", (16, 64, 16, 32), (0.0, 1.45), ((0.0, 0.04, 0.04), (1.0, 0.03, 0.03), (1.45, 0.025, 0.02))),
    ("foot_l", (32, 64, 16, 16), (-0.1, 1.1), ((-0.1, 0.04, 0.045), (1.1, 0.03, 0.04))),
    ("foot_r", (48, 64, 16, 16), (-0.1, 1.1), ((-0.1, 0.04, 0.045), (1.1, 0.03, 0.04))),
]
FOOT_LIFT = 0.035        # Fußachse liegt so hoch über Ferse und Spitze (m)
COCO_JOINT = {0: "nose", 5: "lShoulder", 6: "rShoulder", 7: "lElbow", 8: "rElbow", 9: "lWrist", 10: "rWrist",
              11: "lHip", 12: "rHip", 13: "lKnee", 14: "rKnee", 15: "lAnkle", 16: "rAnkle"}
MIN_CONF = 0.5
MAX_SHIFT = 10.0         # Pixel: größerer Versatz zu den Gelenkpunkten gilt als Fehlzuordnung, das Bild zählt nicht
JOINT_SHIFT = 6.0        # Pixel: so weit darf ein einzelner Gelenkpunkt vom mittleren Versatz abweichen
BG_MIN = 14.0            # Farbabstand zum leeren Platz (bester von 3 × 3 Nachbarn), unter dem ein Bildpunkt als Rasen gilt
SHADOW_TONE = 0.05       # Abstand im Farbton (Anteile von Blau, Grün, Rot), unter dem ein dunklerer Punkt als Rasen im Schatten gilt
PURE = 90.0              # Farbabstand zum leeren Platz, ab dem ein Bildpunkt als rein gilt (volles Gewicht)
OCCLUDE = 0.06           # m: so weit darf eine Stelle hinter der vordersten Fläche liegen
OUTLIER = 45.0           # Farbabstand zum Mittel aus Durchgang 1, ab dem ein Wert im zweiten Durchgang nicht zählt
ENOUGH = 0.5             # Gewicht, ab dem eine Stelle als gesehen gilt
MAX_ALIGN = 2.5          # Pixel: so weit darf ein Körperteil dabei geschoben werden
MIN_ALIGN_TEXELS = 24    # weniger sichtbare Stellen: kein Schieben
RIDGE = 0.02             # Bremse gegen große Verschiebungen (Anteil der Spur der Normalgleichung)


def unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9)


def across(v, axis):
    """Anteil von v senkrecht zu axis, Länge 1."""
    return unit(v - (v * axis).sum(-1, keepdims=True) * axis)


def grid():
    """Je Körperteil die Texelmitten: Winkel, t, und ihre Nummer in der Kachel."""
    out = []
    for name, (x, y, w, h), (t0, t1), profile in SEGMENTS:
        cols, rows = np.meshgrid(np.arange(w), np.arange(h))
        theta = (cols + 0.5) / w * 2 * np.pi - np.pi
        t = t0 + (rows + 0.5) / h * (t1 - t0)
        prof = np.array(profile)
        rx, rz = np.interp(t, prof[:, 0], prof[:, 1]), np.interp(t, prof[:, 0], prof[:, 2])
        out.append({"name": name, "theta": theta.ravel(), "t": t.ravel(), "rx": rx.ravel(), "rz": rz.ravel(),
                    "index": ((y + rows) * TILE + x + cols).ravel()})
    return out


def surface(J, n, height, cells, yaw=None):
    """Weltpunkte und Normalen (P, N, 3) aller Texel für Gelenke J (P, 20, 3). `yaw` (P,): Drehung des Rumpfs um seine Längsachse (rad),
    die die Texel gegenüber der aus den Gelenkpunkten geschätzten Ausrichtung weiterdreht (siehe fit_yaw)."""
    g = lambda name: J[:, n[name]]  # noqa: E731
    up_world = np.array([0.0, 0.0, 1.0])
    s = (height / REF_HEIGHT)[:, None]
    hip_mid, sh_mid = (g("lHip") + g("rHip")) / 2, (g("lShoulder") + g("rShoulder")) / 2
    left_h, left_s = unit(g("lHip") - g("rHip")), unit(g("lShoulder") - g("rShoulder"))
    spine = sh_mid - hip_mid
    up = unit(spine)
    chest_forward = unit(np.cross(left_s, up))
    points, normals = [], []
    for c in cells:
        name, th, t = c["name"], c["theta"][None, :], c["t"][None, :]
        rx, rz = c["rx"][None, :] * s, c["rz"][None, :] * s
        if name == "torso":
            k = np.clip(t, 0, 1)[..., None]
            left = unit(left_h[:, None] * (1 - k) + left_s[:, None] * k)
            F = unit(np.cross(left, up[:, None]))
            S = np.cross(up[:, None], F)
            centre = hip_mid[:, None] + t[..., None] * spine[:, None]
        elif name == "head":
            axis = unit(g("head") - g("neck"))
            F = across(g("nose") - g("head"), axis)[:, None]
            S = np.cross(axis, F[:, 0])[:, None]
            centre = sh_mid[:, None] + (t * HEAD_SHARE * height[:, None])[..., None] * axis[:, None]
        else:
            part, side = name.split("_")
            L = "l" if side == "l" else "r"
            a, b = {"upperarm": ("Shoulder", "Elbow"), "lowerarm": ("Elbow", "Wrist"), "thigh": ("Hip", "Knee"),
                    "calf": ("Knee", "Ankle"), "foot": ("Heel", "Toe")}[part]
            A, B = g(L + a), g(L + b)
            if part == "foot":
                A, B = A + FOOT_LIFT * s * up_world, B + FOOT_LIFT * s * up_world
            axis = unit(B - A)
            if part in ("upperarm", "lowerarm"):
                F = across(chest_forward, axis)
                S = np.cross(F, axis)
            else:
                S = across(left_h, axis)
                F = np.cross(axis, S)
            F, S = F[:, None], S[:, None]
            centre = A[:, None] + t[..., None] * (B - A)[:, None]
        if name == "torso" and yaw is not None:
            th = th + yaw[:, None]
        # th ist der Polarwinkel um die Achse (nicht der Parameter der Ellipse): so liest ihn der Viewer (web/avatar-look.js, atan2 der Netzpunkte um die
        # Achse). Mit dem Ellipsenparameter säße ein Merkmal (z. B. die Nummer) im Viewer um rz/rx verschoben und verzerrt.
        cos, sin = np.cos(th)[..., None], np.sin(th)[..., None]
        rho = 1.0 / np.sqrt((cos / rz[..., None]) ** 2 + (sin / rx[..., None]) ** 2)
        x, y = rho * cos, rho * sin
        points.append(centre + x * F + y * S)
        normals.append(unit(x / rz[..., None] ** 2 * F + y / rx[..., None] ** 2 * S))
    return np.concatenate(points, axis=1), np.concatenate(normals, axis=1)


# Je Körperteil: an welchen Gelenkpunkten er ausgerichtet wird (Anfang, Ende) und bei welchem t das Ende erreicht ist
ANCHORS = {"torso": (("lHip", "rHip"), ("lShoulder", "rShoulder"), 1.0), "head": (("lShoulder", "rShoulder"), ("nose",), 0.6),
           "upperarm": (("Shoulder",), ("Elbow",), 1.0), "lowerarm": (("Elbow",), ("Wrist",), 1.0),
           "thigh": (("Hip",), ("Knee",), 1.0), "calf": (("Knee",), ("Ankle",), 1.0), "foot": (("Ankle",), ("Ankle",), 1.0)}
COCO_ORDER = list(COCO_JOINT)
JOINT_SLOT = {COCO_JOINT[c]: k for k, c in enumerate(COCO_ORDER)}


def anchor_weights(cells):
    """Matrix (Texel, 13): Anteil jedes Gelenkpunkts am Versatz eines Texels."""
    rows = []
    for c in cells:
        part, _, side = c["name"].partition("_")
        a, b, reach = ANCHORS[part]
        name = lambda j: j if not side else side + j  # noqa: E731
        m = np.zeros((len(c["t"]), len(COCO_ORDER)))
        w = np.clip(c["t"] / reach, 0, 1)
        for j in a:
            m[:, JOINT_SLOT[name(j)]] += (1 - w) / len(a)
        for j in b:
            m[:, JOINT_SLOT[name(j)]] += w / len(b)
        rows.append(m)
    return np.concatenate(rows)


def running(values, half=2):
    """Gleitender Median über die Zeit (Achse 0), NaN zählt nicht."""
    out = np.full_like(values, np.nan)
    for f in range(len(values)):
        win = values[max(0, f - half):f + half + 1]
        ok = ~np.isnan(win[..., 0])
        cnt = ok.sum(axis=0)
        med = np.nanmedian(np.where(ok[..., None], win, np.nan), axis=0) if ok.any() else out[f]
        out[f] = np.where((cnt >= 2)[..., None], med, values[f])
    return out


def shifts(cam, kp, lens, J, n):
    """Versatz (T, 13, 2) je Bild und Gelenkpunkt zwischen Erkennung und gerechnetem Skelett, in der Linse der Erkennung.
    Unsichere oder abweichende Punkte nehmen den Median des Bilds; NaN = Bild unbrauchbar."""
    T = len(kp)
    out = np.full((T, len(COCO_ORDER), 2), np.nan)
    joints = [n[COCO_JOINT[c]] for c in COCO_ORDER]
    for li, lens_name in enumerate(LENSES):
        frames = np.flatnonzero(lens == li)
        if not len(frames):
            continue
        uv = veo_camera.project(cam, lens_name, J[frames][:, joints].reshape(-1, 3)).reshape(len(frames), len(joints), 2)
        diff = kp[frames][:, COCO_ORDER, :2] - uv
        good = (np.nan_to_num(kp[frames][:, COCO_ORDER, 2]) >= MIN_CONF) & ~np.isnan(diff[..., 0])
        for k, f in enumerate(frames):
            if good[k].sum() < 4:
                continue
            med = np.median(diff[k][good[k]], axis=0)
            if np.linalg.norm(med) > MAX_SHIFT:
                continue
            ok = good[k] & (np.linalg.norm(diff[k] - med, axis=1) < JOINT_SHIFT)
            out[f] = np.where(ok[:, None], diff[k], med)
    return running(out)


def grass(colour, background, uv):
    """Welche Bildpunkte wie der leere Platz aussehen: fast gleich (bester von 3 × 3 Nachbarn) oder gleicher
    Farbton, nur dunkler (Schatten eines Spielers auf dem Rasen). Dazu der Farbabstand zum leeren Platz."""
    chroma = colour / (colour.sum(axis=1, keepdims=True) + 1)
    near, tone, light = np.full(len(colour), np.inf), np.full(len(colour), np.inf), np.zeros(len(colour))
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            bg = sample(background, uv + (dx, dy))
            near = np.minimum(near, np.linalg.norm(colour - bg, axis=1))
            d = np.linalg.norm(chroma - bg / (bg.sum(axis=1, keepdims=True) + 1), axis=1)
            better = d < tone
            tone[better], light[better] = d[better], (colour.sum(axis=1) / (bg.sum(axis=1) + 1))[better]
    return (near < BG_MIN) | ((tone < SHADOW_TONE) & (light > 0.25) & (light < 1.15)), near


def sample(image, uv):
    """Bilineare Farbe (N, 3) an Pixeln uv (N, 2) eines Bilds (H, W, 3)."""
    h, w = image.shape[:2]
    x, y = np.clip(uv[:, 0] - 0.5, 0, w - 1.001), np.clip(uv[:, 1] - 0.5, 0, h - 1.001)
    x0, y0 = x.astype(int), y.astype(int)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    at = lambda yy, xx: image[yy, xx].astype(np.float32)  # noqa: E731
    return at(y0, x0) * (1 - fx) * (1 - fy) + at(y0, x0 + 1) * fx * (1 - fy) + at(y0 + 1, x0) * (1 - fx) * fy + at(y0 + 1, x0 + 1) * fx * fy


MASK_PAD = 24   # Pixel Umgebung um den Spieler für die Personenmaske (die Nachbarn müssen im Ausschnitt sein, damit die Maske sie trennt)


def segmenter():
    """Segmentierungsmodell für Personenmasken (models/yolo11x-seg.pt)."""
    from ultralytics import YOLO
    return YOLO(str(Path(__file__).parent.parent / "models" / "yolo11x-seg.pt"))


def person_masks(model, crops, uvs, scale=3):
    """Personenmaske je Ausschnitt (BGR) mit den sichtbaren Stellen des Spielers uvs (N, 2 in Ausschnittskoordinaten): bool-Bild in der Größe des
    Ausschnitts, einen Pixel verbreitert (dünne Arme fallen sonst am Rand weg), von der Person, in der die meisten Stellen liegen; None, wenn
    weniger als 30 % der Stellen in einer Person liegen. Im Zweikampf liegen viele Stellen eines Spielers auf dem Gegner."""
    out = [None] * len(crops)
    if not crops:
        return out
    big = [cv2.resize(c, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC) for c in crops]
    results = model.predict(big, classes=[0], imgsz=640, conf=0.15, retina_masks=True, verbose=False)
    for i, (crop, uv, r) in enumerate(zip(crops, uvs, results)):
        if r.masks is None or not len(r.masks.data):
            continue
        masks = r.masks.data.cpu().numpy() > 0.5
        ui = np.clip((uv[:, 0] * scale).astype(int), 0, masks.shape[2] - 1)
        vi = np.clip((uv[:, 1] * scale).astype(int), 0, masks.shape[1] - 1)
        score = masks[:, vi, ui].mean(axis=1)
        best = int(score.argmax())
        if score[best] >= 0.3:
            small = cv2.resize(masks[best].astype(np.uint8), (crop.shape[1], crop.shape[0]), interpolation=cv2.INTER_AREA) > 0
            out[i] = cv2.dilate(small.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    return out


def in_mask(entry, uv):
    """Welche Bildpunkte uv (N, 2) in der Maske eines Spielers liegen (entry = (x0, y0, Maske) aus `person_masks`; None = keine Maske: alle)."""
    if entry is None:
        return np.ones(len(uv), bool)
    x0, y0, mask = entry
    h, w = mask.shape
    return mask[np.clip(np.round(uv[:, 1] - y0 - 0.5).astype(int), 0, h - 1), np.clip(np.round(uv[:, 0] - x0 - 0.5).astype(int), 0, w - 1)]


VIEW_OUTLIER = {"torso": 400.0, "head": 110.0}   # Farbabstand zum gewöhnlichen Mittel, ab dem ein Wert in der Ansichtentextur nicht zählt. Rumpf praktisch aus: weißer Aufdruck auf
                                                 # rotem Trikot liegt 150 bis 300 vom unscharfen Mittel, ein engerer Filter (45, 110) ließ von der Nummer nur die Mitte stehen (schmal
                                                 # und hoch). Kopf eng: ohne Filter färben Fremdfarben aus dem Zweikampf ihn (Mannschaftsfarbe im Gesicht).
VIEW_PARTS = ("torso", "head")   # Körperteile mit Ansichtentextur; dünne Teile (Arme, Beine, Füße) bleiben beim Mittel: ein einzelnes Bild liegt dort oft ein paar Pixel daneben
VIEW_DEPTH = 3         # so viele Bilder je Körperteil und Ansicht dürfen Lücken des besten Bilds füllen


def tile_geometry():
    """Je Texel der Kachel: Nummer des Körperteils (-1 = unbenutzt) und Winkelanteil um dessen Achse (0 bis 1; 0,5 = vorn)."""
    part = np.full(TILE * TILE, -1)
    frac = np.zeros(TILE * TILE)
    for s, (_, (x, y, w, h), _, _) in enumerate(SEGMENTS):
        rows, cols = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
        at = ((y + rows) * TILE + x + cols).ravel()
        part[at], frac[at] = s, ((cols + 0.5) / w).ravel()
    return part, frac


def view_texture(texel, colour, weight, quality, obs, nobs, sectors=4, depth=VIEW_DEPTH, outlier=None):
    """Textur eines Spielers aus zusammenhängenden Bildern je Ansicht statt aus dem Mittel aller Bilder.
    Das gemittelte Bild ist unschärfer als jedes einzelne, weil dasselbe Texel in verschiedenen Bildern leicht verschiedene echte Stellen trifft
    (Rumpfdrehung, Stoff, Fehler der Haltung); ein einzelnes Bild verzerrt dagegen glatt und bleibt scharf (Ziffern und Schriftzüge sind zu lesen).
    Je Körperteil und Ansicht (`sectors` gleich große Winkelbereiche um die Achse, weich überblendet) liefert das Bild mit der besten Güte
    (nah, frontal, viele Stellen) alle seine Texel; fehlt dort eines, kommt es vom nächstbesten (bis `depth` Bilder).
    Eingabe je Beobachtung: Texel in der Kachel (N,), Farbe (N, 3), Gewicht (N,), Güte (N,), Nummer des Bilds (N,) von 0 bis nobs - 1.
    Rückgabe: Farben (TILE², 3) und Gewicht der gesehenen Stellen (TILE²; Stellen ohne Wert haben Gewicht 0 und Farbe 0)."""
    size = TILE * TILE
    wsum = np.bincount(texel, weight, minlength=size)
    ref = np.stack([np.bincount(texel, weight * colour[:, ch], minlength=size) for ch in range(3)], axis=1) / np.maximum(wsum, 1e-9)[:, None]
    part, frac = tile_geometry()
    in_view = np.isin(part, [i for i, sg in enumerate(SEGMENTS) if sg[0] in VIEW_PARTS])   # (Texel,): Ansichtentextur statt Mittel
    # Mittel der übrigen Teile: ohne Ausreißer (wie bisher, OUTLIER), die Ansichten dagegen mit lockerem Filter
    limits = VIEW_OUTLIER if outlier is None else {name: outlier for name in VIEW_PARTS}
    limit = np.full(size, OUTLIER)
    for k, sg in enumerate(SEGMENTS):
        if sg[0] in VIEW_PARTS:
            limit[part == k] = limits[sg[0]]
    keep = np.linalg.norm(colour - ref[texel], axis=1) < limit[texel]
    mean_w = weight * keep
    mean_sum = np.stack([np.bincount(texel, mean_w * colour[:, ch], minlength=size) for ch in range(3)], axis=1)
    seen = np.bincount(texel, mean_w, minlength=size)
    mean = mean_sum / np.maximum(seen, 1e-9)[:, None]
    weight = mean_w
    centre = 0.5 + np.arange(sectors) / sectors
    dist = np.abs((frac[None, :] - centre[:, None] + 0.5) % 1.0 - 0.5)
    blend = np.where(dist < 1.0 / sectors, np.cos(np.pi * dist * sectors / 2) ** 2, 0.0)   # (Ansicht, Texel); Summe über die Ansichten = 1
    groups = len(SEGMENTS) * sectors
    score = np.zeros(groups * nobs)
    for k in range(sectors):
        score += np.bincount((part[texel] * sectors + k) * nobs + obs, blend[k, texel] * weight * quality, minlength=groups * nobs)
    score = score.reshape(groups, nobs)
    order = np.argsort(-score, axis=1)[:, :depth]
    field, have = np.zeros((sectors, size, 3)), np.zeros((sectors, size), bool)
    for r in range(order.shape[1]):
        for k in range(sectors):
            g = part[texel] * sectors + k
            take = (obs == order[g, r]) & (score[g, order[g, r]] > 0) & (blend[k, texel] > 0) & (weight > 0) & ~have[k, texel]
            field[k, texel[take]] = colour[take]
            have[k, texel[take]] = True
    mix = blend * have
    total = mix.sum(axis=0)
    out = np.einsum("kt,ktc->tc", mix, field) / np.maximum(total, 1e-9)[:, None]
    return np.where((in_view & (total > 0))[:, None], out, mean), seen


def frame_masks(model, observed):
    """Personenmasken der Spieler eines Bilds (Ausgabe von observe): Liste von (x0, y0, Maske) oder None je Beobachtung."""
    boxes = []
    for o in observed:
        x0, y0 = np.maximum(np.floor(o["uv"].min(axis=0) - MASK_PAD), 0).astype(int)
        x1, y1 = np.ceil(o["uv"].max(axis=0) + MASK_PAD + 1).astype(int)
        boxes.append((x0, y0, o["image"][y0:y1, x0:x1]))
    found = person_masks(model, [b[2] for b in boxes], [o["uv"] - b[:2] for o, b in zip(observed, boxes)])
    return [None if m is None else (b[0], b[1], m) for b, m in zip(boxes, found)]


def gradient(image, uv):
    """Farbe (N, 3) und ihre Ableitung nach x und y (N, 3) an den Bildpunkten uv."""
    c = sample(image, uv)
    gx = sample(image, uv + (0.5, 0)) - sample(image, uv - (0.5, 0))
    gy = sample(image, uv + (0, 0.5)) - sample(image, uv - (0, 0.5))
    return c, gx, gy


def solve_shift(res, gx, gy, w, ridge):
    """Verschiebung d (2,) in Pixeln, die sum w * |res + d_x gx + d_y gy|² klein macht (res = Farbe - Bezug); die Bremse zieht zu 0."""
    a = np.array([[np.sum(w[:, None] * gx * gx), np.sum(w[:, None] * gx * gy)], [np.sum(w[:, None] * gx * gy), np.sum(w[:, None] * gy * gy)]])
    b = -np.array([np.sum(w[:, None] * gx * res), np.sum(w[:, None] * gy * res)])
    lam = ridge * np.trace(a) + 1e-6
    return np.clip(np.linalg.solve(a + lam * np.eye(2), b), -MAX_ALIGN, MAX_ALIGN)


def align(image, uv, seg, weight, ref, ok, passes=2):
    """Verschiebung (N, 2) der sichtbaren Stellen eines Spielers in einem Bild, damit sein Bild zum bisherigen Mittel `ref` (N, 3 je Stelle) passt:
    erst der ganze Körper, dann jedes Körperteil für sich (stärker gebremst). `ok`: Stellen, deren Bezug verlässlich ist; `seg`: Körperteil je Stelle.
    Die Gelenkpunkte (shifts) sind nur auf etwa 1 bis 2 Pixel genau; das Rest-Verwischen im Mittel kommt daher."""
    shift = np.zeros((len(uv), 2))
    wt = weight * ok
    if ok.sum() < MIN_ALIGN_TEXELS:
        return shift
    body, part = np.zeros(2), np.zeros((len(SEGMENTS), 2))
    for _ in range(passes):
        c, gx, gy = gradient(image, uv + body)
        good = ok & (np.linalg.norm(c - ref, axis=1) < OUTLIER)
        if good.sum() >= MIN_ALIGN_TEXELS:
            body = np.clip(body + solve_shift(c[good] - ref[good], gx[good], gy[good], wt[good], RIDGE), -MAX_ALIGN, MAX_ALIGN)
        c, gx, gy = gradient(image, uv + body + part[seg])
        good = ok & (np.linalg.norm(c - ref, axis=1) < OUTLIER)
        for k in range(len(part)):
            m = good & (seg == k)
            if m.sum() >= MIN_ALIGN_TEXELS:
                part[k] = np.clip(part[k] + solve_shift(c[m] - ref[m], gx[m], gy[m], wt[m], RIDGE * 5), -MAX_ALIGN, MAX_ALIGN)
    return body + part[seg]


def load_scene(video, det_path, camera_path, background_path, scene_dir, mesh_path=None):
    """Alles, was ein Durchlauf über die Bilder der Szene braucht: Kamera, Spieler mit Gelenkpunkten im Video (sie
    bekommen eine Textur) und alle übrigen Figuren (sie verdecken nur), Gelenke in Weltkoordinaten."""
    scene_dir = Path(scene_dir)
    cam = veo_camera.load(camera_path)
    det = json.loads(Path(det_path).read_text())
    meta, _, pos, present, (joints, names, slots, _) = check_motion.load(scene_dir)
    own_tracking = "eigenes Tracking" in meta.get("source", {}).get("notes", "")   # Szene ohne Veo (tools/veo_scene.py mit "-")
    views = np.load(f"{det_path}.players{'_own' if own_tracking else ''}.npz")
    n = {name: i for i, name in enumerate(names)}
    entities = meta["entities"]
    W, H = cam["lensSize"]
    cells = grid()
    players, others = [], []
    for slot, entity in enumerate(slots):
        e = entities[entity]
        here = present[:, entity]
        if not here.any():
            continue
        world = joints[:, slot].astype(float).copy()
        world[..., :2] += pos[:, entity, None, :2]
        world[~here] = np.nan
        legs = np.linalg.norm(world[:, n["lHip"]] - world[:, n["lKnee"]], axis=-1) + np.linalg.norm(world[:, n["lKnee"]] - world[:, n["lAnkle"]], axis=-1)
        height = float(np.nanmedian(legs)) / 0.5   # Bein (Hüfte bis Knöchel) rund halbe Körpergröße
        if f"{e['id']}.kp" not in views:
            others.append({"world": world, "height": height, "here": here})
            continue
        kp, lens, down = views[f"{e['id']}.kp"], views[f"{e['id']}.lens"], views[f"{e['id']}.down"]
        lens = np.where(np.isnan(lens), -1, lens).astype(int)
        shift = shifts(cam, kp, lens, world, n)
        usable = here & ~np.isnan(shift[:, 0, 0]) & ~down
        players.append({"id": e["id"], "entity": entity, "team": e["team"], "group": e["team"] + ("-gk" if e.get("role") == "goalkeeper" else ""),
                        "world": world, "height": height, "lens": lens, "shift": shift, "usable": usable})
    return {"video": video, "cam": cam, "det": det, "meta": meta, "present": present, "n": n, "W": W, "H": H,
            "total": meta["frames"], "ratio": det["fps"] / meta["fps"],
            "background": cv2.imread(str(background_path)).astype(np.float32),
            "cells": cells, "index": np.concatenate([c["index"] for c in cells]), "anchor": anchor_weights(cells),
            "segment": np.concatenate([np.full(len(c["t"]), s) for s, c in enumerate(cells)]),
            "players": players, "others": others,
            "mesh": avatar_mesh.AvatarMesh(mesh_path, SEGMENTS, TILE) if mesh_path else None}


def frames(sc):
    """Die Bilder der Szene (Nummer f der Bewegungsdaten, Videobild), einmal von vorn bis hinten."""
    cap = cv2.VideoCapture(str(sc["video"]))
    frame_no, image = -1, None
    for f in range(sc["total"]):
        want = min(int(round(f * sc["ratio"])), len(sc["det"]["frames"]) - 1)
        while frame_no < want:
            ok, image = cap.read()
            frame_no += 1
            if not ok:
                break
        if image is None:
            break
        yield f, image
    cap.release()


YAW_SPAN = np.deg2rad(40.0)    # so weit darf der Rumpf je Bild gegenüber der Schätzung aus den Gelenkpunkten gedreht werden
YAW_STEP = np.deg2rad(8.0)
YAW_PRIOR = 4.0                # Farbabstand, den eine Drehung um die ganze Spanne kostet (Bremse bei unklarem Bild)
YAW_ERR_CAP = 80.0             # einzelne Abweichungen zählen höchstens so viel (Verdeckung, Rasen am Rand)
YAW_MIN_TEXELS = 150


def best_yaw(sc, f, image, a, fit):
    """Drehung des Rumpfs von Spieler a in Bild f (rad), bei der die Farben der Rumpftexel im Bild am besten zum Bezug passen.
    `fit` = (Farben (P, Kachel², 3), gesehen (P, Kachel²)). Die Haltung aus den Gelenkpunkten liegt bei Drehungen um 20 bis 30° daneben,
    das ist so viel wie der Rückenaufdruck breit ist. Rechnet nur den Rumpf: Gitter mit YAW_STEP, dann Feinsuche."""
    p, n, cam, H = sc["players"][a], sc["n"], sc["cam"], sc["H"]
    li = int(p["lens"][f])
    if li < 0:   # kein Gelenkpunkt-Bezug in diesem Bild: Haltung bleibt
        return 0.0
    lens_name = LENSES[li]
    lens_image = image[li * H:(li + 1) * H]
    torso = sc["cells"][0]
    texel = torso["index"]
    ref, seen = fit[0][a][texel], fit[1][a][texel]
    if seen.sum() < YAW_MIN_TEXELS:
        return 0.0
    J, height = p["world"][f][None], np.array([p["height"]])
    centre = cam["lenses"][lens_name]["centre"]
    shift = sc["anchor"][:len(texel)] @ p["shift"][f]

    def cost(d):
        pts, nrm = surface(J, n, height, sc["cells"][:1], np.array([d]))
        view = centre - pts[0]
        dist = np.linalg.norm(view, axis=-1)
        facing = (nrm[0] * view).sum(-1) / dist
        uv = veo_camera.project(cam, lens_name, pts[0]) + shift
        ok = seen & (facing > 0.3) & (uv[:, 0] >= 1) & (uv[:, 0] < sc["W"] - 2) & (uv[:, 1] >= 1) & (uv[:, 1] < H - 2)
        if ok.sum() < YAW_MIN_TEXELS:
            return np.inf
        err = np.minimum(np.linalg.norm(sample(lens_image, uv[ok]) - ref[ok], axis=1), YAW_ERR_CAP)
        return float((err * facing[ok]).sum() / facing[ok].sum()) + YAW_PRIOR * (d / YAW_SPAN) ** 2

    grid_ = np.arange(-YAW_SPAN, YAW_SPAN + 1e-9, YAW_STEP)
    costs = [cost(d) for d in grid_]
    d = float(grid_[int(np.argmin(costs))])
    if not np.isfinite(min(costs)):
        return 0.0
    fine = [d - YAW_STEP / 2, d + YAW_STEP / 2]
    fc = [cost(x) for x in fine]
    return float(([d] + fine)[int(np.argmin([min(costs)] + fc))])


def fit_yaw(sc, rounds=2, began=None):
    """Drehung des Rumpfs je Bild und Spieler: {(f, Spieler): rad}. Runde 0 mittelt die Bilder wie gewohnt; in jeder weiteren Runde wird je Bild die
    Drehung gesucht, bei der der Rumpf am besten zum bisherigen Mittel passt, und das Mittel damit neu gebildet (es wird dabei schärfer)."""
    players, index = sc["players"], sc["index"]
    P, size = len(players), len(players) * TILE * TILE
    table, ref = {}, None
    for r in range(rounds + 1):
        sums, wsum = np.zeros((size, 3)), np.zeros(size)
        new = {}
        for f, image in frames(sc):
            fit = None if r == 0 else (ref[0].reshape(P, TILE * TILE, 3), ref[1].reshape(P, TILE * TILE))
            for o in observe(sc, f, image, yaw=new, fit=fit):
                texel = o["player"] * TILE * TILE + index[o["cell"]]
                w = o["weight"] * (1.0 if r == 0 else (np.linalg.norm(o["colour"] - ref[0][texel], axis=1) < 80.0))
                for ch in range(3):
                    sums[:, ch] += np.bincount(texel, w * o["colour"][:, ch], minlength=size)
                wsum += np.bincount(texel, w, minlength=size)
        ref = (sums / np.maximum(wsum, 1e-9)[:, None], wsum >= ENOUGH)
        table = new
        if r:
            d = np.degrees(np.array(list(table.values())))
            print(f"  Drehung Runde {r}: Mittel {d.mean():+.1f}°, Streuung {d.std():.1f}°, im Betrag über 20°: {np.mean(np.abs(d) > 20):.0%}"
                  + (f" [{time.time() - began:.0f} s]" if began else ""), flush=True)
    return table


def observe(sc, f, image, only=None, yaw=None, fit=None):
    """Was Bild f über die Oberfläche der Spieler verrät: je Spieler (nur `only`, sonst alle mit brauchbarer Ausrichtung)
    die sichtbaren Stellen ("cell" = Nummer in der Reihenfolge von grid()), ihre Bildpunkte uv, Farben und Gewichte.
    Verdecken dürfen alle Figuren im Bild, auch die, deren Farben in diesem Bild nicht zählen.
    `yaw`: Tabelle {(f, Spieler): Drehung des Rumpfs (rad)} aus fit_yaw; mit `fit` (Bezugsfarben, gesehen) wird sie für dieses Bild erst bestimmt."""
    players, others, n, cells, index, anchor = sc["players"], sc["others"], sc["n"], sc["cells"], sc["index"], sc["anchor"]
    cam, W, H, background = sc["cam"], sc["W"], sc["H"], sc["background"]
    N = len(index)
    active = [k for k, p in enumerate(players) if p["usable"][f]]
    if not active:
        return []
    cover = [players[k] for k, p in enumerate(players) if p["world"][f, 0, 0] == p["world"][f, 0, 0] and not p["usable"][f]]
    cover += [o for o in others if o["here"][f]]
    bodies = [players[k] for k in active] + cover
    J = np.stack([b["world"][f] for b in bodies])
    heights = np.array([b["height"] for b in bodies])
    mesh = sc.get("mesh")
    turn = np.zeros(len(bodies))
    for k, a in enumerate(active):
        if fit is not None and (only is None or players[a]["id"] in only):
            yaw[(f, a)] = best_yaw(sc, f, image, a, fit)
        turn[k] = yaw.get((f, a), 0.0) if yaw is not None else 0.0
    pts, nrm = surface(J, n, heights, cells, turn if turn.any() else None)
    if mesh is not None:   # Oberfläche des Viewer-Netzes statt der Zylinder, wo der Viewer die Figur zeichnet (tools/avatar_mesh.py)
        for k, b in enumerate(bodies):
            got = mesh.points(f, b["id"], index) if "id" in b else None
            if got is not None:
                ok = ~np.isnan(got[0][:, 0])
                pts[k][ok], nrm[k][ok] = got[0][ok], got[1][ok]
    out = []
    for li, lens_name in enumerate(LENSES):
        lens_image = image[li * H:(li + 1) * H]
        lens_bg = background[li * H:(li + 1) * H]
        centre = cam["lenses"][lens_name]["centre"]
        view = centre - pts
        dist = np.linalg.norm(view, axis=-1)
        facing = (nrm * view).sum(-1) / dist
        uv = veo_camera.project(cam, lens_name, pts.reshape(-1, 3)).reshape(len(bodies), N, 2)
        uv_raw = uv.copy()   # ohne Versatz zu den erkannten Gelenkpunkten (für Messungen)
        for k, b in enumerate(bodies):
            if "shift" in b and b["lens"][f] == li and not np.isnan(b["shift"][f, 0, 0]):
                uv[k] += anchor @ b["shift"][f]
        inside = (facing > 0.15) & (uv[..., 0] >= 1) & (uv[..., 0] < W - 2) & (uv[..., 1] >= 1) & (uv[..., 1] < H - 2)
        if not inside.any():
            continue
        # Tiefenpuffer aus allen sichtbaren Flächen (je Stelle 2 × 2 Pixel)
        depth = np.full((H, W), np.inf, np.float32)
        ui, vi, di = uv[..., 0][inside].astype(int), uv[..., 1][inside].astype(int), dist[inside]
        for du in (0, 1):
            for dv in (0, 1):
                np.minimum.at(depth, (np.minimum(vi + dv, H - 1), np.minimum(ui + du, W - 1)), di)
        for k, a in enumerate(active):
            if only is not None and players[a]["id"] not in only:
                continue
            m = inside[k]
            if not m.any():
                continue
            q = uv[k][m]
            front = dist[k][m] <= depth[q[:, 1].astype(int), q[:, 0].astype(int)] + OCCLUDE
            q = q[front]
            if not len(q):
                continue
            colour = sample(lens_image, q)
            empty, apart = grass(colour, lens_bg, q)
            # Gewicht: frontal gesehen, Auflösung (Pixel je Meter), keine Rasenfarbe. Arme und Beine sind nur wenige
            # Pixel breit, viele Bildpunkte mischen Körper und Rasen; je deutlicher ein Punkt sich vom leeren Platz
            # abhebt, desto reiner zeigt er den Körper und desto mehr zählt er.
            scale = 1.0 / dist[k][m][front]
            w = (facing[k][m][front] - 0.1) * scale * 20.0 * ~empty * np.minimum(apart / PURE, 1.0) ** 2
            out.append({"player": a, "lens": li, "cell": np.flatnonzero(m)[front], "uv": q, "colour": colour, "weight": w,
                        "facing": facing[k][m][front], "dist": dist[k][m][front], "image": lens_image,
                        "uv_raw": uv_raw[k][m][front]})
    return out


def main(video, det_path, camera_path, background_path, scene_dir, check_path=None, quality_power=0.0, align_rounds=0, masks=False, views=0, turn=0, mesh_path=None, view_depth=VIEW_DEPTH):
    began = time.time()
    scene_dir = Path(scene_dir)
    sc = load_scene(video, det_path, camera_path, background_path, scene_dir, mesh_path)
    players, index = sc["players"], sc["index"]
    present = sc["present"]
    P = len(players)
    print(f"{P} Spieler mit Gelenkpunkten im Video; Bilder mit brauchbarer Ausrichtung: "
          f"{sum(int(p['usable'].sum()) for p in players)} von {sum(int(present[:, p['entity']].sum()) for p in players)}", flush=True)

    yaw = fit_yaw(sc, turn, began) if turn else None   # Drehung des Rumpfs je Bild (None = Haltung aus den Gelenkpunkten)

    if views:   # Ansichtentextur: je Körperteil und Ansicht ein zusammenhängendes Bild (view_texture)
        model = segmenter() if masks else None
        store = [{k: [] for k in ("texel", "colour", "weight", "quality", "obs")} for _ in range(P)]
        for f, image in frames(sc):
            observed = observe(sc, f, image, yaw=yaw)
            entries = frame_masks(model, observed) if masks else [None] * len(observed)
            for o, entry in zip(observed, entries):
                st = store[o["player"]]
                n = len(st["obs"])
                st["texel"].append(index[o["cell"]].astype(np.int64))
                st["colour"].append(o["colour"].astype(np.float32))
                st["weight"].append((o["weight"] * in_mask(entry, o["uv"])).astype(np.float64))
                st["quality"].append((o["facing"] / o["dist"]).astype(np.float64))
                st["obs"].append(np.full(len(o["cell"]), n, np.int64))
        mean_rows, wplain_rows = [], []
        for a in range(P):
            st = store[a]
            if not st["obs"]:
                mean_rows.append(np.zeros((TILE * TILE, 3)))
                wplain_rows.append(np.zeros(TILE * TILE))
                continue
            cat = {k: np.concatenate(v) for k, v in st.items()}
            tex, seen = view_texture(cat["texel"], cat["colour"], cat["weight"], cat["quality"], cat["obs"], len(st["obs"]), sectors=views, depth=view_depth)
            mean_rows.append(tex)
            wplain_rows.append(seen)
        mean, wplain = np.concatenate(mean_rows), np.concatenate(wplain_rows)
        store = None
        print(f"  [{time.time() - began:.0f} s] Ansichten", flush=True)
    else:
        # Durchgang 1: einfaches gewichtetes Mittel (und je Stelle die beste Güte). Danach `align_rounds` Durchgänge, in denen jedes Körperteil
        # je Bild auf das bisherige Mittel geschoben wird, Ausreißer wegfallen und nahe, frontale Bilder stärker zählen.
        size = P * TILE * TILE
        mean, wplain, best = None, None, np.zeros(size)
        model, mask_cache = (segmenter() if masks else None), {}
        for rnd in range(1 + max(align_rounds, 1)):
            sums, wq, wp = np.zeros((size, 3)), np.zeros(size), np.zeros(size)
            for f, image in frames(sc):
                observed = observe(sc, f, image, yaw=yaw)
                if masks and rnd == 0:   # Personenmasken einmal je Bild und Spieler rechnen und für die weiteren Durchgänge merken
                    for o, entry in zip(observed, frame_masks(model, observed)):
                        mask_cache[(f, o["player"], o["lens"])] = entry
                for o in observed:
                    texel = o["player"] * TILE * TILE + index[o["cell"]]
                    colour, w = o["colour"], o["weight"]
                    if masks:
                        w = w * in_mask(mask_cache[(f, o["player"], o["lens"])], o["uv"])
                    q = o["facing"] / o["dist"]
                    if rnd == 0:
                        np.maximum.at(best, texel, q)
                    else:
                        if align_rounds:
                            shift = align(o["image"], o["uv"], sc["segment"][o["cell"]], w, mean[texel], wplain[texel] >= ENOUGH)
                            colour = sample(o["image"], o["uv"] + shift)
                        w = w * (np.linalg.norm(colour - mean[texel], axis=1) < OUTLIER)
                    wg = w * np.minimum(q / np.maximum(best[texel], 1e-9), 1.0) ** quality_power if rnd else w
                    for ch in range(3):
                        sums[:, ch] += np.bincount(texel, wg * colour[:, ch], minlength=size)
                    wq += np.bincount(texel, wg, minlength=size)
                    wp += np.bincount(texel, w, minlength=size)   # "gesehen" hängt nicht von der Güte ab
            mean, wplain = sums / np.maximum(wq, 1e-9)[:, None], wp
            print(f"  [{time.time() - began:.0f} s] Durchgang {rnd + 1}", flush=True)

    weight = wplain.reshape(P, TILE * TILE)
    colour = mean.reshape(P, TILE * TILE, 3)
    seen = weight >= ENOUGH
    used = np.zeros(TILE * TILE, bool)
    used[index] = True
    print("Gesehener Anteil der Oberfläche je Spieler:", {p["id"]: round(float(seen[k][used].mean()), 2) for k, p in enumerate(players)}, flush=True)

    # Lücken füllen: gespiegelte Seite, Mannschaftsmittel für Trikot/Hose/Stutzen, sonst Mittel der Spielerzeile
    mirror = np.arange(TILE * TILE)
    for name, (x, y, w, h), _, _ in SEGMENTS:
        other = name[:-1] + ("r" if name.endswith("_l") else "l") if name[-2:] in ("_l", "_r") else name
        ox, oy = next(s[1][:2] for s in SEGMENTS if s[0] == other)
        rows, cols = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
        mirror[((y + rows) * TILE + x + cols).ravel()] = ((oy + rows) * TILE + ox + (w - 1 - cols)).ravel()
    filled = colour.copy()
    have = seen.copy()
    take = ~have & seen[:, mirror]
    filled[take] = colour[:, mirror][take]
    have |= take
    groups = {}
    for k, p in enumerate(players):
        groups.setdefault(p["group"], []).append(k)
    kit = np.zeros(TILE * TILE, bool)
    for name, (x, y, w, h), _, _ in SEGMENTS:
        if name == "torso" or name.split("_")[0] in ("thigh", "calf"):
            kit[(np.arange(y, y + h)[:, None] * TILE + np.arange(x, x + w)[None, :]).ravel()] = True
    team_tiles, extra, extra_have = {}, [], []
    for group, members in groups.items():
        wsum = weight[members].sum(axis=0)
        gmean = (colour[members] * weight[members][..., None]).sum(axis=0) / np.maximum(wsum, 1e-9)[:, None]
        gseen = (seen[members].sum(axis=0) >= 1)
        for k in members:
            take = ~have[k] & gseen & kit   # nur Trikot, Hose, Stutzen vom Mannschaftsmittel; Arme (Unterwäsche, Handschuhe), Kopf und Füße sind je Spieler verschieden
            filled[k][take] = gmean[take]
            have[k] |= take
        if not group.endswith("-gk") and len(members) >= 2:   # Kachel für Spieler der Mannschaft, die im Video nicht zu sehen waren
            team_tiles[group] = P + len(extra)
            extra.append(gmean)
            extra_have.append(gseen.copy())
    filled = np.concatenate([filled, np.array(extra).reshape(-1, TILE * TILE, 3)])
    have = np.concatenate([have, np.array(extra_have).reshape(-1, TILE * TILE)])
    for k in range(len(filled)):
        for name, (x, y, w, h), _, _ in SEGMENTS:
            block = (np.arange(y, y + h)[:, None] * TILE + np.arange(x, x + w)[None, :])
            for row in block:
                ok = have[k][row]
                if ok.any() and not ok.all():
                    filled[k][row[~ok]] = filled[k][row[ok]].mean(axis=0)
                    have[k][row[~ok]] = True
            ok = have[k][block.ravel()]
            if not ok.all():
                fill = filled[k][block.ravel()[ok]].mean(axis=0) if ok.any() else np.array([128.0, 128.0, 128.0])
                filled[k][block.ravel()[~ok]] = fill

    rows_needed = -(-len(filled) // COLUMNS)
    atlas = np.zeros((rows_needed * TILE, COLUMNS * TILE, 3), np.uint8)
    for k in range(len(filled)):
        tile = np.clip(filled[k], 0, 255).reshape(TILE, TILE, 3).astype(np.uint8)
        atlas[(k // COLUMNS) * TILE:(k // COLUMNS + 1) * TILE, (k % COLUMNS) * TILE:(k % COLUMNS + 1) * TILE] = tile
    cv2.imwrite(str(scene_dir / "looks.png"), atlas)
    meta_path = scene_dir / "meta.json"
    full = json.loads(meta_path.read_text())
    full["looks"] = {
        "file": "looks.png", "tile": TILE, "columns": COLUMNS,
        "players": {p["id"]: k for k, p in enumerate(players)},
        "teams": team_tiles,
        "segments": [{"name": name, "rect": list(rect), "t": list(t)} for name, rect, t, _ in SEGMENTS],
        "headShare": HEAD_SHARE, "footLift": FOOT_LIFT,
        "seen": {p["id"]: round(float(seen[k][used].mean()), 2) for k, p in enumerate(players)},
        "source": "Farben je Spieler aus dem Video (tools/veo_looks.py): Körperoberfläche mit der gerechneten Haltung ins "
                  "Kamerabild gelegt, über alle Bilder gemittelt; nie gesehene Stellen von der Gegenseite, bei Trikot/Hose/Stutzen "
                  "aus der Mannschaft und sonst aus der eigenen Zeile.",
    }
    meta_path.write_text(json.dumps(full, indent=2, ensure_ascii=False) + "\n")
    print(f"-> {scene_dir / 'looks.png'} ({atlas.shape[1]} × {atlas.shape[0]}), {time.time() - began:.0f} s")
    if check_path:
        np.savez_compressed(f"{check_path}.npz", weight=weight, colour=colour, ids=[p["id"] for p in players])
        big = cv2.resize(atlas, None, fx=3, fy=3, interpolation=cv2.INTER_NEAREST)
        for k, p in enumerate(players):
            cv2.putText(big, p["id"], ((k % COLUMNS) * TILE * 3 + 4, (k // COLUMNS) * TILE * 3 + 370), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.imwrite(str(check_path), big)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("video", "detektionen", "kamera", "hintergrund", "szenenordner"):
        ap.add_argument(name)
    ap.add_argument("pruefbild", nargs="?", help="Prüfbild (jpg) und Rohdaten (.npz) schreiben")
    ap.add_argument("--guete", type=float, default=0.0, metavar="P",
                    help="Gütegewicht: je Stelle zählen die nahsten, frontalsten Bilder (Güte / beste Güte der Stelle) hoch P; 0 = einfaches Mittel (Standard). "
                         "Größer = schärfer, aber körniger (gemessen: 6 bringt Kanten und Körnung, 2 bis 3 sind milder)")
    ap.add_argument("--maske", action="store_true",
                    help="Nur Bildpunkte zählen, die in der Personenmaske des Spielers liegen (models/yolo11x-seg.pt, rechnet einmal je Bild und Spieler): "
                         "im Zweikampf liegen viele Stellen auf dem Gegner und färben die Textur (rote Flecken am grünen Spieler)")
    ap.add_argument("--ansichten", type=int, default=0, metavar="N",
                    help="Textur aus zusammenhängenden Bildern je Ansicht statt aus dem Mittel aller Bilder: je Körperteil N Winkelbereiche (4 empfohlen), "
                         "jeder aus dem Bild mit der besten Güte (nah, frontal). Schärfer: Ziffern und Schriftzüge werden lesbar. 0 = Mittel (Standard)")
    ap.add_argument("--ausrichtung", type=int, default=0, metavar="N",
                    help="N Durchgänge, in denen jedes Körperteil je Bild auf das bisherige Mittel geschoben wird (je Durchgang rund ein Bilddurchlauf mehr); 0 = nur Gelenkpunkte (Standard)")
    ap.add_argument("--drehung", type=int, default=0, metavar="N",
                    help="N Runden, in denen je Bild die Drehung des Rumpfs um seine Achse (bis ±40°) gesucht wird, bei der er am besten zum Mittel passt; "
                         "die Haltung aus den Gelenkpunkten liegt dort um 15 bis 30° daneben. 0 = Haltung unverändert (Standard)")
    ap.add_argument("--netz", metavar="PKL", help="Oberfläche des Viewer-Netzes (tools/avatar_bake.py) statt der vereinfachten Zylinder: die Videobilder werden auf dieselben "
                    "Punkte gelegt, an denen der Viewer die Textur liest")
    ap.add_argument("--tiefe", type=int, default=VIEW_DEPTH, metavar="N",
                    help="mit --ansichten: so viele Bilder je Körperteil und Ansicht füllen Lücken des besten Bilds (1 = nur das beste Bild, Lücken vom Mittel)")
    a = ap.parse_args()
    main(a.video, a.detektionen, a.kamera, a.hintergrund, a.szenenordner, a.pruefbild, quality_power=a.guete, align_rounds=a.ausrichtung, masks=a.maske, views=a.ansichten, turn=a.drehung, mesh_path=a.netz, view_depth=a.tiefe)
