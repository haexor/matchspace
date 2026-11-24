#!/usr/bin/env python3
"""Passt ein Skelett so an die 2D-Gelenkpunkte eines Spielers an, dass es aus Kamerasicht mit dem Video übereinstimmt (Hilfsmodul).

Was eine Kamera misst, ist die Lage der Gelenke im Bild. Die Tiefe der Haltung misst sie nicht.
Deshalb wird je Spieler eine Bewegung gesucht, die

  1. im Bild auf den erkannten Gelenkpunkten liegt (gewichtet mit deren Sicherheit),
  2. in allem, was das Bild offen lässt, einer natürlichen Bewegung folgt: Stehen, Gehen oder
     Laufen passend zu Tempo und Richtung des Spielers (tools/motion_clips.py), im Takt der
     im Video sichtbaren Schritte,
  3. feste Knochenlängen hat, einfache Gelenkgrenzen einhält und sich über die Zeit ruhig ändert.

Wo ein Spieler verdeckt ist oder Gelenke nicht erkannt werden, läuft die natürliche Bewegung
im Takt weiter. Lücken werden so von beiden Seiten her überbrückt, statt Gelenke gerade zu
verbinden.

Achsen: x, y waagerecht (Feld), z hoch. Gelenke: die ersten 16 aus synth_poses.NAMES (ohne Fersen
und Fußspitzen, die das Bild nicht hergibt).
"""
import math
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).parent))
import motion_clips  # noqa: E402
import pose_limits  # noqa: E402
import veo_camera  # noqa: E402
from synth_poses import NAMES  # noqa: E402

I = {n: i for i, n in enumerate(NAMES)}
FIT = NAMES[:16]
# COCO-Punkt je Gelenk (Kopfmitte und Nase gesondert)
COCO = {"lShoulder": 5, "rShoulder": 6, "lElbow": 7, "rElbow": 8, "lWrist": 9, "rWrist": 10,
        "lHip": 11, "rHip": 12, "lKnee": 13, "rKnee": 14, "lAnkle": 15, "rAnkle": 16}
JOINT_WEIGHT = {"head": 0.8, "nose": 0.4, "lWrist": 0.7, "rWrist": 0.7, "lElbow": 0.9, "rElbow": 0.9}
MIN_CONF = 0.3          # darunter gilt ein Gelenkpunkt als nicht erkannt
REF_HEIGHT = 0.9        # Höhe über dem Rasen, um die das Kamerabild linearisiert wird
DROOP = pose_limits.SHOULDER_DROOP
PHASES = 32             # Stützstellen der Schrittphase bei der Suche nach dem Takt
ITERATIONS = 400
DEPTH_STIFFNESS = 4.0   # Gewicht, mit dem die Tiefe der Haltung an der natürlichen Bewegung hängt
SMOOTHNESS = 150.0      # Gewicht, mit dem sich die Abweichung von der natürlichen Bewegung über die Zeit ruhig ändern muss


def linearize(cam, lens, pos):
    """Lokale Abbildung Feld -> Bild je Zeitpunkt: Pixel = ref + A · (Punkt - (pos, REF_HEIGHT)).

    lens: (T,) Linsennummer oder NaN; pos: (T, 2). Rückgabe: ref (T, 2), A (T, 2, 3); NaN ohne Linse."""
    T = len(pos)
    ref, A = np.full((T, 2), np.nan), np.full((T, 2, 3), np.nan)
    step = 0.3
    for li, name in enumerate(veo_camera.LENSES):
        m = (lens == li) & ~np.isnan(pos[:, 0])
        if not m.any():
            continue
        base = np.column_stack([pos[m], np.full(m.sum(), REF_HEIGHT)])
        ref[m] = veo_camera.project(cam, name, base)
        for axis in range(3):
            e = np.zeros(3)
            e[axis] = step
            A[m, :, axis] = (veo_camera.project(cam, name, base + e) - veo_camera.project(cam, name, base - e)) / (2 * step)
    return ref, A


