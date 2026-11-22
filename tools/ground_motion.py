#!/usr/bin/env python3
"""Bewegung eines Spielers, der zu Boden geht, liegt und wieder aufsteht.

Aus einem Blickwinkel und bei rund 55 Pixeln Körpergröße lassen sich die Gelenke eines liegenden
Spielers nicht einzeln ablesen: Was dabei herauskam, waren verdrehte, unmögliche Haltungen. Verlässlich
messbar ist dagegen, wie hoch der Körper noch aufragt (Höhe der Box im Verhältnis zur Körpergröße) und
wann er liegt. Daraus wird hier ein Ablauf aus festen, möglichen Haltungen gebildet:

    hinfallen:  aufrecht -> vorgebeugt -> auf Händen und Knien -> bäuchlings
    liegen:     bäuchlings -> auf der Seite, Beine angezogen
    aufstehen:  auf der Seite -> sitzend, auf die Hände gestützt -> sitzend -> kniend/hockend -> vorgebeugt -> aufrecht

Welche Haltung gilt, bestimmt die gemessene Höhe; zwischen den Haltungen wird überblendet. Der Sturz
geht in Laufrichtung. Das ist eine plausible Darstellung, keine gelenkgenaue Messung.

Koordinaten der Vorlagen: x nach vorn (Fallrichtung, im Liegen zum Kopf), y nach links, z hoch.
"""
import math

import numpy as np

import pose_limits
from pose_limits import I, NAMES, unit

UPRIGHT = 1.0   # Höhe als Anteil der Körpergröße, ab der die gemessene Haltung gilt


def _template(up, left, limbs, planted=()):
    """Baut Knochenrichtungen (20, 3) aus Rumpfachse, Links-Vektor und den Richtungen der Gliedmaßen.

    limbs: lKnee, lAnkle, rKnee, rAnkle, lElbow, lWrist, rElbow, rWrist, head. planted: Seiten ("l", "r"),
    deren Fuß flach auf dem Rasen steht; sonst steht der Fuß rechtwinklig vom Unterschenkel ab."""
    up, left = unit(np.array(up, float)), np.array(left, float)
    left = unit(left - (left @ up) * up)
    chest = np.cross(left, up)
    d = np.zeros((20, 3))
    d[I["neck"]] = up
    d[I["lHip"]], d[I["rHip"]] = left, -left
    d[I["lShoulder"]], d[I["rShoulder"]] = left, -left
    for name, v in limbs.items():
        d[I[name]] = unit(np.array(v, float))
    d[I["nose"]] = unit(0.95 * chest - 0.3 * d[I["head"]])
    for side in "lr":
        shank = d[I[side + "Ankle"]]
        ahead = np.array([1.0, 0, 0]) if side in planted else chest
        toe = unit(ahead - (ahead @ shank) * shank) if side not in planted else np.array([1.0, 0, 0])
        d[I[side + "Toe"]] = toe
        d[I[side + "Heel"]] = unit(-0.65 * toe + 0.76 * (np.array([0, 0, -1.0]) if side in planted else shank))
    return pose_limits.limit_directions(d[None], math.pi)[0]


Y = np.array([0, 1.0, 0])
BENT = _template((0.5, 0, 0.87), Y, {
    "head": (0.64, 0, 0.77), "lKnee": (0.17, 0.09, -0.98), "lAnkle": (-0.17, 0, -0.98), "rKnee": (0.17, -0.09, -0.98), "rAnkle": (-0.17, 0, -0.98),
    "lElbow": (0.25, 0.15, -0.96), "lWrist": (0.5, 0, -0.87), "rElbow": (0.25, -0.15, -0.96), "rWrist": (0.5, 0, -0.87)}, planted="lr")
