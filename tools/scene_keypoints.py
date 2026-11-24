"""Gelenkpunkte und Bodenphasen (Stufen 3 und 4a/4b von tools/veo_scene.py).

  - Je Spieler die 2D-Gelenkpunkte seiner Boxen einsammeln (aus tools/veo_keypoints.py); liegen sie auf einem Spieler in
    fremdem Trikot, werden sie verworfen. Körpergröße aus den Gelenkpunkten.
  - Der Personendetektor übersieht flach liegende Spieler oft ganz: Wo ein Spieler keine Box hat, seine Position aber
    weitergeführt wird, wird im vergrößerten Ausschnitt nach einer Person im eigenen Trikot gesucht (teuer, wird gemerkt).
  - Bodenphasen (fallen, liegen, aufsetzen, aufstehen): Die Haltung wird direkt aus den 2D-Gelenkpunkten als Seitenansicht
    gelesen, über die Zeit beruhigt, Lücken werden gehalten.
"""
import math
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import pose_fit  # noqa: E402
import pose_limits  # noqa: E402
import veo_camera  # noqa: E402
import veo_keypoints  # noqa: E402
from scene_boxes import BOX_TO_BODY, LENSES, box_metres, posture  # noqa: E402
from scene_util import hold, running_median, segments  # noqa: E402
from veo_keypoints import torso_colour  # noqa: E402

CROP_HEIGHT = 384
DOWN_CONF = 0.3       # Mindestsicherheit eines Gelenkpunkts am Boden
HOLD = 60             # Bilder, über die die letzte erkannte Haltung am Boden gehalten wird
MIN_DOWN = 8          # Bilder am Stück, die ein Spieler liegen muss, damit es als Sturz gilt
AROUND = 45           # Bilder vor und nach dem Liegen, die noch zur Bodenphase gehören (fallen, aufstehen)
CACHE_VERSION = 7.0


@dataclass
class Joints:
    """Gelenkpunkte je Spieler. kp2d: Feld (Bilder, 17, 3) Pixel und Sicherheit (NaN ohne Erkennung); boxed: Bilder mit
    Gelenkpunkten aus einer Box des Detektors; body: Körpergröße aus den Gelenkpunkten (m); vbox: Box der Person, die die
    Suche ohne Box gefunden hat."""
    kp2d: dict
    boxed: dict
    body: dict
    vbox: dict