def targets(kp):
    """COCO-Punkte (T, 17, 3) -> Zielpunkte (T, 16, 2) und Gewichte (T, 16) für die Gelenke in FIT."""
    T = len(kp)
    xy, w = np.zeros((T, 16, 2)), np.zeros((T, 16))
    conf = np.nan_to_num(kp[:, :, 2])
    pts = np.nan_to_num(kp[:, :, :2])
    for name, c in COCO.items():
        j = I[name]
        xy[:, j], w[:, j] = pts[:, c], np.where(conf[:, c] >= MIN_CONF, conf[:, c], 0.0) * JOINT_WEIGHT.get(name, 1.0)
    # Kopfmitte: zwischen den Ohren; sonst Mittel der erkannten Punkte im Gesicht
    ears = (conf[:, 3] >= MIN_CONF) & (conf[:, 4] >= MIN_CONF)
    face = np.where(conf[:, :5] >= MIN_CONF, conf[:, :5], 0.0)
    centre = (pts[:, :5] * face[:, :, None]).sum(axis=1) / np.maximum(face.sum(axis=1, keepdims=True), 1e-9)
    xy[:, I["head"]] = np.where(ears[:, None], (pts[:, 3] + pts[:, 4]) / 2, centre)
    w[:, I["head"]] = np.where(ears, (conf[:, 3] + conf[:, 4]) / 2, np.where(face.sum(axis=1) > 0, 0.5 * face.max(axis=1), 0.0)) * JOINT_WEIGHT["head"]
    xy[:, I["nose"]], w[:, I["nose"]] = pts[:, 0], np.where(ears & (conf[:, 0] >= MIN_CONF), conf[:, 0], 0.0) * JOINT_WEIGHT["nose"]
    return xy, w


def heading_speed(positions, ball, fps):
    """Laufrichtung (rad), geglättetes Tempo (m/s) und Geschwindigkeit je Bild; im Stand zeigt die Richtung zum Ball."""
    T = len(positions)
    heading, speed, velocity = np.zeros(T), np.zeros(T), np.zeros((T, 2))
    span = max(1, round(0.4 * fps))   # die gemessene Bahn zittert; kürzer gemessen "läuft" ein stehender Spieler
    h, smooth = None, 0.0
    for t in range(T):
        if np.isnan(positions[t, 0]):
            h, smooth = None, 0.0
            continue
        a, b = positions[max(0, t - span)], positions[min(T - 1, t + span)]
        v = np.zeros(2)
        if not np.isnan(a[0]) and not np.isnan(b[0]):
            v = (b - a) / ((min(T - 1, t + span) - max(0, t - span)) / fps)
        s = float(np.linalg.norm(v))
        if s > 12:
            v, s = np.zeros(2), 0.0
        smooth += (s - smooth) * 0.3
        target = None
        if s > 0.8:
            target = math.atan2(v[1], v[0])
        elif ball is not None and not np.isnan(ball[t, 0]) and np.linalg.norm(ball[t] - positions[t]) > 0.5:
            target = math.atan2(ball[t, 1] - positions[t, 1], ball[t, 0] - positions[t, 0])
        if h is None:
            h = target or 0.0
        elif target is not None:
            diff = target - h
            h += math.atan2(math.sin(diff), math.cos(diff)) * 0.2
        heading[t], speed[t], velocity[t] = h, smooth, v
    return heading, speed, velocity


def _turn(d, angle):
    """Dreht Richtungen (T, ..., 3) je Zeitpunkt um die Hochachse."""
    c, s = np.cos(angle), np.sin(angle)
    shape = (-1,) + (1,) * (d.ndim - 2)
    c, s = c.reshape(shape), s.reshape(shape)
    return np.stack([d[..., 0] * c - d[..., 1] * s, d[..., 0] * s + d[..., 1] * c, d[..., 2]], axis=-1)