CROUCH = _template((0.42, 0, 0.91), Y, {
    "head": (0.5, 0, 0.87), "lKnee": (0.97, 0.17, -0.17), "lAnkle": (-0.26, 0, -0.97), "rKnee": (0.17, -0.1, -0.98), "rAnkle": (-0.98, 0, -0.17),
    "lElbow": (0.34, 0.2, -0.92), "lWrist": (0.64, 0, -0.77), "rElbow": (0.34, -0.2, -0.92), "rWrist": (0.64, 0, -0.77)}, planted="l")
SIT = _template((0.09, 0, 1.0), Y, {
    "head": (0.17, 0, 0.98), "lKnee": (0.77, 0.17, 0.62), "lAnkle": (0.5, 0, -0.87), "rKnee": (0.77, -0.17, 0.62), "rAnkle": (0.5, 0, -0.87),
    "lElbow": (-0.34, 0.26, -0.9), "lWrist": (-0.17, 0.1, -0.98), "rElbow": (-0.34, -0.26, -0.9), "rWrist": (-0.17, -0.1, -0.98)}, planted="lr")
PROPPED = _template((-0.6, 0, 0.8), Y, {   # sitzend, Oberkörper zurückgelehnt, auf die Hände gestützt
    "head": (-0.35, 0, 0.94), "lKnee": (0.94, 0.15, 0.3), "lAnkle": (0.9, 0.05, -0.43), "rKnee": (0.97, -0.12, 0.2), "rAnkle": (0.92, -0.05, -0.38),
    "lElbow": (-0.45, 0.35, -0.82), "lWrist": (-0.3, 0.15, -0.94), "rElbow": (-0.45, -0.35, -0.82), "rWrist": (-0.3, -0.15, -0.94)}, planted="lr")
ALL_FOURS = _template((0.97, 0, 0.24), Y, {
    "head": (0.87, 0, 0.5), "lKnee": (0.1, 0.1, -0.99), "lAnkle": (-0.98, 0, -0.17), "rKnee": (0.1, -0.1, -0.99), "rAnkle": (-0.98, 0, -0.17),
    "lElbow": (0.1, 0.1, -0.99), "lWrist": (0.05, 0, -1.0), "rElbow": (0.1, -0.1, -0.99), "rWrist": (0.05, 0, -1.0)})
PRONE = _template((1.0, 0, 0.03), Y, {
    "head": (0.98, 0, 0.2), "lKnee": (-1.0, 0.09, 0), "lAnkle": (-1.0, 0, 0.03), "rKnee": (-1.0, -0.09, 0), "rAnkle": (-1.0, 0, 0.03),
    "lElbow": (0.34, 0.94, 0), "lWrist": (0.94, -0.34, 0), "rElbow": (0.34, -0.94, 0), "rWrist": (0.94, 0.34, 0)})
SIDE = _template((1.0, 0, 0.03), (0, 0, -1.0), {   # auf der linken Seite, Gesicht nach -y
    "head": (1.0, -0.1, 0.05), "lKnee": (-0.5, -0.87, 0), "lAnkle": (-0.94, 0.34, 0), "rKnee": (-0.64, -0.77, 0.05), "rAnkle": (-0.9, 0.42, 0.05),
    "lElbow": (0.3, -0.95, -0.05), "lWrist": (0.9, -0.4, 0), "rElbow": (-0.3, -0.9, 0.3), "rWrist": (0.5, -0.8, -0.3)})