def side_pose(kp, lens, cam, spot, lengths, left_far):
    """Haltung eines Spielers am Boden aus 2D-Gelenkpunkten, als Seitenansicht gelesen.

    Jeder Punkt wird auf die senkrechte Ebene durch den Standort des Spielers gerechnet, quer zur
    Blickrichtung: Das ergibt Höhe und seitliche Lage. In Blickrichtung bekommt nur die Breite von
    Becken und Schultern eine Tiefe (linke Seite hinten, wenn left_far), sonst liegt alles in der Ebene.
    Ein Knochen kann in der Ansicht nur kürzer erscheinen, als er ist: Gelenke, die das verletzen,
    gelten als nicht erkannt.
    kp: (17, 3) COCO-Punkte (Pixel, Sicherheit); spot: Standort am Boden (2); lengths: Knochenlängen
    des Spielers (pose_limits.bone_lengths). Rückgabe: (17, 3) H36M im Feld oder None."""
    conf = kp[:, 2]
    if np.isnan(conf).any() or (conf[[5, 6, 11, 12]] < DOWN_CONF).any():
        return None
    eye = cam["position"]
    view = np.array([spot[0] - eye[0], spot[1] - eye[1], 0.0])
    view /= np.linalg.norm(view)
    rays = veo_camera.rays(cam, lens, kp[:, :2])
    pts = eye + rays * (((np.array([spot[0], spot[1], 0.0]) - eye) @ view) / (rays @ view))[:, None]
    pts[conf < DOWN_CONF] = np.nan
    pelvis, thorax = (pts[11] + pts[12]) / 2, (pts[5] + pts[6]) / 2
    torso = np.linalg.norm(thorax - pelvis)
    if np.isnan(torso) or torso < 0.05 or torso > 1.25 * lengths["neck"]:
        return None
    axis = (thorax - pelvis) / torso  # vom Becken zum Kopf
    slack = 1.25
    for a, b, c, l1, l2 in ((11, 13, 15, "lKnee", "lAnkle"), (12, 14, 16, "rKnee", "rAnkle"), (5, 7, 9, "lElbow", "lWrist"), (6, 8, 10, "rElbow", "rWrist")):
        if np.linalg.norm(pts[b] - pts[a]) > slack * lengths[l1]:
            pts[b] = pts[c] = np.nan
        elif np.linalg.norm(pts[c] - pts[b]) > slack * lengths[l2]:
            pts[c] = np.nan
    if np.linalg.norm(pts[0] - thorax) > slack * (lengths["head"] + 0.12):
        pts[0] = np.nan

    def chain(a, b, c, l1, l2):  # fehlende Gelenke: gestreckt weiter
        pb = pts[b] if not np.isnan(pts[b, 0]) else pts[a] - axis * l1
        step = pb - pts[a]
        pc = pts[c] if not np.isnan(pts[c, 0]) else pb + step / max(np.linalg.norm(step), 1e-6) * l2
        return pb, pc

    def depth(a, b, half):  # was von der halben Breite im Bild fehlt, liegt in Blickrichtung
        return math.sqrt(max(half ** 2 - (np.linalg.norm(pts[a] - pts[b]) / 2) ** 2, 0.0)) * (1 if left_far else -1)
    nose = pts[0] if not np.isnan(pts[0, 0]) else thorax + axis * lengths["head"]
    out = np.zeros((17, 3))
    out[0], out[7], out[8] = pelvis, (pelvis + thorax) / 2, thorax
    out[9], out[10] = thorax + 0.55 * (nose - thorax), thorax + 1.3 * (nose - thorax)
    hips, chest = depth(11, 12, lengths["lHip"]), depth(5, 6, lengths["lShoulder"])
    for sign, hip, kn, an, sh, el, wr, h_hip, h_kn, h_an, h_sh, h_el, h_wr in ((1, 11, 13, 15, 5, 7, 9, 4, 5, 6, 11, 12, 13), (-1, 12, 14, 16, 6, 8, 10, 1, 2, 3, 14, 15, 16)):
        knee, ankle = chain(hip, kn, an, lengths["lKnee"], lengths["lAnkle"])
        elbow, wrist = chain(sh, el, wr, lengths["lElbow"], lengths["lWrist"])
        out[h_hip], out[h_kn], out[h_an] = (q + view * hips * sign for q in (pts[hip], knee, ankle))
        out[h_sh], out[h_el], out[h_wr] = (q + view * chest * sign for q in (pts[sh], elbow, wrist))
    return out


def read_keypoints(run, observed, smooth):
    """Gelenkpunkte für jede Box aus tools/veo_keypoints.py (einmal je Szene gerechnet) und Körpergröße daraus.
    Rückgabe (kp2d, body)."""
    n, cam, cam_pos, obs = run.n, run.cam, run.cam_pos, observed.obs
    kp_path = Path(str(run.det_path) + ".keypoints.npz")
    if not kp_path.exists() or kp_path.stat().st_mtime < Path(run.det_path).stat().st_mtime:
        veo_keypoints.main(run.video, run.det_path, run.camera_path, out_path=str(kp_path))
    with np.load(kp_path) as archive:
        found = {name: archive[name] for name in archive.files}
    kit = observed.kit
    kp2d = {key: np.full((n, 17, 3), np.nan) for key in smooth}
    foreign = 0
    for key in smooth:
        b = obs[key]
        for fi in np.flatnonzero(~np.isnan(b[:, 0])):
            row = found["index"][fi, int(b[fi, 0]), 0] + int(b[fi, 8])
            colour = int(found["colour"][row])
            if kit.get(key, -1) >= 0 and colour >= 0 and colour != kit[key]:
                foreign += 1
                continue
            kp2d[key][fi] = found["kp"][row]
    # Körpergröße aus den Gelenkpunkten: Bein und Rumpf erscheinen im Bild höchstens so lang, wie sie sind
    # (in die Tiefe geneigt kürzer). Maß ist deshalb ein Wert etwas über der Mitte aller Bilder, in Metern am Ort des Spielers.
    body = {}
    for key, kp in kp2d.items():
        _, A = pose_fit.linearize(cam, obs[key][:, 0], obs[key][:, 5:7])
        # Bildvektor -> Meter in der Ebene quer zur Blickrichtung (seitlich, hoch); die Linsenbilder sind gekippt
        away = obs[key][:, 5:7] - cam_pos[:2]
        side = np.column_stack([away[:, 1], -away[:, 0]]) / np.maximum(np.linalg.norm(away, axis=1, keepdims=True), 1e-9)
        M = np.stack([np.einsum("tij,tj->ti", A[:, :, :2], side), A[:, :, 2]], axis=2)
        ok = np.isfinite(M).all(axis=(1, 2))
        inverse = np.full((n, 2, 2), np.nan)
        inverse[ok] = np.linalg.inv(M[ok])

        def span(a, b):
            return np.linalg.norm(np.einsum("tij,tj->ti", inverse, a - b), axis=1)
        sure = (kp[:, 5:17, 2] >= 0.5).all(axis=1) & ok
        legs = (span(kp[:, 11, :2], kp[:, 13, :2]) + span(kp[:, 13, :2], kp[:, 15, :2]) + span(kp[:, 12, :2], kp[:, 14, :2]) + span(kp[:, 14, :2], kp[:, 16, :2])) / 2
        chain = (legs + span((kp[:, 5, :2] + kp[:, 6, :2]) / 2, (kp[:, 11, :2] + kp[:, 12, :2]) / 2))[sure]
        if len(chain) >= 40:
            body[key] = float(np.clip(np.percentile(chain, 60) / pose_limits.CHAIN_SHARE, 1.40, 1.95))
    print("Körpergröße aus den Gelenkpunkten (m):", {f"{k[0]}-{k[1]}": round(v, 2) for k, v in sorted(body.items())}, flush=True)
    with_points = sum(int((~np.isnan(k[:, 0, 0])).sum()) for k in kp2d.values())
    print(f"Gelenkpunkte für {with_points} Boxen übernommen, {foreign} verworfen (fremdes Trikot)", flush=True)
    return kp2d, body


