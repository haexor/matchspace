#!/usr/bin/env python3
"""Echtes Aussehen je Spieler aus dem Video: eine Textur für Trikot, Hose, Stutzen, Schuhe, Haut und Haare.

Jeder Punkt der Körperoberfläche hat eine feste Stelle in einer Kachel (128 × 128 Texel) je Spieler. Die
Oberfläche ist in Körperteile zerlegt (Rumpf, Kopf, Ober- und Unterarme, Ober- und Unterschenkel, Füße); in
jedem Teil zählt die Lage entlang der Achse (t) und der Winkel um sie herum (0 = vorn, +90° = links).

Für jedes Bild der Szene wird jede Stelle mit der gerechneten Haltung ins kalibrierte Kamerabild gelegt.
Sichtbar ist sie, wenn sie zur Kamera zeigt und kein Körper (der eigene oder ein anderer) davor liegt
(Tiefenpuffer aus allen Spielern). Damit Rasen nicht ins Trikot gerät, wird jedes Körperteil je Bild um den
Versatz zu seinen erkannten Gelenkpunkten nachgeschoben, und Bildpunkte, die wie der leere Platz
aussehen (auch Rasen im Schatten eines Spielers), zählen nicht. Gemittelt wird über alle Bilder in zwei Durchgängen (im zweiten ohne Ausreißer);
dreht sich der Spieler, füllt sich nach und nach auch die Rückseite. Was nie zu sehen war, kommt von der
gespiegelten Seite, dann vom Mittel der Mannschaft an dieser Stelle (Torwart und Schiedsrichter für sich).
Spieler, die im Video nicht zu sehen waren, tragen die Mittelkachel ihrer Mannschaft.

Grenzen: Spieler sind im Video rund 50 bis 120 Pixel hoch, die Textur ist entsprechend grob; Gesichter und
Rückennummern sind nicht zu erkennen. Licht und Schatten des Spieltags stecken in den Farben.

Aufruf (nach tools/veo_scene.py, das DETEKTIONEN.json.players.npz schreibt):
    .venv/bin/python tools/veo_looks.py SZENENVIDEO DETEKTIONEN.json KAMERA.json HINTERGRUND.png SZENENORDNER [PRÜFBILD.jpg]

Schreibt SZENENORDNER/looks.png und den Eintrag "looks" in meta.json. web/avatar.js rechnet für jeden Punkt
des Körpermodells dieselben Koordinaten aus der Grundhaltung und liest dort die Farbe.
"""
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import check_motion  # noqa: E402
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
    ("head", (64, 0, 32, 32), (0.0, 1.0),
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


def surface(J, n, height, cells):
    """Weltpunkte und Normalen (P, N, 3) aller Texel für Gelenke J (P, 20, 3)."""
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
        cos, sin = np.cos(th)[..., None], np.sin(th)[..., None]
        points.append(centre + rz[..., None] * cos * F + rx[..., None] * sin * S)
        normals.append(unit(cos / rz[..., None] * F + sin / rx[..., None] * S))
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


def load_scene(video, det_path, camera_path, background_path, scene_dir):
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
            "players": players, "others": others}


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


def observe(sc, f, image, only=None):
    """Was Bild f über die Oberfläche der Spieler verrät: je Spieler (nur `only`, sonst alle mit brauchbarer Ausrichtung)
    die sichtbaren Stellen ("cell" = Nummer in der Reihenfolge von grid()), ihre Bildpunkte uv, Farben und Gewichte.
    Verdecken dürfen alle Figuren im Bild, auch die, deren Farben in diesem Bild nicht zählen."""
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
    pts, nrm = surface(J, n, heights, cells)
    out = []
    for li, lens_name in enumerate(LENSES):
        lens_image = image[li * H:(li + 1) * H]
        lens_bg = background[li * H:(li + 1) * H]
        centre = cam["lenses"][lens_name]["centre"]
        view = centre - pts
        dist = np.linalg.norm(view, axis=-1)
        facing = (nrm * view).sum(-1) / dist
        uv = veo_camera.project(cam, lens_name, pts.reshape(-1, 3)).reshape(len(bodies), N, 2)
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
                        "facing": facing[k][m][front], "dist": dist[k][m][front]})
    return out


def main(video, det_path, camera_path, background_path, scene_dir, check_path=None):
    began = time.time()
    scene_dir = Path(scene_dir)
    sc = load_scene(video, det_path, camera_path, background_path, scene_dir)
    players, index = sc["players"], sc["index"]
    present = sc["present"]
    P = len(players)
    print(f"{P} Spieler mit Gelenkpunkten im Video; Bilder mit brauchbarer Ausrichtung: "
          f"{sum(int(p['usable'].sum()) for p in players)} von {sum(int(present[:, p['entity']].sum()) for p in players)}", flush=True)

    sums = [np.zeros((P * TILE * TILE, 3)), np.zeros((P * TILE * TILE, 3))]
    weights = [np.zeros(P * TILE * TILE), np.zeros(P * TILE * TILE)]
    mean = None
    for rnd in range(2):
        for f, image in frames(sc):
            for o in observe(sc, f, image):
                texel = o["player"] * TILE * TILE + index[o["cell"]]
                colour, w = o["colour"], o["weight"]
                if rnd == 1:
                    w = w * (np.linalg.norm(colour - mean[texel], axis=1) < OUTLIER)
                for ch in range(3):
                    sums[rnd][:, ch] += np.bincount(texel, w * colour[:, ch], minlength=P * TILE * TILE)
                weights[rnd] += np.bincount(texel, w, minlength=P * TILE * TILE)
        mean = sums[rnd] / np.maximum(weights[rnd], 1e-9)[:, None]
        print(f"  [{time.time() - began:.0f} s] Durchgang {rnd + 1}", flush=True)

    weight = weights[1].reshape(P, TILE * TILE)
    colour = mean.reshape(P, TILE * TILE, 3)
    seen = weight >= ENOUGH
    used = np.zeros(TILE * TILE, bool)
    used[index] = True
    print("Gesehener Anteil der Oberfläche je Spieler:", {p["id"]: round(float(seen[k][used].mean()), 2) for k, p in enumerate(players)}, flush=True)

    # Lücken füllen: gespiegelte Seite, dann Mannschaftsmittel an derselben Stelle, dann Mittel der Zeile
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
    team_tiles, extra, extra_have = {}, [], []
    for group, members in groups.items():
        wsum = weight[members].sum(axis=0)
        gmean = (colour[members] * weight[members][..., None]).sum(axis=0) / np.maximum(wsum, 1e-9)[:, None]
        gseen = (seen[members].sum(axis=0) >= 1)
        for k in members:
            take = ~have[k] & gseen
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
                  "Kamerabild gelegt, über alle Bilder gemittelt; nie gesehene Stellen von der Gegenseite oder aus der Mannschaft.",
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
    if len(sys.argv) not in (6, 7):
        sys.exit(__doc__)
    main(*sys.argv[1:])