# Ketten aus (Höhe der Haltung als Anteil der Körpergröße, Haltung)
FALL = ((0.93, BENT), (0.58, ALL_FOURS), (0.21, PRONE))               # von oben nach unten
RISE = ((0.33, SIDE), (0.52, PROPPED), (0.63, SIT), (0.83, CROUCH), (0.93, BENT))      # von unten nach oben
TOP = 0.93                            # oberhalb davon geht es in die gemessene Haltung über
EDGE = 0.3                            # s: Übergang am Anfang und Ende der Bodenphase
ROLL_AFTER, ROLL_TAKES = 0.2, 0.7     # s: so lange nach dem Aufprall beginnt das Drehen auf die Seite, so lange dauert es
FALL_TAKES, RISE_TAKES = 0.5, 0.8     # s: spätestens so kurz vor dem Liegen fällt er, so lange vor dem Ende steht er auf
RISE_RATE = 0.9                       # Anteil der Körpergröße je Sekunde, um den sich ein Spieler höchstens aufrichtet
SIT_UP, SIT_FRAMES, MIN_LIE = 0.45, 4, 0.3   # ab dieser Höhe, so viele gemessene Bilder am Stück, frühestens so lange nach dem Aufprall: er sitzt


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def mix(a, b, w):
    """Überblendet Knochenrichtungen (..., 20, 3); w zwischen 0 (a) und 1 (b)."""
    w = np.asarray(w, float)[..., None, None]
    out = unit((1 - w) * a + w * b)
    out[..., I["pelvis"], :] = 0
    return out


def turn(d, yaw):
    """Dreht Knochenrichtungen (20, 3) um die Hochachse."""
    c, s = math.cos(yaw), math.sin(yaw)
    return d @ np.array([[c, s, 0], [-s, c, 0], [0, 0, 1.0]])


def _along(chain, h):
    """Haltung für die Höhe h auf einer Kette von (Höhe, Haltung); außerhalb gilt das Ende."""
    heights = [k[0] for k in chain]
    order = np.argsort(heights)
    heights, poses = [heights[i] for i in order], [chain[i][1] for i in order]
    if h <= heights[0]:
        return poses[0]
    if h >= heights[-1]:
        return poses[-1]
    k = int(np.searchsorted(heights, h)) - 1
    return mix(poses[k], poses[k + 1], smoothstep((h - heights[k]) / (heights[k + 1] - heights[k])))


def facing(d):
    """Blickrichtung einer Haltung (20, 3) als Winkel um die Hochachse."""
    left = d[I["lHip"]] - d[I["rHip"]]
    return math.atan2(-left[0], left[1])