def natural_motion(positions, ball, fps, lengths, xy=None, weight=None, A=None, start_phase=0.0):
    """Natürliche Bewegung entlang der Bahn eines Spielers als Knochenrichtungen (T, 20, 3); NaN ohne Position.

    Mit Gelenkpunkten (xy, weight aus targets(), A aus linearize()) wird zweierlei aus dem Bild gelesen:
    ob der Spieler rückwärts läuft (linke und rechte Körperseite erscheinen vertauscht) und in
    welcher Schrittphase er ist. Die Phase läuft mit der zum Tempo passenden Schrittfrequenz und
    wird dort, wo Beine zu sehen sind, auf das Bild eingerastet; durch Lücken läuft sie weiter.
    Rückgabe: Richtungen, Maske "läuft rückwärts"."""
    clips = motion_clips.load()
    T = len(positions)
    present = ~np.isnan(positions[:, 0])
    heading, speed, _ = heading_speed(positions, ball, fps)
    backwards = np.zeros(T, bool)
    seen = xy is not None and weight is not None and np.isfinite(A).any()
    if seen:
        # Rückwärts? Die Linie von der rechten zur linken Schulter (und Hüfte) im Bild gegen die Erwartung bei
        # Blick in Laufrichtung. Auswertbar nur, wenn der Spieler nicht genau quer zur Kamera steht.
        Ah = np.nan_to_num(A[:, :, :2])
        left = np.column_stack([-np.sin(heading), np.cos(heading)])
        expect = np.einsum("tij,tj->ti", Ah, left)                      # Bildvektor je Meter nach links
        size = np.linalg.norm(expect, axis=1)
        widest = np.maximum(np.linalg.norm(Ah[:, :, 0], axis=1), np.linalg.norm(Ah[:, :, 1], axis=1))
        evidence, trust = np.zeros(T), np.zeros(T)
        for a, b, half in (("lShoulder", "rShoulder", lengths["lShoulder"]), ("lHip", "rHip", lengths["lHip"])):
            w = np.minimum(weight[:, I[a]], weight[:, I[b]]) * (size > 0.7 * widest)
            seen_width = ((xy[:, I[a]] - xy[:, I[b]]) * expect).sum(axis=1) / np.maximum(2 * half * size ** 2, 1e-6)
            evidence += w * np.clip(seen_width, -1, 1)
            trust += w
        # Nur glauben, was über zwei Sekunden hinweg deutlich ist und mindestens eine Sekunde anhält:
        # von der Seite gesehen ist links/rechts im Bild Zufall.
        half = int(fps)
        kernel = np.ones(2 * half + 1)
        total = np.convolve(trust, kernel, "same")
        backwards = (total > 0.4 * len(kernel)) & (np.convolve(evidence, kernel, "same") / np.maximum(total, 1e-9) < -0.4)
        for a, b in pose_limits.runs(backwards):
            if b - a < fps:
                backwards[a:b] = False
    # Drehung zwischen vorwärts und rückwärts über knapp eine halbe Sekunde, nicht in einem Bild
    turn = np.convolve(backwards.astype(float), np.hanning(max(3, int(0.45 * fps) | 1)) / np.hanning(max(3, int(0.45 * fps) | 1)).sum(), "same")
    facing = heading + math.pi * turn
    advance = 2 * math.pi * clips.cadence(speed) / fps * np.where(backwards, -1.0, 1.0) * (speed > motion_clips.STANDING)

    phase = np.zeros(T)
    if seen:
        grid = np.arange(PHASES) * 2 * math.pi / PHASES
        d = clips.directions(np.broadcast_to(grid, (T, PHASES)), np.broadcast_to(speed[:, None], (T, PHASES)))
        d = _turn(d, facing)
        joints = pose_limits.build(d.reshape(T * PHASES, 20, 3), lengths).reshape(T, PHASES, 20, 3)
        pred = np.einsum("tij,tkmj->tkmi", np.nan_to_num(A), joints)          # (T, PHASES, 20, 2), ohne festen Anteil
        scale = np.maximum(np.linalg.norm(np.nan_to_num(A[:, :, 2]), axis=1), 1e-6)  # Pixel je Meter Höhe
        hips = [I["lHip"], I["rHip"]]
        use = [I[n] for n in ("lKnee", "rKnee", "lAnkle", "rAnkle")]
        hip_w = np.minimum(weight[:, hips[0]], weight[:, hips[1]])
        rel_obs = xy[:, use] - xy[:, hips].mean(axis=1, keepdims=True)
        rel_pred = pred[:, :, use] - pred[:, :, hips].mean(axis=2, keepdims=True)
        err = np.linalg.norm(rel_pred - rel_obs[:, None], axis=3) / scale[:, None, None]
        w = weight[:, use] * (hip_w > 0)[:, None] * (speed > motion_clips.STANDING)[:, None]
        cost = (np.minimum(err, 0.35) ** 2 * w[:, None]).sum(axis=2) * 40
        # Links und rechts verwechselt die Erkennung bei so kleinen Spielern oft: auch die vertauschte Lesart zulassen
        swap = [1, 0, 3, 2]
        err_swapped = np.linalg.norm(rel_pred - rel_obs[:, None][:, :, swap], axis=3) / scale[:, None, None]
        cost = np.minimum(cost, (np.minimum(err_swapped, 0.35) ** 2 * w[:, None][:, :, swap]).sum(axis=2) * 40 + 0.02)
        # beste Folge von Phasen: jeder Schritt soll der Schrittfrequenz folgen
        steps = advance * PHASES / (2 * math.pi)
        offsets = np.arange(PHASES)[None, :] - np.arange(PHASES)[:, None]     # [von, nach]
        total_cost = np.zeros(PHASES)
        back = np.zeros((T, PHASES), int)
        for t in range(1, T):
            if not present[t] or not present[t - 1]:
                total_cost = cost[t].copy() if present[t] else np.zeros(PHASES)
                continue
            delta = (offsets - steps[t] + PHASES / 2) % PHASES - PHASES / 2
            trans = (delta / (0.35 * abs(steps[t]) + 0.25)) ** 2
            through = total_cost[:, None] + trans
            back[t] = through.argmin(axis=0)
            total_cost = through.min(axis=0) + cost[t]
        k = int(total_cost.argmin())
        for t in range(T - 1, -1, -1):
            phase[t] = grid[k]
            if t and present[t] and present[t - 1]:
                k = back[t, k]
            elif t:
                k = 0
        # Die Stützstellen sind grob: Phase entlang der Zeit entrollen und glätten
        for a, b in pose_limits.runs(present, 2):
            un = np.unwrap(phase[a:b])
            if b - a >= 7:
                kernel = np.array([1, 2, 3, 2, 1]) / 9
                un[2:-2] = np.convolve(un, kernel, "valid")
            phase[a:b] = un
    else:
        p = start_phase
        for t in range(T):
            p += advance[t]
            phase[t] = p
    d = _turn(clips.directions(phase, speed), facing)
    d[~present] = np.nan
    return d, backwards


