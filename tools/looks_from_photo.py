#!/usr/bin/env python3
"""Textur aus scharfen Fotos statt aus den Videobildern: Rück-, Vorder- und Seitenansichten eines Spielers (Bild-KI, tools/photo_ai.py) auf den Avatar legen.

Jedes Foto zeigt den Spieler gerade von hinten oder von vorn, scharf und ohne Perspektive. Das Avatar-Netz in der Grundhaltung (tools/avatar_mesh.py)
wird über Gelenkpunkte im Foto (models/yolo11x-pose.pt: Schultern, Hüften, Knie, Knöchel; dazu die Scheitelhöhe der Personenmaske) ins Foto gelegt:
senkrecht Stück für Stück linear, die Breite je Ebene aus dem Abstand der Gelenke links/rechts. Jeder Texel von Rumpf, Kopf, Ober- und Unterschenkeln liest
seine Farbe an der Stelle, an der er im Foto liegt (nur innerhalb der Personenmaske), unverändert: keine Mittelung, keine Farbangleichung an das Video, keine
Überblendung mit der Videotextur. Jeder Texel nimmt das Foto, das ihn am frontalsten sieht; nur in einer schmalen Naht (SEAM) zweier fast gleich frontaler Fotos wird
überblendet. Nur Texel, die kein Foto sieht (zum Beispiel die Brust, wenn es nur ein Rückenfoto gibt), bleiben aus der Videotextur.
Arme: Der Avatar steht in T-Haltung, die Arme im Foto hängen; jeder Armknochen wird in der Bildebene aus der T-Lage in die Richtung der Pose-Punkte (Schulter, Ellbogen, Handgelenk) gedreht und skaliert.

Aufruf:
    .venv/bin/python tools/looks_from_photo.py SZENENORDNER NETZ.pkl --ausgabe ORDNER (--spieler own-5 [--hinten FOTO.png] [--vorn FOTO.png] [--links FOTO.png] [--rechts FOTO.png] | --ki KI_ORDNER) [--debug PREFIX]
SZENENORDNER: Szene mit bereits gerechneter und bereinigter Textur (looks.png in 4-facher Größe, tools/looks_clean.py --aufdruck-behalten).
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import avatar_mesh  # noqa: E402
import veo_looks as vl  # noqa: E402

POSE_MODEL = Path(__file__).resolve().parent.parent / "models" / "yolo11x-pose.pt"
SIGN = {"hinten": -1.0, "vorn": 1.0}     # u = u_c + SIGN · x · sx: Spieler-links (Avatar +x) liegt von hinten links im Bild, von vorn rechts
ARMS = {"upperarm_l": ("upperarm_l", "lowerarm_l", 5, 7), "lowerarm_l": ("lowerarm_l", "hand_l", 7, 9),
        "upperarm_r": ("upperarm_r", "lowerarm_r", 6, 8), "lowerarm_r": ("lowerarm_r", "hand_r", 8, 10)}   # Segment: (Gelenk Anfang, Gelenk Ende am Avatar, Pose-Punkt Anfang, Ende)
BG_DELTA = 7.0            # Lab-Abstand zu einem Hintergrundpixel derselben Zeile, unter dem ein Pixel in der Maske als Hintergrund gilt
GRASS_DELTA = 22.0         # Lab-Abstand zum Rasen, unter dem ein Pixel als Rasen gilt
SEAM = 0.08                # Naht zwischen zwei Fotos: so viel Frontalität (cos) Spielraum, in dem überblendet wird
FACE = {"hinten": np.array([0.0, 0.0, -1.0]), "vorn": np.array([0.0, 0.0, 1.0]),
        "links": np.array([1.0, 0.0, 0.0]), "rechts": np.array([-1.0, 0.0, 0.0])}   # Richtung vom Spieler zur Kamera (Avatar: +z vorn, +x links)
SIDES = ("links", "rechts")
ARM_BAND = 0.17            # so breit (m, mit Rand) liegt der hängende Arm samt Ärmelkante im Foto (dort sieht das Foto keinen Rumpf)
FRONTAL_BIAS = 0.25        # Vorder-/Rückfoto bilden genauer ab als die Seitenfotos: sie behalten den Vorrang bis weit an die Seite (sonst Flecken an der Naht)
HEAD_SIDE_NZ = 0.2         # Kopf: Seitenfotos nur für den seitlichen Streifen (Ohren, Schläfen); im Gesicht legen sie Augen und Nase versetzt daneben (zwei Nasen, vier Augen)
TORSO_MIN_FACING = 0.3      # Rumpf aus Vorder-/Rückfoto nur, wo die Fläche dem Foto zugewandt ist (cos)
THIGH_INNER_T = 0.5         # Oberschenkelachse: so weit nach unten ist die Innenseite von den Shorts und dem anderen Bein verdeckt
THIGH_INNER_FACING = -0.2   # Innenseite: Normale zeigt so weit (cos) zum anderen Bein
LOWER_T = 0.05              # Rumpfachse: darunter liegen Saum und Shorts
TORSO_FILL = "inpaint"       # Rumpflücken (vom Arm verdeckt): "inpaint" (weicher Verlauf aus dem Rand) oder "median"
INPAINT_FLAG = cv2.INPAINT_TELEA
HEAD_NECK_T = 0.1          # Kopfachse: bis hier ist es der Halsansatz
CROWN_T = 0.92             # Kopfachse: ab hier ist es der Scheitel
NECK_T = 1.15              # Rumpfachse: ab hier ist der Rumpf nur noch Hals (Haut)
FILL_MIN_COVERAGE = 0.6    # ab diesem Anteil der Texel eines Teils aus Fotos werden die übrigen aus den Nachbarn gefüllt (sonst bleibt das Video)
PARTS = ("torso", "head", "thigh_l", "thigh_r", "calf_l", "calf_r", "foot_l", "foot_r") + tuple(ARMS)


def person_mask(photo_path):
    """Maske der Person im Foto (models/yolo11x-seg.pt), bool (H, W). Das Foto zeigt eine Person, die das Modell manchmal in Teile (Rumpf, Beine) zerlegt: Vereinigung."""
    result = vl.segmenter().predict(photo_path, imgsz=640, classes=[0], conf=0.3, retina_masks=True, verbose=False)[0]
    masks = result.masks.data.cpu().numpy() > 0.5
    return masks.any(axis=0)


def keypoints(photo_path):
    from ultralytics import YOLO
    r = YOLO(str(POSE_MODEL)).predict(photo_path, verbose=False, conf=0.2)[0]
    best = int(np.argmax([float(c.mean()) for c in r.keypoints.conf]))
    return r.keypoints.xy[best].cpu().numpy(), r.keypoints.conf[best].cpu().numpy()


def arm_band(kp, conf, scale, shape):
    """Maske der hängenden Arme im Foto (Linien Schulter–Ellbogen–Handgelenk, ARM_BAND Meter breit): dort sieht das Foto keinen Rumpf."""
    band = np.zeros(shape, np.uint8)
    for a, b in ((5, 7), (7, 9), (6, 8), (8, 10)):
        if min(conf[a], conf[b]) >= 0.3:
            cv2.line(band, tuple(int(c) for c in kp[a]), tuple(int(c) for c in kp[b]), 1, max(3, int(ARM_BAND * scale)))
    # Schultern: der Ärmelansatz gehört auch zum Arm (sonst bleiben dunkle Kerben an der Schulter)
    for a in (5, 6):
        if conf[a] >= 0.3:
            cv2.circle(band, tuple(int(c) for c in kp[a]), max(3, int(0.35 * ARM_BAND * scale)), 1, -1)
    return band > 0


def fit_side(mesh, photo_path, view):
    """Seitenansicht: wie fit(), nur trägt die Bildbreite die Tiefe (z des Avatars): u = u_Ebene + Richtung · (z − z_Ebene) · Maßstab. Die Blickrichtung der Figur (Nase gegen Hüfte)
    bestimmt, welche Seite das Foto wirklich zeigt (von links schaut die Figur nach Bildlinks); zeigt es die andere, gilt es als diese."""
    kp, conf = keypoints(photo_path)
    mask = person_mask(photo_path)
    J = mesh.joints()
    levels = []
    for joint, l, r in (("foot", 15, 16), ("calf", 13, 14), ("thigh", 11, 12), ("upperarm", 5, 6)):
        use = [i for i in (l, r) if conf[i] >= 0.3]
        if not use:
            raise RuntimeError(f"{photo_path}: Gelenk {joint} nicht sicher gefunden")
        levels.append({"y": J[joint + "_l"][1], "z": J[joint + "_l"][2], "v": float(np.mean([kp[i][1] for i in use])), "u": float(np.mean([kp[i][0] for i in use]))})
    ys, xs = np.nonzero(mask)
    v_top = float(ys.min())
    head = mesh.look[:, 3] == 1
    world = (np.concatenate([mesh.rest, np.ones((len(mesh.rest), 1))], axis=1) @ mesh.bind.T)[:, :3]
    sh, hip = levels[3], levels[2]
    scale = (hip["v"] - sh["v"]) / (sh["y"] - hip["y"])
    top_rows = ys < v_top + 0.08 * (ys.max() - v_top)
    levels.append({"y": float(world[head, 1].max()), "z": J["Head"][2], "v": v_top, "u": float(np.median(xs[top_rows]))})
    levels.sort(key=lambda q: q["y"])
    hip_u = np.mean([kp[i][0] for i in (11, 12) if conf[i] >= 0.3] or [hip["u"]])
    expected = -1.0 if view == "links" else 1.0
    direction = expected
    if conf[0] >= 0.3 and abs(kp[0][0] - hip_u) > 0.01 * mask.shape[1]:
        direction = 1.0 if kp[0][0] > hip_u else -1.0
    actual = "links" if direction < 0 else "rechts"
    return {"kp": kp, "conf": conf, "mask": mask, "side": True, "dir": direction, "scale": scale, "view": actual, "label": view, "arm_mask": arm_band(kp, conf, scale, mask.shape),
            "y": np.array([q["y"] for q in levels]), "v": np.array([q["v"] for q in levels]), "u": np.array([q["u"] for q in levels]), "z": np.array([q["z"] for q in levels])}


def fit(mesh, photo_path, view):
    """Abbildung Avatar (x, y in m) -> Foto (u, v in Pixeln) als Ebenen: je Ebene Höhe v, Mitte u_c und Breitenmaß sx (Pixel je Meter)."""
    if view in SIDES:
        return fit_side(mesh, photo_path, view)
    kp, conf = keypoints(photo_path)
    mask = person_mask(photo_path)
    J = mesh.joints()
    pairs = [("ankle", "foot", 15, 16), ("knee", "calf", 13, 14), ("hip", "thigh", 11, 12), ("shoulder", "upperarm", 5, 6)]
    levels = []
    for name, joint, l, r in pairs:
        if min(conf[l], conf[r]) < 0.5:
            raise RuntimeError(f"{photo_path}: Gelenk {name} nicht sicher gefunden")
        ya, xa = J[joint + "_l"][1], abs(J[joint + "_l"][0])
        left, right = kp[l], kp[r]
        # Spieler-links ist der Avatar +x; im Foto von hinten links, von vorn rechts
        half = abs(left[0] - right[0]) / 2
        levels.append({"y": ya, "v": (left[1] + right[1]) / 2, "u": (left[0] + right[0]) / 2, "sx": half / xa})
    ys, xs = np.nonzero(mask)
    v_top = float(ys.min())
    head = mesh.look[:, 3] == 1
    world = (np.concatenate([mesh.rest, np.ones((len(mesh.rest), 1))], axis=1) @ mesh.bind.T)[:, :3]
    y_top = float(world[head, 1].max())
    sh, hip = levels[3], levels[2]
    scale_y = (hip["v"] - sh["v"]) / (sh["y"] - hip["y"])        # Pixel je Meter senkrecht (Schulter bis Hüfte)
    top_rows = ys < v_top + 0.08 * (ys.max() - v_top)
    levels.append({"y": y_top, "v": v_top, "u": float(np.median(xs[top_rows])), "sx": scale_y})
    levels.sort(key=lambda q: q["y"])
    return {"kp": kp, "conf": conf, "levels": levels, "mask": mask, "arm_mask": arm_band(kp, conf, scale_y, mask.shape), "y": np.array([q["y"] for q in levels]), "v": np.array([q["v"] for q in levels]),
            "u": np.array([q["u"] for q in levels]), "sx": np.array([q["sx"] for q in levels]), "view": view}


def project(fm, P):
    """Foto-Koordinaten (u, v) der Avatarpunkte P (N, 3) in der Grundhaltung."""
    y = P[:, 1]
    # oberhalb der Schulter bis zum Scheitel und unterhalb des Knöchels: Randebenen halten, senkrecht linear fortsetzen
    v = np.interp(y, fm["y"], fm["v"])
    lo = y < fm["y"][0]
    if lo.any():
        v[lo] = fm["v"][0] + (y[lo] - fm["y"][0]) * (fm["v"][1] - fm["v"][0]) / (fm["y"][1] - fm["y"][0])
    u_c = np.interp(y, fm["y"], fm["u"])
    if fm.get("side"):
        return u_c + fm["dir"] * (P[:, 2] - np.interp(y, fm["y"], fm["z"])) * fm["scale"], v
    sx = np.interp(y, fm["y"], fm["sx"])
    return u_c + SIGN[fm["view"]] * P[:, 0] * sx, v


def fill_holes_median(tile, hole, ok, window=2, reach=14):
    """Lücken (hole, vom Arm verdeckt oder von keinem Foto gesehen) mit dem Median der gültigen Foto-Texel unmittelbar daneben füllen (gleiche Zeilen ± window, bis `reach` Texel
    links und rechts der Lücke, die Kachel läuft rund): bei Trikot und Hals die ruhige echte Farbe, ohne Ärmelkanten, Kragen oder Rückennummer aus der übrigen Zeile mitzuziehen."""
    out = tile.copy()
    h, w = hole.shape
    good = ok & ~hole
    for r in range(h):
        if not hole[r].any():
            continue
        cols = np.nonzero(hole[r])[0]
        runs = np.split(cols, np.nonzero(np.diff(cols) > 1)[0] + 1)
        for run in runs:
            span = np.arange(run[0] - reach, run[-1] + reach + 1) % w
            rows = np.arange(max(0, r - window), min(h, r + window + 1))
            sel = good[np.ix_(rows, span)]
            vals = tile[np.ix_(rows, span)][sel]
            if len(vals) >= 8:
                out[r, run] = np.median(vals, axis=0)
    return out


def grass_mask(image, mask):
    """Pixel, die so aussehen wie der Rasen im Foto (Farbabstand zum Rasenmedian außerhalb der Person in Lab): die Personenmaske füllt Lücken zwischen Arm und Körper aus."""
    lab = cv2.cvtColor(image.astype(np.uint8), cv2.COLOR_BGR2LAB).astype(np.float32)
    far = ~(cv2.dilate(mask.astype(np.uint8), np.ones((25, 25), np.uint8)) > 0)
    far[:int(0.7 * far.shape[0])] = False          # Rasen liegt unten; oben stehen Himmel und Bäume (sonst ein Mittel aus allem, das keinen Rasen trifft)
    ref = np.median(lab[far], axis=0)
    bg = np.linalg.norm(lab - ref, axis=2) < GRASS_DELTA
    # Oberhalb des Rasens: Himmel, Bäume, Zaun. Zeilenweise der Hintergrund rechts und links der Person (Band 25–150 px), Pixel der Maske mit nahezu gleicher Farbe sind Hintergrund
    # (Lücken zwischen Arm und Rumpf; sonst liest der Rumpf dort den weißen Himmel).
    m8 = mask.astype(np.uint8)
    band = (cv2.dilate(m8, np.ones((151, 151), np.uint8)) > 0) & ~(cv2.dilate(m8, np.ones((25, 25), np.uint8)) > 0)
    rng = np.random.default_rng(0)
    h = mask.shape[0]
    for r in np.nonzero(mask.any(axis=1))[0]:
        cols = np.nonzero(mask[r])[0]
        lo, hi = max(0, r - 8), min(h, r + 9)
        sy, sx = np.nonzero(band[lo:hi])
        if len(sx) < 20:
            continue
        pick = rng.choice(len(sx), min(len(sx), 300), replace=False)
        samples = lab[lo + sy[pick], sx[pick]]
        d = np.linalg.norm(lab[r, cols][:, None, :] - samples[None], axis=2).min(axis=1)
        bg[r, cols] |= d < BG_DELTA
    return bg


def background(fm, image):
    """grass_mask je Foto nur einmal berechnen."""
    if "bg" not in fm:
        fm["bg"] = grass_mask(image, fm["mask"])
    return fm["bg"]


def snap_inside(inner):
    """Zu jedem Bildpunkt der nächstgelegene Punkt in der Maske `inner` (bool): (Zeilen, Spalten, Abstand). Für die Armränder: Texel an der Seitenlinie lesen das Ärmelinnere statt Rasen."""
    src = (~inner).astype(np.uint8)
    dist, labels = cv2.distanceTransformWithLabels(src, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.nonzero(inner)
    order = np.zeros(labels.max() + 1, int)
    # Beschriftung der Nullpixel: jedes Nullpixel trägt seine eigene Nummer (zeilenweise gezählt, ab 1)
    order[labels[ys, xs]] = np.arange(len(ys))
    idx = order[labels]
    return ys[idx], xs[idx], dist


def skin_reference(fits, images):
    """Hautfarbe (Lab) des Spielers aus den Wangen und der Nase eines Fotos mit Gesicht (vorn, sonst eine Seite); None, wenn keines ein Gesicht zeigt.
    Sie dient nur dazu, im Foto den Hals zu finden (Pixel mit Hautfarbton): kein Farbwert wird übernommen."""
    for view in ("vorn", "links", "rechts"):
        fm = fits.get(view)
        if fm is None or min(fm["conf"][0], fm["conf"][1], fm["conf"][2]) < 0.5:
            continue
        kp = fm["kp"]
        eye = max(float(np.linalg.norm(kp[1] - kp[2])), 8.0)
        x, y = kp[0]
        r = int(0.5 * eye)
        img = images[view].astype(np.uint8)
        box = img[max(0, int(y) - r):int(y) + r + 1, max(0, int(x) - r):int(x) + r + 1]
        if box.size:
            return np.median(cv2.cvtColor(box, cv2.COLOR_BGR2LAB).reshape(-1, 3).astype(np.float32), axis=0)
    return None


def skin_like(image, inner, ref):
    """Pixel von `inner` mit Hautfarbton (Farbart a, b in Lab nahe der Hautfarbe `ref`, Helligkeit nicht zu weit weg): Trikot, Haare und Kragen fallen heraus."""
    lab = cv2.cvtColor(image.astype(np.uint8), cv2.COLOR_BGR2LAB).astype(np.float32)
    chroma = np.linalg.norm(lab[..., 1:] - ref[1:], axis=2)
    return inner & (chroma < 14.0) & (np.abs(lab[..., 0] - ref[0]) < 70.0)


def project_arm(fm, name, P, J):
    """Foto-Koordinaten für Armtexel: Der Avatar steht in T-Haltung, im Foto hängt der Arm. Jeder Armknochen (Schulter–Ellbogen, Ellbogen–Handgelenk) wird in der Bildebene (Drehung um die Tiefenachse, die Vorderseite bleibt vorn)
    aus der T-Lage in die Richtung der Pose-Punkte gedreht und auf deren Länge skaliert. None, wenn die Punkte im Foto unsicher sind."""
    j0, j1, k0, k1 = ARMS[name]
    if min(fm["conf"][k0], fm["conf"][k1]) < 0.5:
        return None
    sign = SIGN[fm["view"]]
    a0, a1 = J[j0], J[j1]
    d0 = np.array([a1[0] - a0[0], a1[1] - a0[1]])
    p0, p1 = fm["kp"][k0], fm["kp"][k1]
    b = np.array([sign * (p1[0] - p0[0]), -(p1[1] - p0[1])])         # Knochenrichtung im Avatar-Rahmen (x links, y oben)
    k = np.linalg.norm(b) / np.linalg.norm(d0)
    ang = np.arctan2(b[1], b[0]) - np.arctan2(d0[1], d0[0])
    c, s_ = np.cos(ang), np.sin(ang)
    # Nur die Knochenachse abbilden (Fußpunkt jedes Texels auf der Achse): ein Arm ist im Foto eine Röhre, deren Farbe entlang der Achse wechselt (Haut, Ärmel).
    # Seitlich versetzte Texel träfen bei kleinen Fehlern der Pose-Punkte den Rumpf oder den Rasen und gäben Zacken.
    d3 = np.asarray(a1, float) - np.asarray(a0, float)
    along = np.clip((P - np.asarray(a0, float)) @ d3 / (d3 @ d3), -0.15, 1.15)
    P = np.asarray(a0, float) + along[:, None] * d3
    r = P[:, :2] - a0[:2]
    rot = np.stack([c * r[:, 0] - s_ * r[:, 1], s_ * r[:, 0] + c * r[:, 1]], axis=1) * k
    return p0[0] + sign * rot[:, 0], p0[1] - rot[:, 1]


def hidden_inner_thigh(name, normal_x, t):
    """Texel der Innenseite im oberen Oberschenkel (zwischen den Beinen, unter den Shorts): bool je Texel. Kein Foto sieht sie; dort stand Schatten oder die Lücke zwischen den Beinen.
    name: thigh_l oder thigh_r, normal_x: x der Normalen (links = +x), t: Lage entlang der Oberschenkelachse."""
    toward_other_leg = np.nan_to_num(normal_x) * (-1.0 if name.endswith("_l") else 1.0)
    return (toward_other_leg > THIGH_INNER_FACING) & (t < THIGH_INNER_T)


def migrate_layout(atlas, looks, f):
    """Kopfbereich der Kacheln auf den Sollbereich (vl.SEGMENTS) bringen, falls die Szene noch den alten, kleineren hat: Der Kopfbereich wird für alle Spieler
    hochskaliert an die neue Stelle kopiert (das Gesicht belegt in der größeren Kachel doppelt so viele Pixel), die Szene bekommt den neuen Bereich im Meta.
    -> (Atlas, Meta). Ist die Szene schon im neuen Layout, kommt beides unverändert zurück."""
    want = next(tuple(v * f for v in rect) for name, rect, _, _ in vl.SEGMENTS if name == "head")
    segs = [dict(s) for s in looks["segments"]]
    head = next(s for s in segs if s["name"] == "head")
    if tuple(head["rect"]) == want:
        return atlas, looks
    ox, oy, ow, oh = head["rect"]
    nx, ny, nw, nh = want
    tile, cols = looks["tile"], looks["columns"]
    out = atlas.copy()
    for k in range(atlas.shape[0] // tile * cols):
        ty, tx = (k // cols) * tile, (k % cols) * tile
        if ty + tile > atlas.shape[0]:
            break
        old = atlas[ty + oy:ty + oy + oh, tx + ox:tx + ox + ow]
        out[ty + ny:ty + ny + nh, tx + nx:tx + nx + nw] = cv2.resize(old, (nw, nh), interpolation=cv2.INTER_CUBIC)
    head["rect"] = list(want)
    return out, {**looks, "segments": segs}


def main(scene_dir, player, photos, mesh_path, out_dir, debug=None):
    scene_dir, out_dir = Path(scene_dir), Path(out_dir)
    meta = json.loads((scene_dir / "meta.json").read_text())
    looks = meta["looks"]
    atlas = cv2.imread(str(scene_dir / "looks.png"))
    cols, tile = looks["columns"], looks["tile"]
    k = looks["players"][player]
    f = tile // vl.TILE
    atlas, looks = migrate_layout(atlas, looks, f)       # Szenen mit dem alten Kopfbereich (kleine Kachel) bekommen den großen
    meta["looks"] = looks
    segments = [(s["name"], tuple(s["rect"]), tuple(s["t"]), None) for s in looks["segments"]]
    mesh = avatar_mesh.AvatarMesh(mesh_path, segments, tile)
    J = mesh.joints()
    ty, tx = (k // cols) * tile, (k % cols) * tile
    fits = {v: fit(mesh, str(p), v) for v, p in photos.items()}
    images = {v: cv2.imread(str(p)).astype(np.float32) for v, p in photos.items()}
    skin = skin_reference(fits, images)
    out = atlas.copy()
    q = np.linspace(0, 100, 101)
    stats = {}
    for si, (name, (x, y, w, h), trange, _) in enumerate(segments):
        if name not in PARTS:
            continue
        rows, cols_ = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
        t_axis = (trange[0] + (rows + 0.5) / h * (trange[1] - trange[0])).ravel()
        index = ((y + rows) * tile + x + cols_).ravel()
        P, N = mesh.rest_points(index)
        ok = ~np.isnan(P[:, 0])
        base = atlas[ty + y:ty + y + h, tx + x:tx + x + w].reshape(-1, 3).astype(np.float32)
        cands = []                      # je Foto: (Rang des Texels (Frontalität, Vorder-/Rückfoto bevorzugt), Farbe, gültig)
        arm_view = next((v for v in ("vorn", "hinten") if v in fits and not fits[v].get("side")), None)   # Arme aus EINEM Foto: sonst Zacken an der Naht (Ärmellänge weicht ab)
        for view, fm in fits.items():
            if name in ARMS and view != arm_view:
                continue
            facing = np.where(ok, np.nan_to_num(N) @ FACE[fm["view"]], -9.0)       # Kamera vorn: +z, hinten: −z, links: +x, rechts: −x
            if name in ARMS:
                got = project_arm(fm, name, np.nan_to_num(P), J)
                if got is None:
                    continue
                u, v = got
            else:
                u, v = project(fm, np.nan_to_num(P))
            H, W = fm["mask"].shape
            inside = ok & (u >= 1) & (u < W - 2) & (v >= 1) & (v < H - 2)
            # Dünne Teile (Arme, Beine, Füße) und Seitenansichten: Die Personenmaske füllt Lücken (zwischen Arm und Körper, zwischen den Beinen), dort steht Rasen oder Trikot.
            # Texel an der Kante lesen deshalb den nächsten Punkt im Inneren der Person ohne Rasenfarbe (snap_inside).
            snap_mode = name in ARMS or bool(fm.get("side")) or name.startswith(("thigh", "calf", "foot"))
            su, sv = u, v
            valid = inside.copy()
            if snap_mode:
                key = "snap13" if name in ARMS else "snap5"
                if key not in fm:
                    k_ = 13 if name in ARMS else 5
                    fm[key] = snap_inside((cv2.erode(fm["mask"].astype(np.uint8), np.ones((k_, k_), np.uint8)) > 0) & ~cv2.dilate(background(fm, images[view]).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool))
                sy_, sx_, _ = fm[key]
                iu, iv = u[inside].astype(int), v[inside].astype(int)
                su, sv = u.copy(), v.copy()
                su[inside], sv[inside] = sx_[iv, iu], sy_[iv, iu]
            else:
                on_person = np.zeros(len(index), bool)
                on_person[inside] = cv2.erode(fm["mask"].astype(np.uint8), np.ones((5, 5), np.uint8))[v[inside].astype(int), u[inside].astype(int)] > 0
                on_person &= ~cv2.dilate(background(fm, images[view]).astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)[v.astype(int).clip(0, H - 1), u.astype(int).clip(0, W - 1)]
                valid &= on_person
                if name == "torso":
                    # Halszeilen: der Hals ist schmaler als die Schulterbreite, auf die die Abbildung dort noch skaliert; die Texel landen neben dem Hals (Rasen).
                    # Sie lesen den nächsten Körperpunkt ohne Rasenfarbe.
                    neck = inside & (np.nan_to_num(P[:, 1]) > J["neck_01"][1] - 0.04)
                    if neck.any():
                        if "snap5" not in fm:
                            fm["snap5"] = snap_inside((cv2.erode(fm["mask"].astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & ~cv2.dilate(background(fm, images[view]).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool))
                        sy_, sx_, _ = fm["snap5"]
                        iu, iv = u[neck].astype(int), v[neck].astype(int)
                        if su is u:
                            su, sv = u.copy(), v.copy()
                        su[neck], sv[neck] = sx_[iv, iu], sy_[iv, iu]
                        valid |= neck
            skin_rows = None      # Hals = Haut: diese Texel lesen den nächsten Pixel mit Hautfarbton (nicht Kragen, Haar oder Rasen)
            if skin is not None and name == "torso":
                skin_rows = inside & (t_axis > NECK_T)
            elif skin is not None and name == "head":
                skin_rows = inside & (t_axis < 0.22)
            if skin_rows is not None and skin_rows.any():
                if "snap_skin" not in fm:
                    inner = (cv2.erode(fm["mask"].astype(np.uint8), np.ones((5, 5), np.uint8)) > 0) & ~cv2.dilate(background(fm, images[view]).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
                    like = skin_like(images[view], inner, skin)
                    fm["snap_skin"] = snap_inside(like) if like.any() else None
                if fm["snap_skin"] is not None:
                    sy_, sx_, _ = fm["snap_skin"]
                    iu, iv = u[skin_rows].astype(int), v[skin_rows].astype(int)
                    if su is u:
                        su, sv = u.copy(), v.copy()
                    su[skin_rows], sv[skin_rows] = sx_[iv, iu], sy_[iv, iu]
                    valid |= skin_rows
            if name == "head" and fm.get("side"):
                valid &= np.abs(np.nan_to_num(N[:, 2])) < HEAD_SIDE_NZ
            neck_ok = np.zeros(len(index), bool) if skin_rows is None else (skin_rows & valid)      # Halsröhre: auch ihre Seiten lesen die Haut vom Vorder-/Rückfoto (sonst Lücken, aus dem Trikot gefüllt: Zackenring)
            if name == "torso" and fm.get("side"):      # Hals und Kragen nur aus Vorder-/Rückfoto: die Seitenfotos bilden den Hals nicht genau genug ab (gezackter Ring an der Naht)
                valid &= np.nan_to_num(P[:, 1]) <= J["neck_01"][1] - 0.01
            if name == "torso":      # der hängende Arm (und die Hand) verdeckt die Rumpfseite: dort sieht dieses Foto keinen Rumpf
                covered = np.zeros(len(index), bool)
                covered[inside] = fm["arm_mask"][v[inside].astype(int), u[inside].astype(int)]
                valid &= ~covered
            if name == "torso" and not fm.get("side"):      # Rumpfrand im Vorder-/Rückfoto: die Abbildung trifft dort knapp daneben (Arm, Rasen), die Texel wären hell/verfälscht
                valid &= (facing >= TORSO_MIN_FACING) | neck_ok
            if name.startswith("thigh"):     # Innenseite im oberen Teil (zwischen den Beinen, unter den Shorts): kein Foto sieht sie, dort stand Schatten oder die Lücke (schwarze Flamme an der Hüfte)
                hidden = hidden_inner_thigh(name, N[:, 0], t_axis)
                valid &= ~hidden
                hip_arm = np.zeros(len(index), bool)          # die hängende Hand und der schwarze Unterärmel liegen im Foto vor der Hüfte
                hip_arm[inside] = fm["arm_mask"][v[inside].astype(int), u[inside].astype(int)]
                valid &= ~(hip_arm & (t_axis < THIGH_INNER_T))
            if name not in ARMS:     # nur Texel, die das Foto sieht (nicht von hinten: sonst käme die Rückennummer auf die Brust); Arme sind eine Röhre in einer Farbe, sie lesen ihr Foto ganz
                valid &= (facing >= 0.0) | neck_ok
            colour = np.zeros((len(index), 3), np.float32)
            colour[valid] = vl.sample(images[view], np.c_[su[valid], sv[valid]] + 0.5)
            rank = facing + (0.0 if fm.get("side") else FRONTAL_BIAS)
            cands.append((np.where(valid, rank, -9.0), colour, valid))
        if not cands:
            continue
        # Jeder Texel liest sein Foto unverändert: das frontalste. Nur in einer schmalen Naht (zwei Fotos fast gleich frontal) wird überblendet; keine Videotextur, keine Farbangleichung.
        F = np.stack([c[0] for c in cands])
        best = F.max(axis=0)
        wgt = np.clip((F - (best - SEAM)) / SEAM, 0, 1) ** 2 * (F > -9.0)
        total = wgt.sum(axis=0)
        acc = sum(wgt[i][:, None] * cands[i][1] for i in range(len(cands)))
        has = total > 0
        coverage = float(has[ok].mean()) if ok.any() else 0.0
        stats[name] = coverage
        # Texel, die kein Foto sieht: bei guter Abdeckung (alle Ansichten da) aus den Nachbartexeln der Fotos gefüllt; nur bei kaum Fotos (zum Beispiel nur ein Rückenfoto) bleibt die Videotextur
        new = np.where(has[:, None], acc / np.maximum(total, 1e-9)[:, None], base)
        tile_new = np.clip(new, 0, 255).astype(np.uint8).reshape(h, w, 3)
        if name == "torso" and TORSO_FILL == "median":
            tile_new = fill_holes_median(tile_new, (ok & ~has).reshape(h, w), ok.reshape(h, w))
        settled = np.zeros((h, w), bool)
        if name == "torso":
            # Unterer Rumpf (Saum, Shorts): rund um die Hüfte einfarbig; vom Arm verdeckte Seiten bekommen den Median der ganzen Zeile (nicht den Verlauf aus dem Rand,
            # der dunkle Ärmelreste mitzieht: dunkle Flamme an der Hüfte)
            low = np.repeat((t_axis.reshape(h, w)[:, :1] < LOWER_T), w, axis=1)
            gone = (ok & ~has).reshape(h, w) & low
            if gone.any():
                tile_new = fill_holes_median(tile_new, gone, ok.reshape(h, w), window=1, reach=w)
                settled = gone
        if name == "head":      # Scheitel (die letzten Zeilen): im Foto knapp am Rand der Personenmaske, dort steht Himmel zwischen den Haaren; die Haarzeile darunter fortsetzen
            tile_new[int(CROWN_T * h):] = tile_new[int(CROWN_T * h) - 1]
            tile_new[:int(HEAD_NECK_T * h)] = tile_new[int(HEAD_NECK_T * h)]      # Halsansatz am Kopf: die Zeile darüber fortsetzen (dort schimmerte das Trikot als Zackenring durch)
        if coverage >= FILL_MIN_COVERAGE:
            hole = ((ok & ~has).reshape(h, w) & ~settled).astype(np.uint8)
            if hole.any():
                pad = 6
                wrapped = np.concatenate([tile_new[:, -pad:], tile_new, tile_new[:, :pad]], axis=1)
                hole_w = np.concatenate([hole[:, -pad:], hole, hole[:, :pad]], axis=1)
                tile_new = cv2.inpaint(wrapped, hole_w, 9 if name == "torso" else 4, INPAINT_FLAG)[:, pad:-pad]
        # Texel ohne Netz (Naht der Kachel, wird nicht gezeichnet, aber beim Filtern gelesen): aus den Nachbarn füllen (die Naht läuft um die Kachel herum)
        gap = (~ok).reshape(h, w).astype(np.uint8)
        if gap.any():
            pad = 6
            wrapped = np.concatenate([tile_new[:, -pad:], tile_new, tile_new[:, :pad]], axis=1)
            gap_w = np.concatenate([gap[:, -pad:], gap, gap[:, :pad]], axis=1)
            tile_new = cv2.inpaint(wrapped, gap_w, 3, cv2.INPAINT_TELEA)[:, pad:-pad]
        out[ty + y:ty + y + h, tx + x:tx + x + w] = tile_new
    print("Anteil der Texel aus Fotos je Teil:", {a: round(c, 2) for a, c in stats.items()})
    out_dir.mkdir(parents=True, exist_ok=True)
    for item in scene_dir.iterdir():
        if item.name != "looks.png" and not (out_dir / item.name).exists():
            (shutil.copytree if item.is_dir() else shutil.copy2)(item, out_dir / item.name)
    cv2.imwrite(str(out_dir / "looks.png"), out)
    meta["looks"].setdefault("fromPhoto", {})[player] = {v: Path(p).name for v, p in photos.items()}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    print(f"-> {out_dir}")
    if debug:
        for view, fm in fits.items():
            img = images[view].astype(np.uint8).copy()
            for si, (name, (x, y, w, h), _, _) in enumerate(segments):
                if name not in PARTS:
                    continue
                rows, cols_ = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
                P, N = mesh.rest_points(((y + rows) * tile + x + cols_).ravel())
                ok = ~np.isnan(P[:, 0]) & (np.nan_to_num(N) @ FACE[fm["view"]] > 0.5)
                if name in ARMS and fm.get("side"):
                    continue
                got = project_arm(fm, name, np.nan_to_num(P), J) if name in ARMS else project(fm, np.nan_to_num(P))
                if got is None:
                    continue
                u, v = got
                for uu, vv in zip(u[ok][::5], v[ok][::5]):
                    cv2.circle(img, (int(uu), int(vv)), 2, (0, 255, 255) if name == "torso" else (0, 128, 255) if name in ARMS else (255, 0, 255), -1)
            cv2.imwrite(f"{debug}_{view}_overlay.png", cv2.resize(img, None, fx=0.5, fy=0.5))
        cv2.imwrite(f"{debug}_atlas.png", np.hstack([atlas[ty:ty + tile, tx:tx + tile], out[ty:ty + tile, tx:tx + tile]]))


def all_players(scene_dir, ki_dir, mesh_path, out_dir):
    """Alle Spieler, für die tools/photo_ai.py Ansichten erzeugt hat (KI_ORDNER/index.json), nacheinander in dieselbe Ausgabeszene legen."""
    index = json.loads((Path(ki_dir) / "index.json").read_text())
    known = json.loads((Path(scene_dir) / "meta.json").read_text())["looks"]["players"]
    src = scene_dir
    for player, views in index.items():
        photos = {v: Path(ki_dir) / player / f"{v}.png" for v in ("hinten", "vorn", "links", "rechts") if views.get(v, {}).get("ok")}
        if not photos or player not in known:
            continue
        print(f"== {player}: {', '.join(photos)}", flush=True)
        try:
            main(src, player, photos, mesh_path, out_dir)
            src = out_dir
        except Exception as err:   # noqa: BLE001  (ein Spieler mit unsicherer Haltung im Foto darf den Rest nicht stoppen)
            print(f"   übersprungen: {err}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("szenenordner")
    ap.add_argument("netz")
    ap.add_argument("--spieler")
    ap.add_argument("--ki", help="Ordner von tools/photo_ai.py: alle Spieler darin übernehmen (statt --spieler/--hinten/--vorn)")
    ap.add_argument("--hinten")
    ap.add_argument("--vorn")
    ap.add_argument("--links")
    ap.add_argument("--rechts")
    ap.add_argument("--ausgabe", required=True)
    ap.add_argument("--debug")
    a = ap.parse_args()
    if a.ki:
        all_players(a.szenenordner, a.ki, a.netz, a.ausgabe)
        sys.exit(0)
    photos = {v: p for v, p in (("hinten", a.hinten), ("vorn", a.vorn), ("links", a.links), ("rechts", a.rechts)) if p}
    if not (a.spieler and photos):
        sys.exit("--spieler und mindestens --hinten oder --vorn angeben (oder --ki ORDNER).")
    main(a.szenenordner, a.spieler, photos, a.netz, a.ausgabe, a.debug)
