#!/usr/bin/env python3
"""Macht aus einer kurzen Veo-Szene Positionen und Körperhaltungen für den Viewer.

Ablauf (Erkennung aus tools/veo_detect.py + veo_colors.py, Gelenkpunkte aus tools/veo_keypoints.py):
  1. Boxen über die Zeit zu Folgen verketten und den Veo-Spuren zuordnen, also Rückennummern
     vergeben. Verglichen wird am Boden in Metern (Kameramodell aus tools/veo_camera.py).
  2. Position je Spieler selbst messen: Fußpunkt der Box am Boden, geglättet. Veo liefert nur
     noch die Rückennummer und füllt Lücken. Körpergröße aus der Boxhöhe.
  3. Je Spieler die 2D-Gelenkpunkte seiner Boxen einsammeln (ViTPose).
     Spieler am Boden (gefoult, gestürzt) erkennt die Box: sehr niedrig oder breiter als hoch.
     Der Personendetektor übersieht flach liegende Spieler oft ganz. Deshalb wird dort, wo ein
     Spieler keine Box hat, Veo aber seine Position weiterführt, in einem vergrößerten
     Ausschnitt trotzdem nach Gelenkpunkten gesucht. Die Haltung am Boden (fallen, liegen,
     aufsetzen, aufstehen) wird direkt aus den 2D-Gelenkpunkten als Seitenansicht gelesen.
  4. Haltung: Je Spieler wird die Bewegung gesucht, die im Kamerabild auf den Gelenkpunkten
     liegt und in allem, was das Bild offen lässt (Tiefe, verdeckte Gelenke, Lücken), einer
     natürlichen Bewegung im Takt der sichtbaren Schritte folgt (tools/pose_fit.py).
  5. Grenzen des Körpers (tools/pose_limits.py), Glättung, Boden: Jede Figur hat in jedem
     Bild ein vollständiges, mögliches Skelett. Stehende Füße bleiben an ihrer Stelle.

Grenzen: ein Blickwinkel, Spieler nur rund 55 Pixel hoch. Was quer zur Blickrichtung
geschieht, ist gemessen; die Tiefe der Haltung ist erschlossen. Füße stehen immer auf dem
Boden, Sprünge gehen verloren.

Aufruf:
    .venv/bin/python tools/veo_scene.py VEO_ORDNER KAMERA.json VEO_ALIGN.json VIDEO START_S DETEKTIONEN.json BASIS_SPIEL AUSGABE_SPIEL
Ohne Veo (eigenes Spielertracking aus tools/track_players.py, Spieler ohne Rückennummer): VEO_ORDNER und
VEO_ALIGN.json als "-". Vom BASIS_SPIEL werden dann nur Platz, Kulisse, Mannschaften und Uhr übernommen.
Die Teile ohne Veo (Spuren, Ball) stehen in tools/own_scene.py.
"""
import json
import math
import os
import shutil
import sys
import time
from array import array
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.signal import savgol_filter

sys.path.insert(0, str(Path(__file__).parent))
import pose_fit  # noqa: E402
import pose_limits  # noqa: E402
import veo_camera  # noqa: E402
import check_motion  # noqa: E402
import ground_motion  # noqa: E402
import track_limits  # noqa: E402
import veo_keypoints  # noqa: E402
import veo_tracks  # noqa: E402
from veo_keypoints import torso_colour  # noqa: E402
from own_scene import (BALL_GAP, BALL_REACH, MIN_APPEARANCE, OWN_GAP, attach_ball, drop_same_place, own_ball,  # noqa: E402
                       own_identities)
from synth_poses import BONES, JOINTS, NAMES  # noqa: E402

LENSES = ("left", "right")
GATE = 1.5            # Meter: Einzelzuordnung Veo-Position zu Fußpunkt
WIDE_GATE = 4.0       # Meter: so weit darf eine verkettete Box von der Veo-Position liegen
LINK = 0.35           # Verkettung: höchster Abstand zum Vorgänger, in Boxhöhen
MAX_MISS = 10         # Bilder, die eine Folge ohne Erkennung überlebt
VOTE_WINDOW = 45      # Bilder vor und zurück, deren Einzelzuordnungen über die Nummer abstimmen
MIN_VOTES = 3
CROP_HEIGHT = 384
MIN_SEGMENT = 24      # Spieler mit weniger zugeordneten Bildern werden nicht aus dem Video gelesen
SEEN_SHARE = 0.6      # Anteil erkannter Gelenke, ab dem ein Bild als "aus dem Video gelesen" zählt
DEFAULT_HEIGHT = 1.70
DOWN_HEIGHT = 0.4     # Box niedriger als dieser Anteil der Körpergröße: Spieler liegt
DOWN_WIDE = (1.1, 0.6)   # oder Box breiter als hoch (Verhältnis) und zugleich niedriger als dieser Anteil
LOW_HEIGHT = 0.8      # darunter gilt der Spieler als geduckt, kniend oder sitzend
DOWN_CONF = 0.3       # Mindestsicherheit eines Gelenkpunkts am Boden
HOLD = 60             # Bilder, über die die letzte erkannte Haltung am Boden gehalten wird
MIN_DOWN = 8          # Bilder am Stück, die ein Spieler liegen muss, damit es als Sturz gilt
AROUND = 45           # Bilder vor und nach dem Liegen, die noch zur Bodenphase gehören (fallen, aufstehen)
CACHE_VERSION = 6.0
BOX_TO_BODY = 0.93    # Boxen umfassen etwas mehr als den Körper (Unschärfe, Haare, Sohle); Abzug geschätzt, nicht gemessen
DEPTH_CALM = 36000.0  # Gewicht der Ruhe in Blickrichtung: Schwankungen des Abstands schneller als rund 0,3 Hz gelten als Rauschen
OUT_FPS = 25
POSE_SCALE, MISSING, CHUNK_FRAMES = 0.001, -32768, 1500


def running_median(values, window):
    half = window // 2
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return np.array([np.nanmedian(values[max(0, i - half):i + half + 1]) for i in range(len(values))])