def _unit(v):
    return v / torch.clamp(v.norm(dim=-1, keepdim=True), min=1e-8)


BONES = ["neck", "head", "hips", "shoulders", "lElbow", "rElbow", "lWrist", "rWrist", "lKnee", "rKnee", "lAnkle", "rAnkle"]
B = {n: i for i, n in enumerate(BONES)}


def _forward(d, length):
    """Knochenrichtungen (T, 12, 3) -> Gelenke (T, 16, 3) relativ zum Becken, dazu Körperachsen."""
    up = d[:, B["neck"]]
    hl, sl = d[:, B["hips"]], d[:, B["shoulders"]]
    z = torch.tensor([0.0, 0.0, 1.0], dtype=d.dtype, device=d.device)
    L = length
    J = {"pelvis": torch.zeros_like(up)}
    J["neck"] = L["neck"] * up
    J["head"] = J["neck"] + L["head"] * d[:, B["head"]]
    face = _unit(torch.cross(sl, z.expand_as(sl), dim=-1))
    J["nose"] = J["head"] + L["nose"] * _unit(0.95 * face - 0.3 * z)
    for side, sign in (("l", 1.0), ("r", -1.0)):
        J[side + "Hip"] = sign * L["lHip"] * hl
        J[side + "Knee"] = J[side + "Hip"] + L["lKnee"] * d[:, B[side + "Knee"]]
        J[side + "Ankle"] = J[side + "Knee"] + L["lAnkle"] * d[:, B[side + "Ankle"]]
        J[side + "Shoulder"] = J["neck"] + L["lShoulder"] * _unit(sign * math.cos(DROOP) * sl - math.sin(DROOP) * up)
        J[side + "Elbow"] = J[side + "Shoulder"] + L["lElbow"] * d[:, B[side + "Elbow"]]
        J[side + "Wrist"] = J[side + "Elbow"] + L["lWrist"] * d[:, B[side + "Wrist"]]
    return torch.stack([J[n] for n in FIT], dim=1)


def _prior_bones(d20):
    """Vorlage (T, 20, 3) -> die 12 Richtungen des Fits."""
    out = np.zeros((len(d20), 12, 3))
    out[:, B["neck"]], out[:, B["head"]] = d20[:, I["neck"]], d20[:, I["head"]]
    out[:, B["hips"]] = pose_limits.unit(d20[:, I["lHip"]] - d20[:, I["rHip"]])
    out[:, B["shoulders"]] = pose_limits.unit(d20[:, I["lShoulder"]] - d20[:, I["rShoulder"]])
    for n in BONES[4:]:
        out[:, B[n]] = d20[:, I[n]]
    return out


