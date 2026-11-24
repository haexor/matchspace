#!/usr/bin/env python3
"""Hält Körperhaltungen in dem Bereich, den ein menschlicher Körper hergibt (Hilfsmodul).

Eine aus dem Video gelesene Haltung kann Dinge zeigen, die es nicht gibt: Knie, die nach vorn
durchknicken, einen Rumpf in der Waagerechten, Arme, die in einem Bild um 90° springen.
Dieses Modul lässt so etwas nicht durch, egal was die Messung liefert:

  1. Gelenkgrenzen je Bild: Rumpfneigung, Hüfte, Knie (beugt nur nach hinten, höchstens
     150°), Schultergürtel, Oberarm, Ellbogen, Kopf.
  2. Feste Knochenlängen je Spieler.
  3. Zeit: Jeder Knochen dreht sich höchstens so schnell, wie ein Mensch es kann, dazu eine
     Glättung. Sprünge von Bild zu Bild verschwinden.
  4. Boden: Kein Körperteil liegt unter dem Rasen, der tiefste Punkt steht auf. Dass ein Fuß, der
     aufsteht, an seiner Stelle bleibt (kein Rutschen), regelt tools/foot_planting.py.

Die Grenzen sind bewusst großzügig (Sportler, Grätschen, Schüsse). Für Spieler am Boden
(gefoult, gestürzt, sitzend) entfällt die Grenze für die Rumpfneigung; der Körper liegt dann
mit seiner Dicke auf dem Rasen auf. Ob ein Spieler am Boden ist, entscheidet nicht dieses
Modul, sondern die Messung (tools/veo_scene.py: Höhe und Form der erkannten Box).

Skelette: H36M (17 Gelenke, Zwischenformat) und MatchSpace (20 Gelenke, synth_poses.NAMES).
Achsen: x, y waagerecht, z hoch; Positionen relativ zum Becken.
"""
import math
from pathlib import Path
import sys

import numpy as np
from scipy.signal import butter, filtfilt

sys.path.insert(0, str(Path(__file__).parent))
from synth_poses import NAMES  # noqa: E402

# H36M: 0 Becken, 1-3 rechtes Bein, 4-6 linkes Bein, 7 Wirbelsäule, 8 Brust, 9 Hals/Nase, 10 Scheitel,
# 11-13 linker Arm, 14-16 rechter Arm
H_PARENT = [0, 0, 1, 2, 0, 4, 5, 0, 7, 8, 9, 8, 11, 12, 8, 14, 15]
H_MIRROR = [0, 4, 5, 6, 1, 2, 3, 7, 8, 9, 10, 14, 15, 16, 11, 12, 13]
I = {n: i for i, n in enumerate(NAMES)}
PARENT = {"neck": "pelvis", "head": "neck", "nose": "head", "lShoulder": "neck", "rShoulder": "neck",
          "lElbow": "lShoulder", "rElbow": "rShoulder", "lWrist": "lElbow", "rWrist": "rElbow",
          "lHip": "pelvis", "rHip": "pelvis", "lKnee": "lHip", "rKnee": "rHip", "lAnkle": "lKnee", "rAnkle": "rKnee",
          "lHeel": "lAnkle", "rHeel": "rAnkle", "lToe": "lHeel", "rToe": "rHeel"}
ORDER = [n for n in NAMES if n != "pelvis"]  # NAMES ist so sortiert, dass Vorgänger zuerst kommen
# Höchste Drehgeschwindigkeit je Knochen (rad/s) und Grenzfrequenz der Glättung (Hz), nach dem Gelenk am Ende
SPEED = {"neck": (6, 3), "head": (10, 4), "nose": (10, 4), "Shoulder": (8, 3), "Elbow": (18, 5), "Wrist": (25, 6),
         "Hip": (6, 3), "Knee": (15, 5), "Ankle": (25, 6), "Heel": (30, 6), "Toe": (30, 6)}