def search_without_box(run, observed, smooth):
    """Bilder ohne Box, in denen die Position weitergeführt wird: im vergrößerten Ausschnitt nach einer Person im eigenen
    Trikot suchen (für Spieler am Boden). Das ist teuer und wird neben den Erkennungen gemerkt.
    Rückgabe (vkp, vbox): Gelenkpunkte und Box der gefundenen Person je Spieler."""
    n, size, obs, kit = run.n, run.size, observed.obs, observed.kit
    det_path, camera_path = run.det_path, run.camera_path
    stamp = [Path(x).stat().st_mtime for x in (det_path, camera_path) + (() if run.no_veo else (run.align_path,))] \
        + [float(observed.total_boxes), CACHE_VERSION, float(run.no_veo),
           float(zlib.crc32(repr(sorted(obs)).encode()))]   # Spielernamen: ändern sich mit gelesenen Rückennummern
    # je Bild und Linse: wo jeder Spieler im Bild erwartet wird (Unterkante seiner Box oder Veo-Position)
    expected = [({}, {}) for _ in range(n)]
    for key, b in obs.items():
        for fi in np.flatnonzero(~np.isnan(b[:, 0])):
            wide = b[fi, 3] - b[fi, 1] > b[fi, 4] - b[fi, 2]
            expected[fi][int(b[fi, 0])][key] = ((b[fi, 1] + b[fi, 3]) / 2, (b[fi, 2] + b[fi, 4]) / 2 if wide else b[fi, 4])
    for key, v in smooth.items():
        for fi in np.flatnonzero(~np.isnan(v["virtual"][:, 0])):
            expected[fi][int(v["virtual"][fi, 0])][key] = tuple(v["virtual"][fi, 1:3])
    cache_path = Path(str(det_path) + (".virtual_own.npz" if run.no_veo else ".virtual.npz"))
    cached = np.load(cache_path) if cache_path.exists() else None
    if cached is not None and len(cached["stamp"]) == len(stamp) and np.allclose(cached["stamp"], stamp):
        split = lambda k: (k.split("|")[1], int(k.split("|")[2]))  # noqa: E731
        vkp = {split(k): cached[k] for k in cached.files if k.startswith("kp|")}
        vbox = {split(k): cached[k] for k in cached.files if k.startswith("vb|")}
        print(f"Suche in Bildern ohne Box aus {cache_path} übernommen", flush=True)
        return vkp, vbox
    from ultralytics import YOLO
    model = YOLO("models/yolo11x-pose.pt")
    vkp = {key: np.full((n, 17, 3), np.nan) for key in smooth}
    vbox = {key: np.full((n, 4), np.nan) for key in smooth}  # Box der gefundenen Person
    cap = cv2.VideoCapture(run.video)
    pending = []  # (key, bild, x0, y0, maßstab, ausschnitt, erwartung)

    def flush():
        if not pending:
            return
        results = model.predict([p[5] for p in pending], imgsz=CROP_HEIGHT, conf=0.15, verbose=False)
        for (key, fi, x0, y0, s, img, expect), res in zip(pending, results):
            if res.keypoints is None or not len(res.boxes):
                continue
            # Nur Personen im eigenen Trikot kommen in Frage, und nur am erwarteten Fußpunkt, sofern dort nicht
            # ein Mitspieler näher erwartet wird. Bezugspunkt ist bei breiten Boxen (liegend) die Mitte.
            all_kp = res.keypoints.data.cpu().numpy()
            mine = [c for c in range(len(all_kp)) if kit.get(key, -1) < 0 or torso_colour(img, all_kp[c]) == kit[key]]
            li, u, v, stand_px = expect
            box = res.boxes.xyxy.cpu().numpy() / s + [x0, y0, x0, y0]
            wide = (box[:, 2] - box[:, 0]) > (box[:, 3] - box[:, 1])
            anchor = np.column_stack([(box[:, 0] + box[:, 2]) / 2, np.where(wide, (box[:, 1] + box[:, 3]) / 2, box[:, 3])])
            dist = np.linalg.norm(anchor - [u, v], axis=1)
            rivals = np.array([q for other, q in expected[fi][int(li)].items() if other != key and kit.get(other) == kit.get(key)]).reshape(-1, 2)
            k = next((c for c in sorted(mine, key=lambda c: dist[c]) if dist[c] < 0.6 * stand_px
                      and (not len(rivals) or np.linalg.norm(rivals - anchor[c], axis=1).min() > dist[c])), None)
            if k is None:
                continue
            vbox[key][fi] = box[k]
            kp = all_kp[k]
            vkp[key][fi] = np.column_stack([kp[:, 0] / s + x0, kp[:, 1] / s + y0, kp[:, 2]])
        pending.clear()

    for fi in range(n):
        ok, image = cap.read()
        if not ok:
            break
        for key, s in smooth.items():
            li, u, v, stand_px = s["virtual"][fi]
            if s["have"][fi] or np.isnan(li):
                continue
            half, mid = 0.75 * stand_px, v - 0.3 * stand_px
            x0, x1 = int(max(0, u - half)), int(min(size[0], u + half))
            y0, y1 = int(max(0, mid - half)), int(min(size[1], mid + half))
            crop = image[int(li) * size[1] + y0:int(li) * size[1] + y1, x0:x1]
            if crop.shape[0] >= 12 and crop.shape[1] >= 12:
                scale = CROP_HEIGHT / crop.shape[0]
                pending.append((key, fi, x0, y0, scale, cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC), (li, u, v, stand_px)))
            if len(pending) >= 64:
                flush()
    flush()
    np.savez_compressed(cache_path, stamp=stamp, **{f"kp|{k[0]}|{k[1]}": v for k, v in vkp.items()}, **{f"vb|{k[0]}|{k[1]}": v for k, v in vbox.items()})
    return vkp, vbox