def to_h36m(joints):
    """Gelenke des Fits (T, 16, 3) relativ zum Becken -> H36M (T, 17, 3)."""
    p = np.zeros((len(joints), 17, 3))
    g = lambda n: joints[:, I[n]]  # noqa: E731
    p[:, 1], p[:, 2], p[:, 3] = g("rHip"), g("rKnee"), g("rAnkle")
    p[:, 4], p[:, 5], p[:, 6] = g("lHip"), g("lKnee"), g("lAnkle")
    p[:, 8], p[:, 7] = g("neck"), g("neck") / 2
    p[:, 9], p[:, 10] = g("neck") + 0.6 * (g("head") - g("neck")), g("neck") + 1.4 * (g("head") - g("neck"))
    p[:, 11], p[:, 12], p[:, 13] = g("lShoulder"), g("lElbow"), g("lWrist")
    p[:, 14], p[:, 15], p[:, 16] = g("rShoulder"), g("rElbow"), g("rWrist")
    return p


def fit(xy, weight, ref, A, positions, eye, lengths, prior, max_lean, device="cuda"):
    """Sucht die Bewegung eines Spielers.

    xy, weight: Zielpunkte (T, 16, 2) in Pixeln und Gewichte (T, 16) aus targets(); ref, A aus linearize();
    positions: (T, 2) Bodenposition; eye: Standort der Kamera (3); lengths: Knochenlängen (pose_limits.bone_lengths);
    prior: natürliche Bewegung (T, 20, 3); max_lean: größte Rumpfneigung je Bild (T,) in rad.
    Die Körpergröße bleibt fest: Ein zu großes Skelett müsste sich im Bild "klein machen" und würde sich dazu in die
    Tiefe neigen oder in die Knie gehen.
    Rückgabe: dict mit h36m (T, 17, 3) relativ zum Becken, shift (T, 2) Versatz der Bodenposition,
    error (mittlere Abweichung im Bild in Pixeln) und observed (T,) Anteil
    erkannter Gelenke."""
    T = len(positions)
    present = ~np.isnan(positions[:, 0]) & ~np.isnan(prior[:, 1, 0])
    usable = present & np.isfinite(A).all(axis=(1, 2))
    w_np = weight * usable[:, None]
    f64 = dict(dtype=torch.float64, device=device)
    tt = lambda v: torch.tensor(np.nan_to_num(np.asarray(v, float)), **f64)  # noqa: E731
    p0 = tt(_prior_bones(np.nan_to_num(prior)))
    p0 = torch.where(p0.norm(dim=-1, keepdim=True) > 0.5, p0, torch.tensor([0.0, 0.0, 1.0], **f64))
    xy_t, w_t, ref_t, A_t = tt(xy), tt(w_np), tt(ref), tt(A)
    here = tt(present.astype(float))
    px = torch.clamp(A_t[:, :, 2].norm(dim=1), min=1.0) * (lengths["neck"] + lengths["lKnee"] + lengths["lAnkle"] + lengths["head"] + 0.2)
    clear = tt(pose_limits.CLEARANCE[:16])
    lean_cos = torch.cos(tt(max_lean))
    # Blickrichtung der Kamera am Boden: Versatz in die Tiefe ist kaum messbar und wird klein gehalten
    view = tt(positions - np.asarray(eye)[:2])
    view = view / torch.clamp(view.norm(dim=1, keepdim=True), min=1e-6)
    view3 = torch.cat([view, torch.zeros((T, 1), **f64)], dim=1)[:, None]
    length = {k: float(v) for k, v in lengths.items()}

    raw = p0.clone().requires_grad_(True)
    shift = torch.zeros((T, 2), **f64, requires_grad=True)
    lift = torch.zeros(T, **f64, requires_grad=True)   # Höhe über dem Stand auf dem Rasen (Fuß auf der Spitze, Absprung, Modellfehler)
    opt = torch.optim.Adam([{"params": [raw], "lr": 0.02}, {"params": [shift, lift], "lr": 0.01}])
    seen = (w_t > 0).double()
    # je Richtung: wird das Gelenk am Ende des Knochens gesehen?
    end = {"neck": ["lShoulder", "rShoulder"], "head": ["head"], "hips": ["lHip", "rHip"], "shoulders": ["lShoulder", "rShoulder"]}
    stiff = torch.tensor([DEPTH_STIFFNESS * (3.0 if n in ("neck", "head") else 1.0) for n in BONES], **f64)
    bone_seen = torch.stack([torch.stack([seen[:, I[j]] for j in end.get(n, [n])], dim=1).min(dim=1).values for n in BONES], dim=1)

    def project(J, shift):
        low = (J[:, :, 2] - clear).min(dim=1).values
        X = J.clone()
        X[:, :, 2] = X[:, :, 2] - low[:, None] + lift[:, None] - REF_HEIGHT
        X[:, :, :2] = X[:, :, :2] + shift[:, None]
        return ref_t[:, None] + torch.einsum("tij,tkj->tki", A_t, X)

    # Links und rechts verwechselt die Erkennung bei so kleinen Spielern oft. Für Beine und Arme wird deshalb je Bild
    # die Lesart genommen (wie erkannt oder vertauscht), die besser zur aktuellen Haltung passt.
    groups = [[I[n] for n in ("lKnee", "rKnee", "lAnkle", "rAnkle")], [I[n] for n in ("lElbow", "rElbow", "lWrist", "rWrist")]]
    mirror = list(range(16))
    for a, b in (("lKnee", "rKnee"), ("lAnkle", "rAnkle"), ("lElbow", "rElbow"), ("lWrist", "rWrist")):
        mirror[I[a]], mirror[I[b]] = I[b], I[a]
    xy_m, w_m = xy_t[:, mirror], w_t[:, mirror]
    xy_use, w_use = xy_t.clone(), w_t.clone()
    swapped = torch.zeros((T, len(groups)), dtype=torch.bool, device=device)

    def cost_of(J, shift, target, w):
        res = (project(J, shift) - target) / px[:, None, None]
        e = torch.sqrt((res ** 2).sum(dim=-1) + 1e-10)
        return torch.where(e < 0.04, 0.5 * e ** 2, 0.04 * (e - 0.02)) * w

    for it in range(ITERATIONS):
        opt.zero_grad()
        d = _unit(raw)
        J = _forward(d, length)
        if it % 25 == 0:
            with torch.no_grad():
                plain, flipped = cost_of(J, shift, xy_t, w_t), cost_of(J, shift, xy_m, w_m)
                for g, joints in enumerate(groups):
                    swapped[:, g] = flipped[:, joints].sum(dim=1) < 0.7 * plain[:, joints].sum(dim=1) - 1e-5
                    xy_use[:, joints] = torch.where(swapped[:, g, None, None], xy_m[:, joints], xy_t[:, joints])
                    w_use[:, joints] = torch.where(swapped[:, g, None], w_m[:, joints], w_t[:, joints])
        data = cost_of(J, shift, xy_use, w_use).sum() / T * 2000

        diff = d - p0
        # Im Bild darf die Haltung der Messung folgen. In die Tiefe bleibt sie bei der natürlichen Bewegung, solange
        # das Bild nicht deutlich etwas anderes verlangt: Sonst würde jede kleine Abweichung der Knochenlängen als
        # Neigung zur Kamera hin oder von ihr weg gedeutet.
        deep_diff = (diff * view3).sum(dim=-1)
        prior_term = (((diff ** 2).sum(dim=-1) * (0.02 + 0.5 * (1 - bone_seen)) + stiff * deep_diff ** 2) * here[:, None]).sum() / T
        pair = (here[2:] * here[1:-1] * here[:-2])
        accel = diff[2:] - 2 * diff[1:-1] + diff[:-2]
        smooth = ((accel ** 2).sum(dim=-1) * pair[:, None]).sum() / T * SMOOTHNESS
        jerk = J[2:] - 2 * J[1:-1] + J[:-2]
        smooth = smooth + ((jerk ** 2).sum(dim=-1) * pair[:, None]).sum() / T * 3
        # Der Rumpf dreht sich nie ruckartig, auch wenn die Vorlage es täte
        trunk = d[:, :4]
        turn = trunk[2:] - 2 * trunk[1:-1] + trunk[:-2]
        smooth = smooth + ((turn ** 2).sum(dim=-1) * pair[:, None]).sum() / T * 60

        up, hl, sl = d[:, B["neck"]], d[:, B["hips"]], d[:, B["shoulders"]]
        fwd = _unit(torch.cross(hl, up, dim=-1))
        limits = (torch.relu(lean_cos - up[:, 2]) ** 2).sum() * 4
        limits = limits + ((hl * up).sum(-1) ** 2).sum() * 2
        limits = limits + (torch.relu((sl * up).sum(-1).abs() - math.sin(math.radians(20))) ** 2).sum() * 2
        limits = limits + (torch.relu(math.cos(math.radians(45)) - (hl * sl).sum(-1)) ** 2).sum() * 2
        limits = limits + (torch.relu(math.cos(math.radians(45)) - (d[:, B["head"]] * up).sum(-1)) ** 2).sum() * 2
        chest = _unit(torch.cross(sl, up, dim=-1))
        for side in "lr":
            thigh, shank = d[:, B[side + "Knee"]], d[:, B[side + "Ankle"]]
            ahead = _unit(fwd - (fwd * thigh).sum(-1, keepdim=True) * thigh)
            limits = limits + (torch.relu((shank * ahead).sum(-1) - 0.05) ** 2).sum() * 3      # Knie beugt nur nach hinten
            limits = limits + (torch.relu(-(thigh * fwd).sum(-1) - 0.55) ** 2).sum() * 2        # Oberschenkel nicht weit nach hinten
            out = hl if side == "l" else -hl
            spread = (thigh * out).sum(-1)
            limits = limits + (torch.relu(spread - 0.6) ** 2 + torch.relu(-0.3 - spread) ** 2).sum() * 3   # abspreizen, kreuzen
            hinge = _unit(out - (out * thigh).sum(-1, keepdim=True) * thigh)
            limits = limits + (torch.relu((shank * hinge).sum(-1).abs() - 0.3) ** 2).sum() * 3    # Knie ist ein Scharnier
            upper, fore = d[:, B[side + "Elbow"]], d[:, B[side + "Wrist"]]
            behind = -((fore - (fore * upper).sum(-1, keepdim=True) * upper) * chest).sum(-1)
            limits = limits + (torch.relu(behind - 0.35) ** 2).sum() * 1                        # Unterarm klappt nicht nach hinten
            limits = limits + (torch.relu(-0.85 - (fore * upper).sum(-1)) ** 2).sum() * 2      # Ellbogen höchstens rund 150°
        # Beine kreuzen sich kaum: der linke Fuß bleibt links vom rechten (aus Sicht des Beckens)
        for joint, slack in (("Knee", 0.04), ("Ankle", 0.08)):
            apart = ((J[:, I["l" + joint]] - J[:, I["r" + joint]]) * hl).sum(-1)
            limits = limits + (torch.relu(-slack - apart) ** 2).sum() * 150
        limits = limits / T

        deep = (shift * view).sum(-1)
        side_shift = shift - deep[:, None] * view
        root = ((deep ** 2) * 5 + (side_shift ** 2).sum(-1) * 0.5).sum() / T
        s_acc = shift[2:] - 2 * shift[1:-1] + shift[:-2]
        l_acc = lift[2:] - 2 * lift[1:-1] + lift[:-2]
        root = root + (s_acc ** 2).sum() / T * 1000 + (lift ** 2).sum() / T * 1500 + (l_acc ** 2).sum() / T * 2000
        loss = data + prior_term + smooth + limits + root
        loss.backward()
        opt.step()

    with torch.no_grad():
        d = _unit(raw)
        J = _forward(d, length)
        res = project(J, shift) - xy_use
        err = ((res ** 2).sum(-1).sqrt() * (w_use > 0)).sum() / torch.clamp((w_use > 0).sum(), min=1)
    joints = J.cpu().numpy()
    joints[~present] = np.nan
    body = [I[n] for n in COCO]
    return {"h36m": to_h36m(joints), "shift": shift.detach().cpu().numpy() * present[:, None], 
            "lift": lift.detach().cpu().numpy() * present,
            "swapped": swapped.cpu().numpy() & present[:, None], "error": float(err), "observed": (w_np[:, body] > 0).mean(axis=1)}