DEG = math.pi / 180
MAX_LEAN = 35 * DEG
SHOULDER_DROOP = 18 * DEG   # Schultergelenke liegen etwas unter dem Halsansatz
# Körpermaße als Anteil der "Kette" Bein (Hüfte-Knie-Knöchel) plus Rumpf (Hüft- bis Schulterlinie). Die Kette ist das,
# was sich an den erkannten Gelenkpunkten am verlässlichsten messen lässt; die Anteile sind an den Gelenkpunkten aller
# Spieler einer Szene gemessen (Streuung zwischen Spielern rund 0,01) und passen zu üblichen Körpermaßen
# (Hüftgelenk auf gut halber Körperhöhe).
CHAIN_SHARE = 0.775       # Kette als Anteil der Körpergröße (Schulterhöhe minus Knöchelhöhe)
SHARE = {"thigh": 0.311, "shank": 0.305, "torso": 0.387, "upperArm": 0.200, "foreArm": 0.170,
         "shoulderWidth": 0.225, "hipWidth": 0.155, "head": 0.151}   # head: Kopfmitte über der Schulterlinie


def unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9)


def dot(a, b):
    return (a * b).sum(axis=-1, keepdims=True)


def clamp_cone(d, axis, limit):
    """Dreht Richtungen d so weit zur Achse, dass der Winkel höchstens limit beträgt."""
    c = np.clip(dot(d, axis), -1, 1)
    angle = np.arccos(c)
    perp = unit(d - c * axis)
    capped = np.minimum(angle, limit)
    return np.cos(capped) * axis + np.sin(capped) * perp


def rotate_to(v, a, b):
    """Dreht Vektoren v (..., 3) mit der kürzesten Drehung, die die Einheitsrichtung a auf b bringt."""
    axis = np.cross(a, b)
    sin = np.linalg.norm(axis, axis=-1, keepdims=True)
    k = axis / np.maximum(sin, 1e-9)
    cos = dot(a, b)
    turned = v * cos + np.cross(k, v) * sin + k * dot(k, v) * (1 - cos)
    return np.where(sin > 1e-6, turned, v)


def limit_leg(t, sk, left, up, fwd, out):
    """Oberschenkel t und Unterschenkel sk (n, 3) in den Grenzen von Hüfte und Knie.

    Oberschenkel: nach vorn bis 120°, nach hinten 30°, abspreizen 50°, zur Mitte 20° (out zeigt vom
    Körper weg). Knie: beugt nur nach hinten (0 bis 150°); die Beugeebene darf sich um ±35° drehen."""
    beta = np.clip(np.arcsin(np.clip(dot(t, out), -1, 1)), -20 * DEG, 50 * DEG)
    alpha = np.clip(np.arctan2(dot(t, fwd), -dot(t, up)), -30 * DEG, 120 * DEG)
    t2 = np.cos(beta) * (np.sin(alpha) * fwd - np.cos(alpha) * up) + np.sin(beta) * out
    a = unit(left - dot(left, t2) * t2)
    n = np.cross(a, t2)
    perp = sk - dot(sk, t2) * t2
    flex = np.minimum(np.arctan2(np.linalg.norm(perp, axis=1, keepdims=True), dot(sk, t2)), 150 * DEG)
    twist = np.clip(np.arctan2(dot(perp, a), dot(perp, n)), -35 * DEG, 35 * DEG)
    return t2, np.cos(flex) * t2 + np.sin(flex) * (np.cos(twist) * n + np.sin(twist) * a)


def limit_arm(u, w, out, chest, up):
    """Oberarm u und Unterarm w (n, 3): nicht quer durch den Körper, nicht hoch hinter den Rücken, Ellbogen höchstens 150°."""
    uo, uf, uu = dot(u, out), dot(u, chest), dot(u, up)
    uo = np.where((uo < -0.5) & (uf < 0.5), -0.5, uo)
    uu = np.where((uf < 0) & (uu > 0.2), 0.2, uu)
    uf = np.maximum(uf, -0.87)
    u2 = unit(uo * out + uf * chest + uu * up)
    return u2, clamp_cone(w, u2, 150 * DEG)