def segments(mask, minimum):
    start = None
    for i, ok in enumerate(list(mask) + [False]):
        if ok and start is None:
            start = i
        elif not ok and start is not None:
            if i - start >= minimum:
                yield start, i
            start = None


def link_tracklets(frames, lens):
    """Verkettet die Boxen einer Linse von Bild zu Bild. Rückgabe: je Bild die Folgennummer je Box."""
    active, next_id, out = {}, 0, []  # nummer -> [bild, x, fußpunkt y, höhe, vx, vy, farbe]
    for fi, fr in enumerate(frames):
        b = np.array(fr[lens], float).reshape(-1, 6)
        cur = np.full(len(b), -1, int)
        c = np.column_stack([(b[:, 0] + b[:, 2]) / 2, b[:, 3]])
        h = b[:, 3] - b[:, 1]
        live = [(k, a) for k, a in active.items() if fi - a[0] <= MAX_MISS]
        active = dict(live)
        if len(b) and live:
            a = np.array([v for _, v in live])
            dt = fi - a[:, 0]
            pred = a[:, 1:3] + a[:, 4:6] * dt[:, None]
            cost = np.linalg.norm(pred[:, None] - c[None], axis=2) / a[:, 3:4]
            cost += 0.15 * (a[:, 6:7] != b[:, 5][None])
            cost[np.abs(np.log(h[None] / a[:, 3:4])) > 0.4] = 9
            r, cc = linear_sum_assignment(np.minimum(cost, 2 * LINK))
            for i, j in zip(r, cc):
                if cost[i, j] < LINK:
                    cur[j] = live[i][0]
        for j in range(len(b)):
            v = np.zeros(2)
            if cur[j] < 0:
                cur[j], next_id = next_id, next_id + 1
            else:
                old = active[cur[j]]
                v = 0.5 * old[4:6] + 0.5 * (c[j] - old[1:3]) / (fi - old[0])
            active[cur[j]] = np.array([fi, c[j, 0], c[j, 1], h[j], v[0], v[1], b[j, 5]])
        out.append(cur)
    return out


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


def box_metres(cam, lens, boxes):
    """Fußpunkt am Boden (x, y) und Höhe in Metern je Box (Strahl durch die Oberkante, geschnitten über dem Fußpunkt)."""
    b = np.asarray(boxes, float).reshape(-1, 4)
    centre = (b[:, 0] + b[:, 2]) / 2
    out = np.full((len(b), 3), np.nan)
    out[:, :2] = veo_camera.to_ground(cam, lens, np.column_stack([centre, b[:, 3]]))[0]
    ray = veo_camera.rays(cam, lens, np.column_stack([centre, b[:, 1]]))
    reach = np.linalg.norm(out[:, :2] - cam["position"][:2], axis=1)
    out[:, 2] = cam["position"][2] + ray[:, 2] * reach / np.maximum(np.linalg.norm(ray[:, :2], axis=1), 1e-9)
    return out


def posture(height_m, width_px, height_px, body_height):
    """Aus Boxmaßen: liegt der Spieler, und ist er zumindest tief (geduckt, kniend, sitzend)?"""
    share = height_m * BOX_TO_BODY / body_height
    with np.errstate(invalid="ignore", divide="ignore"):
        down = (share < DOWN_HEIGHT) | ((width_px / height_px > DOWN_WIDE[0]) & (share < DOWN_WIDE[1]))
        low = share < LOW_HEIGHT
    return down, low | down


def hold(values, limit):
    """Füllt Lücken (NaN) entlang der Zeit mit dem nächstgelegenen gültigen Bild, höchstens limit Bilder weit."""
    out = values.copy()
    good = np.flatnonzero(~np.isnan(values.reshape(len(values), -1)[:, 0]))
    if not len(good):
        return out
    for i in np.flatnonzero(np.isnan(values.reshape(len(values), -1)[:, 0])):
        j = good[np.argmin(np.abs(good - i))]
        if abs(j - i) <= limit:
            out[i] = values[j]
    return out


def feet_on_ground(cam, eye, kp, lens, height):
    """Bodenpunkt unter dem Becken aus Gelenkpunkten (n, 17, 3); NaN, wo Hüften oder Knöchel nicht sicher erkannt sind.

    Ein Fuß in der Luft erscheint weiter weg, als er ist. Der Abstand zur Kamera kommt deshalb vom näheren
    der beiden Knöchel (der steht), der andere zählt höchstens 0,2 m mit."""
    out = np.full((len(kp), 2), np.nan)
    ankle_height, hip_height = 0.07 * height / 1.70, 0.51 * height
    for li, name in enumerate(LENSES):
        m = (lens == li) & (np.nan_to_num(kp[:, [11, 12, 15, 16], 2]) >= 0.5).all(axis=1)
        if not m.any():
            continue
        reach = np.stack([np.linalg.norm(veo_camera.to_ground(cam, name, kp[m, a, :2], ankle_height)[0] - eye[:2], axis=1) for a in (15, 16)])
        near, far = np.nanmin(reach, axis=0), np.nanmax(reach, axis=0)
        distance = near + np.minimum((far - near) / 2, 0.2)
        hips = veo_camera.to_ground(cam, name, (kp[m, 11, :2] + kp[m, 12, :2]) / 2, hip_height)[0] - eye[:2]
        out[m] = eye[:2] + hips / np.maximum(np.linalg.norm(hips, axis=1, keepdims=True), 1e-9) * distance[:, None]
    return out