def gather_joints(run, observed, smooth) -> Joints:
    """Stufe 3: Gelenkpunkte aus den Boxen und, wo keine Box ist, aus der Suche im Ausschnitt."""
    kp2d, body = read_keypoints(run, observed, smooth)
    vkp, vbox = search_without_box(run, observed, smooth)
    run.clock("Gelenkpunkte und Suche ohne Box")
    boxed = {key: ~np.isnan(k[:, 0, 0]) for key, k in kp2d.items()}  # Bilder mit Gelenkpunkten aus einer eigenen Box
    for key in smooth:
        there = ~np.isnan(vbox[key][:, 0])
        kp2d[key][there] = vkp[key][there]
    return Joints(kp2d, boxed, body, vbox)


def fill_gaps(run, observed, smooth, heights, joints: Joints) -> None:
    """Stufe 4a: Bilder ohne Detektor-Box: Lage aus der Box der Gelenkpunkt-Erkennung. Wo auch die nichts findet, gilt der
    Spieler als liegend, wenn er unmittelbar davor oder danach lag, beiderseits tief war und sich in der Lücke kaum bewegt hat
    (sonst ist er nur verdeckt). Ändert smooth."""
    n, fps, cam, where, vbox = run.n, run.fps, run.cam, observed.where, joints.vbox
    for key, s in smooth.items():
        found = np.flatnonzero(~np.isnan(vbox[key][:, 0]))
        for li in (0, 1):
            idx = found[s["virtual"][found, 0] == li]
            if len(idx):
                box = vbox[key][idx]
                tall = box_metres(cam, LENSES[li], box)[:, 2]
                down, low = posture(tall, box[:, 2] - box[:, 0], box[:, 3] - box[:, 1], heights[key])
                s["down"][idx], s["low"][idx], s["lens"][idx] = down, low, li
                s["share"][idx] = tall * BOX_TO_BODY / heights[key]
        known = s["have"].copy()
        known[found] = True
        for a, b in segments(~known & ~np.isnan(s["virtual"][:, 0]), 1):
            near = s["down"][max(0, a - 20):a].any() or s["down"][b:b + 20].any()
            left = a == 0 or s["low"][max(0, a - 45):a].any()
            right = b == n or s["low"][b:b + 45].any()
            way = np.linalg.norm(where[b - 1][key] - where[a][key]) / max((b - a) / fps, 0.2)
            if near and left and right and way < 2.0:
                s["down"][a:b] = s["low"][a:b] = True
                s["lens"][a:b] = s["virtual"][a:b, 0]