def limit_directions(d, max_lean=MAX_LEAN):
    """Gelenkgrenzen für Knochenrichtungen des 20-Gelenk-Skeletts (T, 20, 3); NaN-Zeilen bleiben.

    Letzter Schritt vor dem Aufbau der Figur: Glätten über die Zeit kann Grenzen wieder verletzen
    (Oberschenkel und Rumpf werden je für sich geglättet). max_lean: Zahl oder je Bild (T,)."""
    out = d.copy()
    ok = ~np.isnan(d[:, I["neck"], 0])
    if not ok.any():
        return out
    x = unit(d[ok])
    lean = np.broadcast_to(np.asarray(max_lean, float), (len(d),))[ok][:, None]
    up = x[:, I["neck"]]
    target = clamp_cone(up, np.broadcast_to([0, 0, 1.0], up.shape), lean)
    x = rotate_to(x, up[:, None], target[:, None])
    up = target
    left = x[:, I["lHip"]] - x[:, I["rHip"]]
    left = unit(left - dot(left, up) * up)
    fwd = np.cross(left, up)
    x[:, I["lHip"]], x[:, I["rHip"]] = left, -left
    for side, away in (("l", left), ("r", -left)):
        knee, ankle = I[side + "Knee"], I[side + "Ankle"]
        t2, s2 = limit_leg(x[:, knee], x[:, ankle], left, up, fwd, away)
        for foot in (I[side + "Heel"], I[side + "Toe"]):          # der Fuß dreht mit dem Unterschenkel mit
            x[:, foot] = rotate_to(x[:, foot], x[:, ankle], s2)
        x[:, knee], x[:, ankle] = t2, s2
    line = unit(x[:, I["lShoulder"]] - x[:, I["rShoulder"]])
    twist = np.clip(np.arctan2(dot(line, fwd), dot(line, left)), -45 * DEG, 45 * DEG)
    tilt = np.clip(np.arcsin(np.clip(dot(line, up), -1, 1)), -20 * DEG, 20 * DEG)
    line = np.cos(tilt) * (np.cos(twist) * left + np.sin(twist) * fwd) + np.sin(tilt) * up
    flat = unit(line - dot(line, up) * up)
    chest = np.cross(flat, up)
    for side, sign in (("l", 1.0), ("r", -1.0)):
        x[:, I[side + "Shoulder"]] = unit(math.cos(SHOULDER_DROOP) * sign * line - math.sin(SHOULDER_DROOP) * up)
        elbow, wrist = I[side + "Elbow"], I[side + "Wrist"]
        x[:, elbow], x[:, wrist] = limit_arm(x[:, elbow], x[:, wrist], sign * flat, chest, up)
    head = clamp_cone(x[:, I["head"]], up, 45 * DEG)
    x[:, I["nose"]] = rotate_to(x[:, I["nose"]], x[:, I["head"]], head)
    x[:, I["head"]] = head
    out[ok] = x
    return out