def smooth_track(pos, eye, sideways=True):
    """Glättet eine Bahn (n, 2), in Blickrichtung der Kamera viel stärker als quer dazu.

    Ein Pixel im Bild sind quer zur Blickrichtung wenige Zentimeter, in die Tiefe aber rund 0,3 m: Der Abstand
    zur Kamera ist viel ungenauer gemessen als die seitliche Lage. In Blickrichtung gilt deshalb die ruhigste
    Bahn, die zu den Messungen passt (gleichmäßiges Tempo bleibt erhalten, Beschleunigungen werden über gut
    eine Sekunde verteilt); sonst käme aus dem Messrauschen ein Hin und Her, in das sich die Figur legen müsste."""
    if len(pos) < 9:
        return pos
    rel = pos - eye[:2]
    reach, angle = np.linalg.norm(rel, axis=1), np.unwrap(np.arctan2(rel[:, 1], rel[:, 0]))
    reach = track_limits._solve(reach, np.full(len(pos) - 2, DEPTH_CALM), np.zeros(len(pos) - 1))
    if sideways:
        angle = savgol_filter(angle, min(15, len(pos) // 2 * 2 - 1), 2)
    return eye[:2] + reach[:, None] * np.column_stack([np.cos(angle), np.sin(angle)])


def resample(values, n_out, ratio):
    """Lineares Umrechnen einer Bildfolge (n, ...) auf n_out Bilder; Bild i der Ausgabe liegt bei i * ratio. NaN bleibt NaN."""
    src = np.arange(n_out) * ratio
    a = np.minimum(src.astype(int), len(values) - 1)
    b = np.minimum(a + 1, len(values) - 1)
    w = (src - a).reshape(-1, *([1] * (values.ndim - 1)))
    return values[a] + (values[b] - values[a]) * w


def resample_keypoints(kp, lens, n_out, ratio):
    """Gelenkpunkte (n, 17, 3) und Linse (n,) auf n_out Bilder umrechnen; Bild i der Ausgabe liegt bei i * ratio.

    Zwischen zwei erkannten Bildern derselben Linse wird gemittelt, sonst das nähere genommen."""
    src = np.arange(n_out) * ratio
    a = np.minimum(src.astype(int), len(kp) - 1)
    b = np.minimum(a + 1, len(kp) - 1)
    w = src - a
    ok_a, ok_b = ~np.isnan(kp[a, 0, 0]) & ~np.isnan(lens[a]), ~np.isnan(kp[b, 0, 0]) & ~np.isnan(lens[b])
    near = np.where((w < 0.5) | ~ok_b, a, b)
    out, lens_out = kp[near].copy(), lens[near].copy()
    both = ok_a & ok_b & (lens[a] == lens[b])
    mixed = kp[a] * (1 - w)[:, None, None] + kp[b] * w[:, None, None]
    mixed[:, :, 2] = np.minimum(kp[a, :, 2], kp[b, :, 2])
    out[both] = mixed[both]
    none = ~(ok_a | ok_b) | np.isnan(out[:, 0, 0])
    out[none], lens_out[none] = np.nan, np.nan
    return out, lens_out


def main(veo_dir, camera_path, align_path, video, start, det_path, base_dir, out_dir):
    began = time.time()

    def clock(label):
        print(f"  [{time.time() - began:.0f} s] {label}", flush=True)
    cam = veo_camera.load(camera_path)
    no_veo = align_path == "-"     # ohne Veo: eigenes Spielertracking
    if not no_veo:
        align = json.loads(Path(align_path).read_text())
        tracks = veo_tracks.build_tracks(veo_tracks.load_export(veo_dir), align["H"])
    det = json.loads(Path(det_path).read_text())
    size, start, fps, frames = cam["lensSize"], float(start), det["fps"], det["frames"]
    n = len(frames)
    L, W = cam["pitch"]["length"], cam["pitch"]["width"]
    cam_pos = cam["position"]

    # 1. Boxen verketten, Einzelzuordnungen am Boden als Stimmen sammeln, je Folge und Zeitfenster
    #    die Mehrheit nehmen -> obs[(team, nummer)][bild] = (linse, x1, y1, x2, y2, bodenX, bodenY, größe)
    chain = [link_tracklets(frames, lens) for lens in LENSES]
    votes, where, ground, direct = [{}, {}], [], [], 0
    for fi, fr in enumerate(frames):
        if not no_veo:
            people = veo_tracks.positions_at(tracks, start + fr["t"] + align["timeOffsetS"])
            where.append({(tracks[t]["team"], tracks[t]["jersey"]): p for t, p in people})
        per_lens = []
        for li, lens in enumerate(LENSES):
            b = np.array(fr[lens], float).reshape(-1, 6)
            g = np.full((len(b), 3), np.nan)
            if len(b):
                centre = (b[:, 0] + b[:, 2]) / 2
                g[:, :2], dist = veo_camera.to_ground(cam, lens, np.column_stack([centre, b[:, 3]]))
                g[(np.abs(g[:, 0]) > L / 2 + 5) | (np.abs(g[:, 1]) > W / 2 + 5)] = np.nan
                # Körpergröße: Strahl durch die Boxoberkante, geschnitten über dem Fußpunkt
                ray = veo_camera.rays(cam, lens, np.column_stack([centre, b[:, 1]]))
                reach = np.linalg.norm(g[:, :2] - cam_pos[:2], axis=1)
                g[:, 2] = cam_pos[2] + ray[:, 2] * reach / np.maximum(np.linalg.norm(ray[:, :2], axis=1), 1e-9)
                if not no_veo:
                    for tid, j, _ in veo_tracks.assign_ground(people, tracks, g[:, :2], b[:, 5], GATE):
                        votes[li].setdefault(int(chain[li][fi][j]), {})[fi] = (tracks[tid]["team"], tracks[tid]["jersey"])
            per_lens.append(g)
        ground.append(per_lens)
    best = [{} for _ in range(n)]
    for li, lens in enumerate(LENSES):
        members = {}
        for fi, ids in enumerate(chain[li]):
            for j, t in enumerate(ids):
                members.setdefault(int(t), []).append((fi, j))
        for t, items in members.items():
            v = votes[li].get(t)
            if not v:
                continue
            vf = np.array(sorted(v))
            vk = [v[f] for f in vf]
            for fi, j in items:
                lo, hi = np.searchsorted(vf, [fi - VOTE_WINDOW, fi + VOTE_WINDOW + 1])
                if hi - lo < MIN_VOTES:
                    continue
                key, count = Counter(vk[lo:hi]).most_common(1)[0]
                g = ground[fi][li][j]
                if count < 0.6 * (hi - lo) or key[1] < 0 or key not in where[fi] or np.isnan(g[0]):
                    continue
                dist = float(np.linalg.norm(g[:2] - where[fi][key]))
                if dist > WIDE_GATE:
                    continue
                if key not in best[fi] or dist < best[fi][key][0]:
                    best[fi][key] = (dist, li, *frames[fi][lens][j][:4], *g, j, v.get(fi) == key)
    obs = {}
    for fi in range(n):
        for key, row in best[fi].items():
            obs.setdefault(key, np.full((n, 9), np.nan))[fi] = row[1:10]   # letzte Spalte: Nummer der Box im Bild
            direct += bool(row[10])
    total_boxes = sum(len(b) for b in best)
    if no_veo:
        # Eigene Spuren: Zuordnung Box -> Spieler direkt aus dem Tracking; „where“ ist die eigene Spur, über
        # Lücken gerade verbunden (dort wird wie bisher in vergrößerten Ausschnitten nach Liegenden gesucht).
        identities = own_identities(det, cam, n, video)
        own_kit, keepers = {}, set()
        where = [{} for _ in range(n)]
        for key, (colour, keeper, items) in identities.items():
            rows = np.full((n, 9), np.nan)
            for fi, r in items.items():
                li, j = int(r[3]), int(r[8])
                g = ground[fi][li][j]
                if np.isnan(g[0]):
                    continue
                rows[fi] = (li, *frames[fi][LENSES[li]][j][:4], *g, j)
            seen = np.flatnonzero(~np.isnan(rows[:, 0]))
            if len(seen) < 2:
                continue
            obs[key] = rows
            own_kit[key] = colour if not keeper else -1
            if keeper:
                keepers.add(key)
            # Lücken bis OWN_GAP gerade verbinden; über längere Lücken ist der Spieler nicht da (er steckt dann oft in einer anderen Spur)
            bridged = np.zeros(n, bool)
            bridged[seen] = True
            for a, b in zip(seen[:-1], seen[1:]):
                if b - a <= OWN_GAP * fps:
                    bridged[a:b] = True
            for fi in np.flatnonzero(bridged):
                where[fi][key] = np.array([np.interp(fi, seen, rows[seen, 5]), np.interp(fi, seen, rows[seen, 6])])
        removed = drop_same_place(obs, where)   # zwei Spuren an derselben Stelle sind eine Person
        total_boxes = int(sum((~np.isnan(b[:, 0])).sum() for b in obs.values()))
        print(f"Doppelte Spuren an derselben Stelle: {removed} Spieler-Bilder entfernt", flush=True)
        print(f"Eigenes Tracking: {len(obs)} Spuren auf dem Platz ({dict(Counter(k[0] for k in obs))}, davon {len(keepers)} Torwart), "
              f"{total_boxes} Boxen zugeordnet", flush=True)
    else:
        veo_error = np.array([row[0] for b in best for row in b.values()])
        print(f"{total_boxes} Boxen mit Rückennummer, davon {total_boxes - direct} nur über die Verkettung; "
              f"Abstand Veo-Position zu unserem Fußpunkt: Median {np.median(veo_error):.2f} m, 90 % unter {np.percentile(veo_error, 90):.2f} m", flush=True)

    # 2. Ausreißer entfernen (Box springt zu einem Nachbarn), Mitte und Höhe glätten
    smooth, heights = {}, {}
    for key, b in obs.items():
        cx, cy, h = (b[:, 1] + b[:, 3]) / 2, (b[:, 2] + b[:, 4]) / 2, b[:, 4] - b[:, 2]
        for li in (0, 1):  # Linsenwechsel verschiebt die Pixelkoordinaten: je Linse getrennt beurteilen
            m = b[:, 0] == li
            if m.sum() < 5:
                b[m] = np.nan
                continue
            mx = running_median(np.where(m, cx, np.nan), 21)
            my = running_median(np.where(m, cy, np.nan), 21)
            mh = running_median(np.where(m, h, np.nan), 31)
            # Die Boxhöhe selbst ist kein Ausreißermerkmal: Wer fällt, wird in wenigen Bildern niedrig.
            bad = m & (np.hypot(cx - mx, cy - my) > 0.6 * mh)
            b[bad] = np.nan
        have = ~np.isnan(b[:, 0])
        if have.sum() < MIN_SEGMENT:
            b[:] = np.nan
            continue
        cx, cy, h, w = (b[:, 1] + b[:, 3]) / 2, (b[:, 2] + b[:, 4]) / 2, b[:, 4] - b[:, 2], b[:, 3] - b[:, 1]
        heights[key] = float(np.clip(np.nanpercentile(b[:, 7], 60) * BOX_TO_BODY, 1.45, 1.95))
        # Höhe in Pixeln, die der Spieler an dieser Stelle stehend hätte
        stand = np.full(n, np.nan)
        for li, lens in enumerate(LENSES):
            m = b[:, 0] == li
            if m.any():
                foot = np.column_stack([b[m, 5:7], np.zeros(m.sum())])
                top = foot + [0, 0, heights[key] / BOX_TO_BODY]
                stand[m] = np.abs(veo_camera.project(cam, lens, top)[:, 1] - veo_camera.project(cam, lens, foot)[:, 1])
        # am Boden: Box sehr niedrig oder breiter als hoch; über ein paar Bilder beruhigt
        down, low = posture(b[:, 7], w, h, heights[key])
        share = running_median(np.where(have, b[:, 7] * BOX_TO_BODY / heights[key], np.nan), 5)   # Höhe des Körpers als Anteil der Körpergröße
        down = running_median(np.where(have, down.astype(float), np.nan), 7) > 0.5
        low = running_median(np.where(have, low.astype(float), np.nan), 7) > 0.5
        if key[0] != "referee":
            # Bilder ohne Box, in denen Veo die Position weiterführt: Linse, erwarteter Fußpunkt (u, v), Stehhöhe in Pixeln
            virtual = np.full((n, 4), np.nan)
            for fi in np.flatnonzero(~have):
                spot = where[fi].get(key)
                if spot is None:
                    continue
                margin = 5.0
                for li, lens in enumerate(LENSES):
                    uv = veo_camera.project(cam, lens, [[spot[0], spot[1], 0], [spot[0], spot[1], heights[key] / BOX_TO_BODY]])
                    inside = min(uv[0, 0], size[0] - uv[0, 0], uv[0, 1], size[1] - uv[0, 1])
                    if not np.isnan(uv).any() and inside > margin:
                        virtual[fi], margin = (li, uv[0, 0], uv[0, 1], abs(uv[1, 1] - uv[0, 1])), inside
            smooth[key] = {"lens": b[:, 0].copy(), "cx": cx, "cy": cy, "h": running_median(h, 31), "w": running_median(w, 5),
                           "stand": stand, "have": have, "down": down & have, "low": (low | down) & have, "virtual": virtual, "share": share}
    print(f"{len(smooth)} Spieler mit Boxfolge; im Mittel in {np.mean([s['have'].mean() for s in smooth.values()]):.0%} der Bilder zugeordnet", flush=True)
    print("Körpergröße aus der Boxhöhe (m):", {f"{k[0]}-{k[1]}": round(v, 2) for k, v in sorted(heights.items())}, flush=True)

    clock("Boxen zugeordnet")
    # 3. Gelenkpunkte je Spieler. Für jede Box liegen sie aus tools/veo_keypoints.py vor (einmal je Szene gerechnet).
    #    Liegen die Punkte auf einem Spieler in fremdem Trikot (Zweikampf, Verdeckung), werden sie verworfen.
    kp_path = Path(str(det_path) + ".keypoints.npz")
    if not kp_path.exists() or kp_path.stat().st_mtime < Path(det_path).stat().st_mtime:
        veo_keypoints.main(video, det_path, camera_path, out_path=str(kp_path))
    with np.load(kp_path) as archive:
        found = {name: archive[name] for name in archive.files}
    kit = own_kit if no_veo else {(tr["team"], tr["jersey"]): tr["cls"] for tr in tracks.values()}  # Farbklasse des Trikots je Spieler
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

    #    Bilder ohne Box, in denen Veo die Position weiterführt: im vergrößerten Ausschnitt nach einer Person
    #    im eigenen Trikot suchen (für Spieler am Boden). Das ist teuer und wird neben den Erkennungen gemerkt.
    stamp = [Path(x).stat().st_mtime for x in (det_path, camera_path) + (() if no_veo else (align_path,))] + [float(total_boxes), CACHE_VERSION, float(no_veo)]
    # je Bild und Linse: wo jeder Spieler im Bild erwartet wird (Unterkante seiner Box oder Veo-Position)
    expected = [({}, {}) for _ in range(n)]
    for key, b in obs.items():
        for fi in np.flatnonzero(~np.isnan(b[:, 0])):
            wide = b[fi, 3] - b[fi, 1] > b[fi, 4] - b[fi, 2]
            expected[fi][int(b[fi, 0])][key] = ((b[fi, 1] + b[fi, 3]) / 2, (b[fi, 2] + b[fi, 4]) / 2 if wide else b[fi, 4])
    for key, v in smooth.items():
        for fi in np.flatnonzero(~np.isnan(v["virtual"][:, 0])):
            expected[fi][int(v["virtual"][fi, 0])][key] = tuple(v["virtual"][fi, 1:3])
    cache_path = Path(str(det_path) + (".virtual_own.npz" if no_veo else ".virtual.npz"))
    cached = np.load(cache_path) if cache_path.exists() else None
    if cached is not None and len(cached["stamp"]) == len(stamp) and np.allclose(cached["stamp"], stamp):
        split = lambda k: (k.split("|")[1], int(k.split("|")[2]))  # noqa: E731
        vkp = {split(k): cached[k] for k in cached.files if k.startswith("kp|")}
        vbox = {split(k): cached[k] for k in cached.files if k.startswith("vb|")}
        print(f"Suche in Bildern ohne Box aus {cache_path} übernommen", flush=True)
    else:
        from ultralytics import YOLO
        model = YOLO("models/yolo11x-pose.pt")
        vkp = {key: np.full((n, 17, 3), np.nan) for key in smooth}
        vbox = {key: np.full((n, 4), np.nan) for key in smooth}  # Box der gefundenen Person
        cap = cv2.VideoCapture(video)
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
    clock("Gelenkpunkte und Suche ohne Box")
    boxed = {key: ~np.isnan(k[:, 0, 0]) for key, k in kp2d.items()}  # Bilder mit Gelenkpunkten aus einer eigenen Box
    for key in smooth:
        there = ~np.isnan(vbox[key][:, 0])
        kp2d[key][there] = vkp[key][there]

    # 4a. Bilder ohne Detektor-Box: Lage aus der Box der Gelenkpunkt-Erkennung. Wo auch die nichts findet,
    #     gilt der Spieler als liegend, wenn er unmittelbar davor oder danach lag, beiderseits tief war
    #     und sich in der Lücke kaum bewegt hat (sonst ist er nur verdeckt).
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
    # 4b. Spieler am Boden. Eine Bodenphase ist ein zusammenhängendes Stück, in dem der Spieler tief ist und
    #     mindestens einmal liegt: fallen, liegen, aufsetzen, aufstehen. Darin wird die Haltung als
    #     Seitenansicht aus den Gelenkpunkten gelesen, über die Zeit beruhigt, Lücken werden gehalten.
    floor = {}  # key -> (n, 17, 3) H36M-Gelenke im Feld, NaN außerhalb der Bodenphasen oder wo nichts erkannt
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

    # Spielstand der Szene aus dem Basisspiel (Veo-Positionen, 25 Hz)
    base_dir, out_dir = Path(base_dir), Path(out_dir)
    base = json.loads((base_dir / "meta.json").read_text())
    E = len(base["entities"])
    period = next(p for p in base["periods"] if p["videoStartS"] <= start <= p["videoStartS"] + (p["endFrame"] - p["startFrame"]) / base["fps"])
    first = period["startFrame"] + round((start - period["videoStartS"]) * base["fps"])
    total = int(n / fps * OUT_FPS)
    ratio = fps / OUT_FPS
    data = array("h")
    with open(base_dir / base["tracks"]["file"], "rb") as f:
        f.seek(first * E * 3 * 2)
        data.fromfile(f, total * E * 3)
    tscale = base["tracks"]["scale"]
    xy = np.array(data, float).reshape(total, E, 3)
    xy = np.where(xy == base["tracks"]["missing"], np.nan, xy * tscale)[:, :, :2]
    if no_veo:
        # Ohne Veo: Spieler sind die eigenen Spuren, ihre Lage die eigene Spur (Lücken gerade verbunden); dazu der Ball.
        # Vom Basisspiel bleiben nur Platz, Kulisse, Mannschaftsnamen und Uhr.
        entities = []
        names = Counter()
        for key in sorted(obs, key=lambda k: (k[0], k[1])):
            names[key[0]] += 1
            entity = {"id": f"{key[0]}-{key[1]}", "kind": "player", "team": key[0], "label": "TW" if key in keepers else f"S{names[key[0]]}"}
            if key in keepers:
                entity["role"] = "goalkeeper"
            entities.append(entity)
        entities.append({"id": "ball", "kind": "ball"})
        base["entities"] = entities
        E = len(entities)
        data = array("h", [base["tracks"]["missing"]]) * (total * E * 3)
        xy = np.full((total, E, 2), np.nan)
        for i, key in enumerate(sorted(obs, key=lambda k: (k[0], k[1]))):
            spot = np.full((n, 2), np.nan)
            for fi, p in ((fi, where[fi][key]) for fi in range(n) if key in where[fi]):
                spot[fi] = p
            xy[:, i] = resample(spot, total, ratio)
    slots = [i for i, e in enumerate(base["entities"]) if e["kind"] == "player"]
    entity_of = {e["id"]: i for i, e in enumerate(base["entities"])}
    ball = next((i for i, e in enumerate(base["entities"]) if e["kind"] == "ball"), None)
    ball_source = "Veo"
    if ball is not None and Path(f"{det_path}.ball.npz").exists():   # eigener Ball aus dem Video (tools/veo_ball.py) statt Veos
        xy[:, ball] = own_ball(resample(np.load(f"{det_path}.ball.npz")["pos"], total, ratio), BALL_GAP * OUT_FPS)
        ball_source = "Video"

    # 2b. Eigene Position: Fußpunkt am Boden. Veo füllt die Lücken, verschoben um den zuletzt
    #     gemessenen Unterschied, damit nichts springt.
    veo_speed, own_speed, measured_share, refined = [], [], {}, 0
    for key, b in obs.items():
        entity = entity_of.get(f"{key[0]}-{key[1]}")
        if entity is None or np.isnan(b[:, 5]).all():
            continue
        point = b[:, 5:7].copy()
        # Genauer als die Unterkante der Box (die oft einen Nachbarn mit umfasst) sind die Gelenkpunkte: seitliche Lage
        # aus der Hüftmitte, Abstand zur Kamera aus dem Fuß, der auf dem Rasen steht.
        if key in kp2d:
            feet = feet_on_ground(cam, cam_pos, kp2d[key], b[:, 0], body.get(key, DEFAULT_HEIGHT))
            better = boxed[key] & ~np.isnan(feet[:, 0]) & (np.linalg.norm(feet - point, axis=1) < 3.0)
            point[better] = feet[better]
            refined += int(better.sum())
        if key in floor:  # am Boden zählt das Becken, nicht die Unterkante der Box
            lying = ~np.isnan(floor[key][:, 0, 0])
            point[lying] = floor[key][lying, 0, :2]
        own = resample(point, total, ratio)
        veo = xy[:, entity].copy()
        offset = own - veo
        for a in range(2):
            m = running_median(offset[:, a], 9)
            offset[np.abs(offset[:, a] - m) > 1.5, :] = np.nan
        seen = ~np.isnan(offset[:, 0])
        if seen.sum() < 5:
            continue
        idx = np.arange(total)
        offset = np.column_stack([np.interp(idx, idx[seen], offset[seen, a]) for a in range(2)])
        pos = veo + offset
        there = ~np.isnan(pos[:, 0])
        for a, e in segments(there, 9):
            pos[a:e] = track_limits.physical(smooth_track(pos[a:e], cam_pos), OUT_FPS)
            if e - a > 15:
                step = int(OUT_FPS * 0.4)
                veo_speed.append(np.linalg.norm(veo[a + step:e] - veo[a:e - step], axis=1) / 0.4)
                own_speed.append(np.linalg.norm(pos[a + step:e] - pos[a:e - step], axis=1) / 0.4)
        xy[:, entity] = pos
        measured_share[key] = seen.mean()
    for i in slots:
        if not any(entity_of.get(f"{k[0]}-{k[1]}") == i for k in measured_share):
            xy[:, i] = track_limits.clean(xy[:, i], OUT_FPS)
    print(f"Position in {refined} Bildern aus den Gelenkpunkten statt aus der Box bestimmt", flush=True)
    if own_speed:
        v, o = np.concatenate(veo_speed), np.concatenate(own_speed)
        print(f"Tempo über 0,4 s gemittelt, {len(measured_share)} Spieler: höchstes laut Veo {np.nanmax(v) * 3.6:.1f} km/h, "
              f"aus eigenen Positionen {np.nanmax(o) * 3.6:.1f} km/h; 99. Perzentil {np.nanpercentile(v, 99) * 3.6:.1f} und {np.nanpercentile(o, 99) * 3.6:.1f} km/h", flush=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    clock("Positionen")

    # 4./5. Haltung je Spieler: natürliche Bewegung entlang seiner Bahn, im Kamerabild an die Gelenkpunkte
    #       angepasst; danach Grenzen des Körpers, Glättung, Boden.
    J = len(JOINTS)
    buf = array("h", [MISSING]) * (math.ceil(total / CHUNK_FRAMES) * CHUNK_FRAMES * len(slots) * J * 3)
    ball_xy = xy[:, ball] if ball is not None else None
    median_height = float(np.median(list(body.values()))) if body else DEFAULT_HEIGHT
    stats, estimated, present_total, summary = Counter(), 0, 0, {}
    slip_before = slip_after = slip_frames = grounded = backward_frames = 0
    errors, views, toes = [], {}, []
    step = max(1, round(0.2 * OUT_FPS))
    nearest = np.minimum(np.round(np.arange(total) * ratio).astype(int), n - 1)
    for slot, entity in enumerate(slots):
        pos = xy[:, entity].copy()
        for a, b in segments(~np.isnan(pos[:, 0]), 1):   # Auftritte unter einer halben Sekunde: keine Figur (zu kurz für eine Haltung)
            if b - a < MIN_APPEARANCE * OUT_FPS:
                pos[a:b] = np.nan
        xy[:, entity] = pos
        present = ~np.isnan(pos[:, 0])
        if not present.any():
            continue
        e = base["entities"][entity]
        key = (e["team"], int(e["id"].rsplit("-", 1)[1])) if no_veo else (e["team"], e["number"]) if "label" not in e else None
        lengths = pose_limits.bone_lengths(body.get(key, median_height))
        down, low, seen, h36 = np.zeros(total, bool), np.zeros(total, bool), np.zeros(total), None
        if key in smooth:
            low, down = smooth[key]["low"][nearest], smooth[key]["floor"][nearest]
            points = np.where(boxed[key][:, None, None], kp2d[key], np.nan)
            kp_out, lens_out = resample_keypoints(points, obs[key][:, 0], total, ratio)
            target, weight = pose_fit.targets(kp_out)
            ref, A = pose_fit.linearize(cam, lens_out, pos)
            weight[down | ~present | np.isnan(ref[:, 0])] = 0
            views[e["id"]] = {"kp": kp_out.astype(np.float32), "lens": lens_out.astype(np.float32), "down": down,
                              "lying": smooth[key]["down"][nearest], "share": smooth[key]["share"][nearest].astype(np.float32)}
            if os.environ.get("MATCHSPACE_DEBUG"):  # Eingaben der Anpassung zum Nachstellen
                np.savez(f"{os.environ['MATCHSPACE_DEBUG']}.{e['id']}.npz", kp=kp_out, lens=lens_out, pos=pos, ball=ball_xy, down=down, low=low,
                         height=body.get(key, median_height), present=present)
            motion, backwards = pose_fit.natural_motion(pos, ball_xy, OUT_FPS, lengths, target, weight, A)
            lean = np.where(down, math.pi, np.where(low, math.radians(70), pose_limits.MAX_LEAN))
            result = pose_fit.fit(target, weight, ref, A, pos, cam_pos, lengths, motion, lean)
            pos = pos + result["shift"]
            for a, b in segments(present, 9):   # die Korrektur der Anpassung darf die Bahn nicht unruhig oder unmöglich machen
                pos[a:b] = track_limits.physical(smooth_track(pos[a:b], cam_pos, sideways=False), OUT_FPS)
            xy[:, entity] = pos
            h36, seen = result["h36m"], result["observed"]
            errors.append(result["error"])
            backward_frames += int((backwards & present).sum())
        else:
            motion, _ = pose_fit.natural_motion(pos, ball_xy, OUT_FPS, lengths, start_phase=slot * 1.7)
        d = motion.copy()
        if h36 is not None:
            for a, b in segments(present & ~np.isnan(h36[:, 0, 0]), 2):
                limited, changes = pose_limits.limit_joints(h36[a:b], lean[a:b, None])
                stats.update(changes)
                d[a:b] = pose_limits.directions_from_h36m(limited)
        if down.any():   # fallen, liegen, aufstehen: Ablauf aus möglichen Haltungen, gesteuert von der gemessenen Körperhöhe
            way = np.gradient(np.where(present[:, None], pos, np.nan), axis=0)
            lying_now = smooth[key]["down"][nearest] & down
            d = ground_motion.sequence(d, smooth[key]["share"][nearest], lying_now, down & present, way, OUT_FPS)
            grounded += int((down & present).sum())
        d = pose_limits.smooth_directions(pose_limits.limit_turn(d, OUT_FPS), OUT_FPS)
        allowed = lean if key in smooth else pose_limits.MAX_LEAN
        d = pose_limits.limit_directions(d, allowed)   # Glätten kann Grenzen wieder verletzen
        d, pos = pose_limits.balance_depth(d, lengths, pos, cam_pos, OUT_FPS, skip=down)
        d = pose_limits.limit_directions(d, allowed)
        for a, b in segments(present, 6):
            pos[a:b] = track_limits.physical(pos[a:b], OUT_FPS)
        xy[:, entity] = pos
        joints, before, after, count = pose_limits.plant_feet(pose_limits.build(d, lengths), pos, OUT_FPS, lengths, skip=down)
        # Das Festhalten der Füße kann die Hüfte überdehnen: Grenzen ein letztes Mal anwenden (der Fuß gibt dann nach)
        joints = pose_limits.build(pose_limits.limit_directions(pose_limits.directions_of(joints), allowed), lengths)
        for side in "lr":
            toes.append(joints[:, NAMES.index(side + "Toe"), :2] + pos)
        slip_before, slip_after, slip_frames = slip_before + before, slip_after + after, slip_frames + count
        values = np.where(np.isnan(joints), MISSING, np.clip(np.round(np.nan_to_num(joints) / POSE_SCALE), -32767, 32767)).astype(np.int64)
        for of in np.flatnonzero(present):
            o = (of * len(slots) + slot) * J * 3
            buf[o:o + J * 3] = array("h", values[of].ravel().tolist())
        from_video = (seen >= SEEN_SHARE) | down
        estimated += int((from_video & present).sum())
        present_total += int(present.sum())
        if key in smooth:
            summary[e["id"]] = round(float((from_video & present).sum() / present.sum()), 2)

    clock("Haltungen")
    if ball is not None and toes:
        xy[:, ball] = attach_ball(xy[:, ball], np.stack(toes, axis=1), OUT_FPS)
    print(f"Ball aus {ball_source}; an den Fuß gezogen, wo er in {BALL_REACH} m Reichweite einer Fußspitze lag")
    # 2D-Gelenkpunkte je Spieler im Takt der Ausgabe, für tools/veo_looks.py (bleibt lokal bei den Rohdaten)
    np.savez_compressed(f"{det_path}.players{'_own' if no_veo else ''}.npz", **{f"{k}.{part}": v for k, view in views.items() for part, v in view.items()})
    flat = np.array(data, np.int64).reshape(total, E, 3)
    flat[:, :, :2] = np.where(np.isnan(xy), base["tracks"]["missing"], np.round(xy / tscale))
    if ball_source == "Video":   # Flughöhe bestimmt die eigene Ballspur noch nicht: am Boden
        flat[:, ball, 2] = 0
    with open(out_dir / "tracks.bin", "wb") as f:
        array("h", flat.ravel().tolist()).tofile(f)

    pose_dir = out_dir / "poses"
    pose_dir.mkdir(exist_ok=True)
    per_chunk = CHUNK_FRAMES * len(slots) * J * 3
    chunks = math.ceil(total / CHUNK_FRAMES)
    for c in range(chunks):
        with open(pose_dir / f"{c:03d}.bin", "wb") as f:
            buf[c * per_chunk:(c + 1) * per_chunk].tofile(f)
    # Bilder des Platzes (Luftbild, Kulisse) aus dem Basisspiel mitnehmen
    pitch = base["pitch"]
    for name in [pitch.get("texture", {}).get("file")] + [w.get("file") for w in pitch.get("backdrop", {}).get("walls", [])]:
        if name and (base_dir / name).exists():
            shutil.copyfile(base_dir / name, out_dir / name)

    meta = dict(base)
    meta.update({
        "frames": total,
        "periods": [{"id": period["id"], "startFrame": 0, "endFrame": total - 1,
                     "clockStartS": period.get("clockStartS", 0) + (start - period["videoStartS"])}],
        "source": {"name": f"{base['source']['name']}, Szene ab Videosekunde {start:.0f}",
                   "notes": ("Positionen und Spuren aus dem Panorama gemessen (eigenes Tracking, ohne Veo), Spieler ohne Rückennummer. " if no_veo else
                             "Positionen aus dem Panorama gemessen (Fußpunkt am Boden), Rückennummern und Lücken aus Veo. ") +
                            "Körperhaltung im Kamerabild an die erkannten Gelenkpunkte angepasst (ein Blickwinkel); "
                            "Tiefe, verdeckte Gelenke und Lücken folgen einer natürlichen Bewegung im Takt der Schritte."},
        "poses": {
            "synthetic": False,
            "estimatedShare": round(estimated / max(1, present_total), 3),
            "source": "2D-Gelenkpunkte (ViTPose) je Spieler, daran angepasstes Skelett (tools/pose_fit.py) mit natürlicher "
                      "Bewegung als Vorlage (tools/motion_clips.py), begrenzt durch tools/pose_limits.py. "
                      "Tiefe erschlossen, Füße auf den Boden gesetzt.",
            "path": "poses/{chunk}.bin", "chunkFrames": CHUNK_FRAMES, "chunks": chunks, "dtype": "int16le",
            "layout": "frame, player, joint, [x, y, z]", "relativeTo": "track", "scale": POSE_SCALE, "missing": MISSING,
            "skeleton": {"joints": [{"name": a, "radius": r, "part": part} for a, r, part in JOINTS],
                         "bones": [{"from": NAMES.index(a), "to": NAMES.index(b), "radius": r, "part": part} for a, b, r, part in BONES]},
        },
    })
    old_meta = out_dir / "meta.json"
    if old_meta.exists() and (out_dir / "looks.png").exists():   # Videotexturen der Spieler (tools/veo_looks.py) behalten
        looks = json.loads(old_meta.read_text()).get("looks")
        if looks:
            meta["looks"] = looks
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    print(f"{total} Frames ({total / OUT_FPS:.0f} s). Jede Figur hat in jedem Bild ein Skelett; in {estimated / max(1, present_total):.0%} "
          f"aller Spieler-Bilder sind mindestens {SEEN_SHARE:.0%} der Gelenke im Video erkannt, der Rest folgt der natürlichen Bewegung.")
    print("Anteil je Spieler:", dict(sorted(summary.items(), key=lambda kv: -kv[1])))
    if errors:
        print(f"Abweichung Skelett zu Gelenkpunkten im Bild: im Mittel {np.mean(errors):.1f} Pixel (schlechtester Spieler {np.max(errors):.1f}); "
              f"rückwärts laufend erkannt: {backward_frames} Spieler-Bilder")
    print("Eingriffe der harten Gelenkgrenzen nach der Anpassung (Bilder, Summe über Spieler und Körperseiten):", dict(stats))
    print(f"Fallen, Liegen und Aufstehen aus Vorlagen dargestellt: {grounded} Spieler-Bilder")
    print(f"Stehende Füße rutschten im Mittel mit {slip_before / max(1, slip_frames):.2f} m/s über den Rasen, "
          f"nach dem Festhalten mit {slip_after / max(1, slip_frames):.2f} m/s ({slip_frames} Fuß-Bilder mit Bodenkontakt)")
    print(f"-> {out_dir}")
    print("Prüfung auf unmögliche Bewegungen (tools/check_motion.py):")
    check_motion.report(check_motion.check(out_dir))


if __name__ == "__main__":
    if len(sys.argv) != 9:
        sys.exit(__doc__)
    main(*sys.argv[1:])
