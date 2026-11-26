#!/usr/bin/env python3
"""Textur aus scharfen Fotos statt aus den Videobildern: Rück- und Vorderansicht eines Spielers (Bild-KI, tools/photo_ai.py) auf den Avatar legen.

Jedes Foto zeigt den Spieler gerade von hinten oder von vorn, scharf und ohne Perspektive. Das Avatar-Netz in der Grundhaltung (tools/avatar_mesh.py)
wird über Gelenkpunkte im Foto (models/yolo11x-pose.pt: Schultern, Hüften, Knie, Knöchel; dazu die Scheitelhöhe der Personenmaske) ins Foto gelegt:
senkrecht Stück für Stück linear, die Breite je Ebene aus dem Abstand der Gelenke links/rechts. Jeder Texel von Rumpf, Kopf, Ober- und Unterschenkeln liest
seine Farbe an der Stelle, an der er im Foto liegt (nur innerhalb der Personenmaske). Farben werden Kanal für Kanal an die Videotextur angepasst
(Beleuchtung, Farbton). Der Blendwinkel wählt je Texel das Foto, das ihn frontal sieht; an den Seiten (über ~50°) geht es weich in die Videotextur über.
Arme: Der Avatar steht in T-Haltung, die Arme im Foto hängen; jeder Armknochen wird in der Bildebene aus der T-Lage in die Richtung der Pose-Punkte (Schulter, Ellbogen, Handgelenk) gedreht und skaliert.

Aufruf:
    .venv/bin/python tools/looks_from_photo.py SZENENORDNER NETZ.pkl --ausgabe ORDNER (--spieler own-5 [--hinten FOTO.png] [--vorn FOTO.png] | --ki KI_ORDNER) [--bis-winkel 75] [--debug PREFIX]
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
GRASS_DELTA = 22.0         # Lab-Abstand zum Rasen, unter dem ein Pixel als Rasen gilt
ARM_ANGLE = 115.0          # Arme: Blendwinkel bis hinter die Seitenlinie (90°)
PARTS = ("torso", "head", "thigh_l", "thigh_r", "calf_l", "calf_r") + tuple(ARMS)


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


def fit(mesh, photo_path, view):
    """Abbildung Avatar (x, y in m) -> Foto (u, v in Pixeln) als Ebenen: je Ebene Höhe v, Mitte u_c und Breitenmaß sx (Pixel je Meter)."""
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
    return {"kp": kp, "conf": conf, "levels": levels, "mask": mask, "y": np.array([q["y"] for q in levels]), "v": np.array([q["v"] for q in levels]),
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
    sx = np.interp(y, fm["y"], fm["sx"])
    return u_c + SIGN[fm["view"]] * P[:, 0] * sx, v


def grass_mask(image, mask):
    """Pixel, die so aussehen wie der Rasen im Foto (Farbabstand zum Rasenmedian außerhalb der Person in Lab): die Personenmaske füllt Lücken zwischen Arm und Körper aus."""
    lab = cv2.cvtColor(image.astype(np.uint8), cv2.COLOR_BGR2LAB).astype(np.float32)
    far = ~(cv2.dilate(mask.astype(np.uint8), np.ones((25, 25), np.uint8)) > 0)
    ref = np.median(lab[far], axis=0)
    return np.linalg.norm(lab - ref, axis=2) < GRASS_DELTA


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
    r = P[:, :2] - a0[:2]
    rot = np.stack([c * r[:, 0] - s_ * r[:, 1], s_ * r[:, 0] + c * r[:, 1]], axis=1) * k
    return p0[0] + sign * rot[:, 0], p0[1] - rot[:, 1]


def main(scene_dir, player, photos, mesh_path, out_dir, max_angle, debug=None):
    scene_dir, out_dir = Path(scene_dir), Path(out_dir)
    meta = json.loads((scene_dir / "meta.json").read_text())
    looks = meta["looks"]
    atlas = cv2.imread(str(scene_dir / "looks.png"))
    cols, tile = looks["columns"], looks["tile"]
    k = looks["players"][player]
    f = tile // vl.TILE
    segments = [(n, (x * f, y * f, w * f, h * f), t, p) for n, (x, y, w, h), t, p in vl.SEGMENTS]
    mesh = avatar_mesh.AvatarMesh(mesh_path, segments, tile)
    J = mesh.joints()
    ty, tx = (k // cols) * tile, (k % cols) * tile
    fits = {v: fit(mesh, str(p), v) for v, p in photos.items()}
    images = {v: cv2.imread(str(p)).astype(np.float32) for v, p in photos.items()}
    out = atlas.copy()
    q = np.linspace(0, 100, 101)
    stats = {}
    torso_gain = {}
    for si, (name, (x, y, w, h), _, _) in enumerate(segments):
        if name not in PARTS:
            continue
        rows, cols_ = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
        index = ((y + rows) * tile + x + cols_).ravel()
        P, N = mesh.rest_points(index)
        ok = ~np.isnan(P[:, 0])
        base = atlas[ty + y:ty + y + h, tx + x:tx + x + w].reshape(-1, 3).astype(np.float32)
        total, acc = np.zeros(len(index)), np.zeros((len(index), 3))
        for view, fm in fits.items():
            facing = np.where(ok, SIGN[view] * N[:, 2], 0.0)       # Kamera vorn: +z, hinten: −z
            # Arme: die Seiten sieht weder Vorder- noch Rückfoto, sie sind fast einfarbig (Ärmel): Foto bis über die Seitenlinie hinaus fortsetzen
            limit = ARM_ANGLE if name in ARMS else max_angle
            angle = np.degrees(np.arccos(np.clip(facing, -1 if name in ARMS else 0, 1)))
            if name in ARMS:
                got = project_arm(fm, name, np.nan_to_num(P), J)
                if got is None:
                    continue
                u, v = got
            else:
                u, v = project(fm, np.nan_to_num(P))
            H, W = fm["mask"].shape
            inside = ok & (u >= 1) & (u < W - 2) & (v >= 1) & (v < H - 2)
            colour = np.zeros((len(index), 3), np.float32)
            colour[inside] = vl.sample(images[view], np.c_[u[inside], v[inside]] + 0.5)
            core = inside & (angle < 40)
            if name in ARMS:
                # die Videotextur der Arme ist selbst verunreinigt (Armflecken), und die Kurve des Rumpfs (fast nur Rot/Grün) verfärbt Schwarz und Haut:
                # nur die Helligkeit des Rumpfs übernehmen (ein Faktor)
                if view not in torso_gain:
                    continue
                colour = colour * torso_gain[view]
            else:
                if core.sum() < 20:
                    continue
                maps = [(np.percentile(colour[core, ch], q), np.percentile(base[core, ch], q)) for ch in range(3)]
                if name == "torso":
                    torso_gain[view] = float(np.median(base[core]) / max(np.median(colour[core]), 1.0))
                for ch in range(3):
                    colour[:, ch] = np.interp(colour[:, ch], *maps[ch])
            colour = np.clip(colour, 0, 255)
            weight = np.clip((limit - angle) / 25.0, 0, 1) * inside
            weight = weight * weight * (3 - 2 * weight)
            if name in ARMS:
                # dünne Arme: Rand der Maske weg (Rasen daneben), Texel an der Seitenlinie lesen den nächsten Punkt im Ärmelinneren
                if "snap" not in fm:
                    fm["snap"] = snap_inside((cv2.erode(fm["mask"].astype(np.uint8), np.ones((13, 13), np.uint8)) > 0) & ~cv2.dilate(grass_mask(images[view], fm["mask"]).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool))
                sy, sx, dist = fm["snap"]
                iu, iv = u[inside].astype(int), v[inside].astype(int)
                colour[inside] = vl.sample(images[view], np.c_[sx[iv, iu], sy[iv, iu]] + 0.5) * torso_gain.get(view, 1.0)
                # kein Abstandslimit: der Avatararm ist breiter als der Arm im Foto, die Randtexel lesen den nächsten Ärmelpunkt
            else:
                on_person = np.zeros(len(index), bool)
                on_person[inside] = cv2.erode(fm["mask"].astype(np.uint8), np.ones((5, 5), np.uint8))[v[inside].astype(int), u[inside].astype(int)] > 0
                weight = weight * on_person
            if name == "torso":      # nur das Trikot: zwischen Saum und Kragen (Hals und Hose bleiben von der Videotextur)
                low, high = J["pelvis"][1] + 0.005, J["neck_01"][1] + 0.018
                edge = np.clip(np.minimum(P[:, 1] - low, high - P[:, 1]) / 0.02, 0, 1)
                weight = weight * np.where(np.isnan(edge), 0, edge)
            total += weight
            acc += weight[:, None] * colour
            stats[(name, view)] = float(weight.mean())
        mix = np.minimum(total, 1.0)
        new = (acc / np.maximum(total, 1e-6)[:, None]) * mix[:, None] + base * (1 - mix[:, None])
        tile_new = np.clip(new, 0, 255).astype(np.uint8).reshape(h, w, 3)
        if name in ARMS and total.size:
            # Texel, die das Netz nicht abdeckt (Naht der Armkachel), hätten die verunreinigte Videofarbe: aus den Nachbarn füllen (Naht läuft um die Kachel herum)
            gap = (~ok).reshape(h, w).astype(np.uint8)
            if gap.any():
                pad = 6
                wrapped = np.concatenate([tile_new[:, -pad:], tile_new, tile_new[:, :pad]], axis=1)
                gap_w = np.concatenate([gap[:, -pad:], gap, gap[:, :pad]], axis=1)
                tile_new = cv2.inpaint(wrapped, gap_w, 3, cv2.INPAINT_TELEA)[:, pad:-pad]
        out[ty + y:ty + y + h, tx + x:tx + x + w] = tile_new
    print("Mittleres Gewicht je Teil/Ansicht:", {f"{a}/{b}": round(c, 2) for (a, b), c in stats.items()})
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
                ok = ~np.isnan(P[:, 0]) & (SIGN[view] * N[:, 2] > 0.5)
                got = project_arm(fm, name, np.nan_to_num(P), J) if name in ARMS else project(fm, np.nan_to_num(P))
                if got is None:
                    continue
                u, v = got
                for uu, vv in zip(u[ok][::5], v[ok][::5]):
                    cv2.circle(img, (int(uu), int(vv)), 2, (0, 255, 255) if name == "torso" else (0, 128, 255) if name in ARMS else (255, 0, 255), -1)
            cv2.imwrite(f"{debug}_{view}_overlay.png", cv2.resize(img, None, fx=0.5, fy=0.5))
        cv2.imwrite(f"{debug}_atlas.png", np.hstack([atlas[ty:ty + tile, tx:tx + tile], out[ty:ty + tile, tx:tx + tile]]))


def all_players(scene_dir, ki_dir, mesh_path, out_dir, max_angle):
    """Alle Spieler, für die tools/photo_ai.py Ansichten erzeugt hat (KI_ORDNER/index.json), nacheinander in dieselbe Ausgabeszene legen."""
    index = json.loads((Path(ki_dir) / "index.json").read_text())
    known = json.loads((Path(scene_dir) / "meta.json").read_text())["looks"]["players"]
    src = scene_dir
    for player, views in index.items():
        photos = {v: Path(ki_dir) / player / f"{v}.png" for v in ("hinten", "vorn") if views.get(v, {}).get("ok")}
        if not photos or player not in known:
            continue
        print(f"== {player}: {', '.join(photos)}", flush=True)
        try:
            main(src, player, photos, mesh_path, out_dir, max_angle)
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
    ap.add_argument("--ausgabe", required=True)
    ap.add_argument("--bis-winkel", type=float, default=75.0, dest="winkel")
    ap.add_argument("--debug")
    a = ap.parse_args()
    if a.ki:
        all_players(a.szenenordner, a.ki, a.netz, a.ausgabe, a.winkel)
        sys.exit(0)
    photos = {v: p for v, p in (("hinten", a.hinten), ("vorn", a.vorn)) if p}
    if not (a.spieler and photos):
        sys.exit("--spieler und mindestens --hinten oder --vorn angeben (oder --ki ORDNER).")
    main(a.szenenordner, a.spieler, photos, a.netz, a.ausgabe, a.winkel, a.debug)