def limit_joints(p, max_lean=MAX_LEAN):
    """Gelenkgrenzen je Bild für H36M-Haltungen (T, 17, 3). Rückgabe: Haltungen, Zähler der Eingriffe.

    max_lean: größte Rumpfneigung gegen die Senkrechte, eine Zahl oder je Bild (T, 1); für
    Spieler am Boden π (keine Grenze)."""
    lengths = np.linalg.norm(p - p[:, H_PARENT], axis=2, keepdims=True)
    stats = {}

    def changed(name, before, after):
        stats[name] = stats.get(name, 0) + int((np.arccos(np.clip(dot(unit(before), unit(after)), -1, 1)) > 3 * DEG).sum())

    # Rumpf: höchstens MAX_LEAN gegen die Senkrechte. Der ganze Körper wird mitgedreht.
    up = unit(p[:, 8] - p[:, 0])
    z = np.broadcast_to([0, 0, 1.0], up.shape)
    target = clamp_cone(up, z, max_lean)
    changed("Rumpfneigung", up, target)
    axis = np.cross(up, target)
    s = np.linalg.norm(axis, axis=1, keepdims=True)
    k = axis / np.maximum(s, 1e-9)
    c = dot(up, target)
    p = np.where(s[:, None] > 1e-6,
                 p * c[:, None] + np.cross(k[:, None], p) * s[:, None] + k[:, None] * (k[:, None] * p).sum(-1, keepdims=True) * (1 - c[:, None]), p)

    up = unit(p[:, 8] - p[:, 0])
    left = p[:, 4] - p[:, 1]
    left = unit(left - dot(left, up) * up)
    fwd = np.cross(left, up)
    d = {j: unit(p[:, j] - p[:, H_PARENT[j]]) for j in range(1, 17)}

    # Becken: Hüftlinie quer zum Rumpf
    d[4], d[1] = left, -left
    # Wirbelsäule: geht nahezu gerade vom Becken zur Brust
    d[7] = clamp_cone(d[7], up, 20 * DEG)
    d[8] = clamp_cone(d[8], up, 20 * DEG)

    for hip, knee, ankle, out in ((4, 5, 6, left), (1, 2, 3, -left)):
        t2, s2 = limit_leg(d[knee], d[ankle], left, up, fwd, out)
        changed("Hüfte", d[knee], t2)
        changed("Knie", d[ankle], s2)
        d[knee], d[ankle] = t2, s2

    # Schultergürtel: gegen das Becken um höchstens 45° verdreht und 20° gekippt
    line = unit(p[:, 11] - p[:, 14])
    twist = np.clip(np.arctan2(dot(line, fwd), dot(line, left)), -45 * DEG, 45 * DEG)
    tilt = np.clip(np.arcsin(np.clip(dot(line, up), -1, 1)), -20 * DEG, 20 * DEG)
    line2 = np.cos(tilt) * (np.cos(twist) * left + np.sin(twist) * fwd) + np.sin(tilt) * up
    changed("Schultergürtel", line, line2)
    d[11], d[14] = line2, -line2
    flat = unit(line2 - dot(line2, up) * up)   # Schulterlinie ohne Kippung: rechtwinklig zu Rumpf und Brust
    chest = np.cross(flat, up)  # nach vorn aus der Brust

    for elbow, wrist, out in ((12, 13, flat), (15, 16, -flat)):
        u2, w2 = limit_arm(d[elbow], d[wrist], out, chest, up)
        changed("Oberarm", d[elbow], u2)
        changed("Ellbogen", d[wrist], w2)
        d[elbow], d[wrist] = u2, w2

    # Hals und Kopf: höchstens 45° gegen den Rumpf
    d9 = clamp_cone(d[9], up, 45 * DEG)
    d10 = clamp_cone(d[10], up, 45 * DEG)
    changed("Kopf", d[10], d10)
    d[9], d[10] = d9, d10

    out = np.zeros_like(p)
    for j in range(1, 17):
        out[:, j] = out[:, H_PARENT[j]] + d[j] * lengths[:, j]
    return out, stats


def bone_lengths(height):
    """Knochenlängen des 20-Gelenk-Skeletts für eine Körpergröße in Metern."""
    chain = CHAIN_SHARE * height
    foot = height / 1.70
    shoulder = 0.5 * SHARE["shoulderWidth"] * chain / math.cos(SHOULDER_DROOP)   # Halsansatz -> Schultergelenk
    drop = math.sin(SHOULDER_DROOP) * shoulder                                    # Halsansatz liegt über der Schulterlinie
    hip = 0.5 * SHARE["hipWidth"] * chain
    return {"neck": SHARE["torso"] * chain + drop, "head": SHARE["head"] * chain - drop, "nose": 0.10 * foot,
            "lShoulder": shoulder, "rShoulder": shoulder, "lElbow": SHARE["upperArm"] * chain, "rElbow": SHARE["upperArm"] * chain,
            "lWrist": SHARE["foreArm"] * chain, "rWrist": SHARE["foreArm"] * chain, "lHip": hip, "rHip": hip,
            "lKnee": SHARE["thigh"] * chain, "rKnee": SHARE["thigh"] * chain, "lAnkle": SHARE["shank"] * chain, "rAnkle": SHARE["shank"] * chain,
            "lHeel": 0.092 * foot, "rHeel": 0.092 * foot, "lToe": 0.25 * foot, "rToe": 0.25 * foot}