def sequence(d, share, lying, floor, heading, fps):
    """Ersetzt in den Bodenphasen die Haltung durch den Ablauf fallen, liegen, aufstehen.

    d: (T, 20, 3) gemessene oder natürliche Haltung (gilt oberhalb der Bodenphasen und an deren Rändern),
    share: (T,) Höhe des Körpers als Anteil der Körpergröße (NaN, wo unbekannt), lying: (T,) Spieler liegt,
    floor: (T,) Bodenphase (umfasst lying samt Fallen und Aufstehen), heading: (T, 2) Laufrichtung."""
    out = d.copy()
    edges = np.flatnonzero(np.diff(np.concatenate([[0], floor.astype(int), [0]])))
    for a, b in zip(edges[::2], edges[1::2]):
        core = np.flatnonzero(lying[a:b])
        if not len(core) or np.isnan(d[a:b, 1, 0]).all():
            continue
        c, e = a + core[0], a + core[-1] + 1
        h = share[a:b].copy()
        known = ~np.isnan(h)
        # Das Liegen endet, sobald der Körper einige Bilder lang wieder Sitzhöhe hat; einzelne spätere
        # „liegt“-Befunde der Box (Verdeckung, Unschärfe) halten ihn sonst am Boden, während er schon aufsteht.
        up = np.flatnonzero(known & (h >= SIT_UP))
        for k in up[up >= c - a + int(MIN_LIE * fps)]:
            later = h[k:][known[k:]][:SIT_FRAMES]
            if len(later) >= SIT_FRAMES and (later >= SIT_UP).all():
                e = min(e, a + k)
                break
        h = np.interp(np.arange(b - a), np.flatnonzero(known), h[known]) if known.any() else np.full(b - a, 0.3)
        before = max(a, c - int(0.4 * fps))
        way = heading[before] if not np.isnan(heading[before, 0]) else np.array([1.0, 0.0])
        yaw_down = math.atan2(way[1], way[0])
        yaw_up = facing(d[b - 1]) if b < len(d) and not np.isnan(d[b - 1, 1, 0]) else yaw_down
        swing = (yaw_up - yaw_down + math.pi) % (2 * math.pi) - math.pi
        roll_end, last = None, 0.0
        for t in range(a, b):
            if np.isnan(d[t, 1, 0]):
                continue
            if t < c:      # hinfallen: die Höhe nimmt nur ab, und spätestens FALL_TAKES vor dem Liegen geht es abwärts
                height = min(h[:t - a + 1].min(), 0.21 + (c - t) / (FALL_TAKES * fps) * 0.8)
                pose, yaw = _along(FALL, height), yaw_down
            elif t < e:    # liegen: erst bäuchlings, dann auf die Seite
                roll = smoothstep(((t - c) / fps - ROLL_AFTER) / ROLL_TAKES)
                pose, yaw, height = mix(PRONE, SIDE, roll), yaw_down, 0.0
                roll_end = pose
            else:          # aufstehen: die Höhe nimmt nur zu, höchstens mit RISE_RATE, und RISE_TAKES vor dem Ende der Phase steht er
                height = h[t - a:].min()
                if b < len(d):
                    height = max(height, 1.0 - (b - t) / (RISE_TAKES * fps) * 0.67)
                height = min(height, last + RISE_RATE / fps)
                rise = ((RISE[0][0], roll_end if roll_end is not None else SIDE),) + RISE[1:]
                pose = _along(rise, height)
                yaw = yaw_down + swing * smoothstep((t - e) / max(b - e, 1))
            last = height
            pose = turn(pose, yaw)
            # oberhalb der vorgebeugten Haltung und an den Rändern der Bodenphase geht es in die gemessene über
            measured = smoothstep((height - TOP) / (UPRIGHT - TOP))
            if a > 0:
                measured = max(measured, 1 - smoothstep((t - a) / (EDGE * fps)))
            if b < len(d):
                measured = max(measured, 1 - smoothstep((b - 1 - t) / (EDGE * fps)))
            out[t] = mix(pose, d[t], measured) if measured > 0 else pose
    return out


if __name__ == "__main__":   # Kontrollbild der Vorlagen: jede Haltung von der Seite und von vorn
    import sys

    import cv2
    lengths = pose_limits.bone_lengths(1.55)
    names = ("BENT", "CROUCH", "SIT", "PROPPED", "ALL_FOURS", "PRONE", "SIDE")
    tiles = []
    for name in names:
        joints = pose_limits.build(globals()[name][None], lengths)[0]
        row = []
        for label, ax, sign in (("Seite", 0, 1), ("vorn", 1, -1), ("oben", None, 1)):
            img = np.full((220, 260, 3), 40, np.uint8)
            def pt(k, ax=ax, sign=sign):
                u, v = (joints[k, 0], joints[k, 1]) if ax is None else (sign * joints[k, ax], joints[k, 2])
                return (int(130 + u * 110), int((110 if ax is None else 205) - v * 110))
            for child in pose_limits.ORDER:
                colour = (80, 200, 255) if child.startswith("l") else (255, 200, 80) if child.startswith("r") else (230, 230, 230)
                cv2.line(img, pt(I[pose_limits.PARENT[child]]), pt(I[child]), colour, 2, cv2.LINE_AA)
            cv2.circle(img, pt(I["head"]), 7, (200, 200, 200), -1)
            cv2.circle(img, pt(I["nose"]), 2, (0, 0, 255), -1)
            cv2.putText(img, f"{name} {label}", (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
            row.append(img)
        tiles.append(np.hstack(row))
        print(name, "Höhe", round(float(joints[:, 2].max() + 0.1) / 1.55, 2), "tiefstes Gelenk", NAMES[int(joints[:, 2].argmin())])
    cv2.imwrite(sys.argv[1], np.vstack(tiles))