def floor_poses(run, observed, smooth, heights, joints: Joints) -> dict:
    """Stufe 4b: Spieler am Boden. Eine Bodenphase ist ein zusammenhängendes Stück, in dem der Spieler tief ist und
    mindestens einmal liegt: fallen, liegen, aufsetzen, aufstehen. Darin wird die Haltung als Seitenansicht aus den
    Gelenkpunkten gelesen, über die Zeit beruhigt, Lücken werden gehalten. Setzt smooth[key]["floor"].
    Rückgabe: Spieler -> Feld (Bilder, 17, 3) H36M-Gelenke, NaN außerhalb der Bodenphasen oder wo nichts erkannt."""
    n, cam, where, obs = run.n, run.cam, observed.where, observed.obs
    kp2d, vbox = joints.kp2d, joints.vbox
    floor = {}
    for key, s in smooth.items():
        s["floor"] = np.zeros(n, bool)
        for a, b in segments(s["low"], 1):
            # nur echtes Liegen zählt (mindestens MIN_DOWN Bilder am Stück), und die Phase reicht höchstens
            # AROUND Bilder davor und danach: so lange dauern Fallen und Aufstehen
            for c, e in segments(s["down"][a:b], MIN_DOWN):
                s["floor"][max(a, a + c - AROUND):min(b, a + e + AROUND)] = True
        if not s["floor"].any():
            continue
        widths = pose_limits.bone_lengths(heights[key])
        g = np.full((n, 17, 3), np.nan)
        for a, b in segments(s["floor"], 1):
            usable = [fi for fi in range(a, b) if key in where[fi] and not np.isnan(kp2d[key][fi, 0, 2])]
            # Welche Körperseite hinten liegt, ist aus einem Blickwinkel nicht zu sehen. Annahme: die Seite,
            # deren Gelenke über die Bodenphase schlechter erkannt werden.
            sides = np.array([kp2d[key][fi, :, 2] for fi in usable]).reshape(-1, 17)
            left_far = bool(len(sides) and sides[:, [5, 7, 9, 11, 13, 15]].mean() < sides[:, [6, 8, 10, 12, 14, 16]].mean())
            for fi in usable:
                li = int(s["lens"][fi])
                pose = side_pose(kp2d[key][fi], LENSES[li], cam, where[fi][key], widths, left_far)
                if pose is None:
                    continue
                # Die Haltung darf nicht höher reichen als die Box, aus der sie stammt (sonst gehören die
                # Gelenkpunkte einem stehenden Nachbarn).
                box = obs[key][fi, 1:5] if s["have"][fi] else vbox[key][fi]
                if pose[:, 2].max() <= box_metres(cam, LENSES[li], box)[0, 2] * 1.35 + 0.15:
                    g[fi] = pose
        found = int((~np.isnan(g[:, 0, 0])).sum())
        for j in range(17):
            for a in range(3):
                g[:, j, a] = running_median(g[:, j, a], 5)
        g = hold(g, HOLD)
        g[~s["floor"]] = np.nan
        floor[key] = g
        print(f"{key[0]}-{key[1]}: Bodenphase über {int(s['floor'].sum())} Bilder ({int(s['down'].sum())} liegend), Gelenke erkannt in {found}", flush=True)
    return floor