def directions_from_h36m(p):
    """H36M-Haltungen (T, 17, 3) -> Knochenrichtungen des 20-Gelenk-Skeletts (T, 20, 3); Becken bleibt 0.

    Fersen und Fußspitzen misst das 3D-Modell nicht. Aufrecht zeigen die Füße in Körperrichtung,
    bei angehobenem Fuß hängt die Spitze nach unten. Am Boden stehen sie rechtwinklig vom
    Unterschenkel ab, in Richtung der Brust."""
    T = len(p)
    d = np.zeros((T, 20, 3))
    z = np.array([0, 0, 1.0])
    up = unit(p[:, 8] - p[:, 0])
    left = unit(p[:, 4] - p[:, 1])
    upright = up[:, 2:3] > 0.7
    chest = unit(np.cross(left, up))  # aus der Brust heraus
    fwd = np.where(upright, unit(np.cross(left, z)), chest)
    head_centre = (p[:, 9] + p[:, 10]) / 2
    d[:, I["neck"]] = up
    d[:, I["head"]] = unit(head_centre - p[:, 8])
    shoulders = unit(p[:, 11] - p[:, 14])
    face = np.where(upright, unit(np.cross(shoulders, z)), unit(np.cross(shoulders, up)))
    d[:, I["nose"]] = unit(face * 0.95 - np.where(upright, z, up) * 0.3)
    for side, sh, el, wr, hip, kn, an in (("l", 11, 12, 13, 4, 5, 6), ("r", 14, 15, 16, 1, 2, 3)):
        across = unit(p[:, sh] - p[:, 8])
        across = unit(across - dot(across, up) * up)
        d[:, I[side + "Shoulder"]] = unit(math.cos(SHOULDER_DROOP) * across - math.sin(SHOULDER_DROOP) * up)
        d[:, I[side + "Elbow"]] = unit(p[:, el] - p[:, sh])
        d[:, I[side + "Wrist"]] = unit(p[:, wr] - p[:, el])
        d[:, I[side + "Hip"]] = unit(p[:, hip] - p[:, 0])
        d[:, I[side + "Knee"]] = unit(p[:, kn] - p[:, hip])
        shank = unit(p[:, an] - p[:, kn])
        d[:, I[side + "Ankle"]] = shank
        # aufrecht: Der tiefere Knöchel steht, der höhere Fuß hängt mit der Spitze nach unten
        lift = np.clip((p[:, an, 2] - np.minimum(p[:, 3, 2], p[:, 6, 2])) * 3.0, 0, 0.9)[:, None]
        toe_up = unit(np.cos(lift) * fwd - np.sin(lift) * z)
        sole_up = -unit(np.cross(np.cross(toe_up, z), toe_up))  # von der Sohle weg nach unten
        # am Boden: Fuß rechtwinklig zum Unterschenkel
        toe_down = unit(chest - dot(chest, shank) * shank)
        toe = np.where(upright, toe_up, toe_down)
        sole = np.where(upright, sole_up, shank)
        d[:, I[side + "Heel"]] = unit(-0.65 * toe + 0.76 * sole)
        d[:, I[side + "Toe"]] = toe
    return d


def lying_pose(heading):
    """Ersatzhaltung für einen Spieler am Boden ohne erkennbare Gelenke: gestreckt auf dem Rücken, Kopf in Richtung heading (2)."""
    hd = np.array([heading[0], heading[1], 0.0])
    left = np.cross(hd, [0, 0, 1.0])
    p = np.zeros((17, 3))
    p[8] = hd * 0.5
    p[7] = hd * 0.25
    p[9], p[10] = hd * 0.62, hd * 0.75
    for sign, hip, kn, an, sh, el, wr in ((1, 4, 5, 6, 11, 12, 13), (-1, 1, 2, 3, 14, 15, 16)):
        p[hip] = left * 0.1 * sign
        p[kn] = p[hip] - hd * 0.45
        p[an] = p[kn] - hd * 0.45
        p[sh] = p[8] + left * 0.18 * sign
        p[el] = p[sh] - hd * 0.28 + left * 0.06 * sign
        p[wr] = p[el] - hd * 0.25
    return p


def smooth_directions(d, fps):
    """Begrenzt je Knochen die Drehgeschwindigkeit und glättet; d: (T, 20, 3), NaN = Spieler nicht da."""
    out = d.copy()
    present = ~np.isnan(d[:, 1, 0])
    edges = np.flatnonzero(np.diff(np.r_[False, present, False].astype(int)))
    for a, b in zip(edges[::2], edges[1::2]):
        for name in ORDER:
            j = I[name]
            key = name if name in SPEED else name[1:]
            max_step, cutoff = SPEED[key][0] / fps, SPEED[key][1]
            x = d[a:b, j]
            passes = []
            for seq in (x, x[::-1]):
                y = seq.copy()
                for t in range(1, len(y)):
                    c = float(np.clip(y[t - 1] @ seq[t], -1, 1))
                    angle = math.acos(c)
                    if angle > max_step:
                        perp = unit(seq[t] - c * y[t - 1])
                        y[t] = math.cos(max_step) * y[t - 1] + math.sin(max_step) * perp
                    else:
                        y[t] = seq[t]
                passes.append(y)
            y = unit(passes[0] + passes[1][::-1])
            if b - a > 12:
                bb, aa = butter(2, min(0.99, cutoff / (fps / 2)))
                y = unit(filtfilt(bb, aa, y, axis=0))
            out[a:b, j] = y
    return out


# Abstand der Gelenkmitte vom Rasen, wenn das Körperteil aufliegt (halbe Dicke); Fuß: Sohle.
CLEARANCE = np.array([{"pelvis": 0.11, "neck": 0.11, "head": 0.11, "nose": 0.03, "Shoulder": 0.07, "Elbow": 0.045, "Wrist": 0.04,
                       "Hip": 0.09, "Knee": 0.06, "Ankle": 0.07, "Heel": 0.0, "Toe": 0.0}[n if n in ("pelvis", "neck", "head", "nose") else n[1:]]
                      for n in NAMES])


def build(d, lengths):
    """Knochenrichtungen (T, 20, 3) und Längen -> Gelenkpositionen relativ zum Bodenpunkt unter dem Becken.

    Der tiefste Punkt des Körpers liegt auf dem Rasen auf: im Stand die Sohle, am Boden Rücken,
    Becken, Knie oder was sonst unten ist, jeweils mit der halben Dicke des Körperteils."""
    T = len(d)
    p = np.zeros((T, 20, 3))
    for name in ORDER:
        p[:, I[name]] = p[:, I[PARENT[name]]] + d[:, I[name]] * lengths[name]
    p[:, :, 2] -= (p[:, :, 2] - CLEARANCE).min(axis=1)[:, None]
    p[np.isnan(d[:, 1, 0])] = np.nan
    return p


def limit_turn(d, fps, fastest=540 * DEG):
    """Begrenzt, wie schnell sich der Körper um die Hochachse dreht (rad/s); d: (T, 20, 3), NaN = nicht da.

    Aus einem Laufweg abgeleitete Blickrichtungen springen, wenn der Spieler fast steht. Die Drehung des
    Beckens wird vorwärts und rückwärts begrenzt und der ganze Körper mitgedreht."""
    out = d.copy()
    for a, b in runs(~np.isnan(d[:, 1, 0]), 3):
        left = d[a:b, I["lHip"]] - d[a:b, I["rHip"]]
        yaw = np.unwrap(np.arctan2(left[:, 1], left[:, 0]))
        step = fastest / fps
        passes = []
        for seq in (yaw, yaw[::-1]):
            y = seq.copy()
            for t in range(1, len(y)):
                y[t] = y[t - 1] + min(max(seq[t] - y[t - 1], -step), step)
            passes.append(y)
        turn = (passes[0] + passes[1][::-1]) / 2 - yaw
        c, s = np.cos(turn)[:, None], np.sin(turn)[:, None]
        x, y = out[a:b, :, 0].copy(), out[a:b, :, 1].copy()
        out[a:b, :, 0], out[a:b, :, 1] = c * x - s * y, s * x + c * y
    return out


def directions_of(joints):
    """Knochenrichtungen (T, 20, 3) aus Gelenkpositionen (T, 20, 3); Becken bleibt 0."""
    d = np.zeros_like(joints)
    for name in ORDER:
        d[:, I[name]] = unit(joints[:, I[name]] - joints[:, I[PARENT[name]]])
    d[np.isnan(joints[:, 1, 0])] = np.nan
    return d


def balance_depth(d, lengths, positions, eye, fps, skip=None, rounds=3):
    """Stellt die Figur in Blickrichtung der Kamera ins Gleichgewicht.

    Wie weit sich ein Spieler zur Kamera hin oder von ihr weg neigt, sieht eine Kamera nicht. Die
    Neigung in dieser Richtung wird deshalb so gewählt, dass er nicht umfällt: Der Schwerpunkt liegt im
    Mittel über den stehenden Füßen, verschoben um das, was Beschleunigung und Kurvenlauf verlangen.
    Jedes Gelenk wird dazu in Blickrichtung verschoben, umso weiter, je höher es liegt (Scherung): Die
    Füße bleiben, wo sie sind, und beide am Boden; der Bodenpunkt unter dem Becken wandert mit.
    d: (T, 20, 3), positions: (T, 2), eye: Kamerastandort, skip: Bilder ohne Eingriff (Spieler am Boden).
    Ohne Kamerastandort (eye None: Haltung nur aus dem Laufweg erzeugt, nichts gemessen) wird in jede
    Richtung ausgeglichen. Rückgabe: neue Richtungen und neue Bodenpunkte."""
    import check_motion
    out, positions = d.copy(), positions.copy()
    ok = ~np.isnan(d[:, 1, 0]) & ~np.isnan(positions[:, 0])
    if ok.sum() < 8:
        return out, positions
    names = {n: i for i, n in enumerate(NAMES)}
    view = unit(np.nan_to_num(positions) - np.asarray(eye, float)[:2]) if eye is not None else None
    bb, aa = butter(2, min(0.99, 1.5 / (fps / 2)))
    for _ in range(rounds):
        joints = build(out, lengths)
        with np.errstate(invalid="ignore"):
            _, off = check_motion.balance(joints[:, None], names, np.where(ok[:, None], positions, np.nan)[:, None], fps)
        error = off[:, 0] if view is None else (off[:, 0] * view).sum(axis=1, keepdims=True) * view
        slope = -error / np.maximum(joints[:, I["pelvis"], 2:3], 0.4)                    # Verschiebung je Meter Höhe (T, 2)
        slope = np.where(np.isnan(slope) | ~ok[:, None], 0.0, slope)
        slope *= np.minimum(1.0, 0.4 / np.maximum(np.linalg.norm(slope, axis=1, keepdims=True), 1e-9))
        if skip is not None:
            slope[skip] = 0.0
        if len(slope) > 12:
            slope = filtfilt(bb, aa, slope, axis=0)
        height = np.maximum(joints[:, :, 2] - 0.07, 0.0)                                 # ab Knöchelhöhe
        joints[:, :, :2] += height[:, :, None] * slope[:, None, :]
        feet = [I[n] for n in NAMES if n.endswith(("Heel", "Toe"))]
        fresh = directions_of(joints)
        fresh[:, feet] = out[:, feet]                                                    # Füße bleiben flach
        out = np.where(ok[:, None, None], fresh, out)
        positions[ok] += (slope * height[:, I["pelvis"], None])[ok]                      # Becken wandert, Füße bleiben im Feld
    return out, positions


def runs(mask, minimum=1):
    edges = np.flatnonzero(np.diff(np.r_[False, mask, False].astype(int)))
    return [(a, b) for a, b in zip(edges[::2], edges[1::2]) if b - a >= minimum]
