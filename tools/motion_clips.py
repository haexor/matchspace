#!/usr/bin/env python3
"""Natürliche Bewegungsabläufe (Stehen, Gehen, Laufen) als Vorlage für die Körperhaltung (Hilfsmodul).

Das Körpermodell web/models/Xbot.glb bringt aufgezeichnete Bewegungen eines Menschen mit
(Motion Capture, Mixamo): Stehen, Gehen, Laufen, jeweils auf der Stelle. Daraus werden die
Richtungen der Knochen des 20-Gelenk-Skeletts gelesen und nach Schrittphase und Tempo
abrufbar gemacht. Diese Vorlage füllt alles, was das Video nicht zeigt: verdeckte Spieler,
nicht erkannte Gelenke, die Tiefe der Haltung. Sie ersetzt den früheren, von Hand gebauten
Laufzyklus.

Phase 0 ist der Moment, in dem der linke Fuß vorn aufsetzt; ein Umlauf (2π) ist ein Doppelschritt.
Körpersystem: x vorwärts, y links, z hoch.

Zum Ansehen:
    .venv/bin/python tools/motion_clips.py            # druckt Tempo und Schrittfrequenz der Vorlagen
"""
import json
import math
import struct
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from synth_poses import NAMES  # noqa: E402

MODEL = Path(__file__).parent.parent / "web" / "models" / "Xbot.glb"
PREFIX = "mixamorig:"
SAMPLES = 48          # Stützstellen je Doppelschritt
I = {n: i for i, n in enumerate(NAMES)}
PARENT = {"neck": "pelvis", "head": "neck", "nose": "head", "lShoulder": "neck", "rShoulder": "neck",
          "lElbow": "lShoulder", "rElbow": "rShoulder", "lWrist": "lElbow", "rWrist": "rElbow",
          "lHip": "pelvis", "rHip": "pelvis", "lKnee": "lHip", "rKnee": "rHip", "lAnkle": "lKnee", "rAnkle": "rKnee",
          "lHeel": "lAnkle", "rHeel": "rAnkle", "lToe": "lHeel", "rToe": "rHeel"}
ORDER = [n for n in NAMES if n != "pelvis"]
MAX_CADENCE = 1.75    # Doppelschritte je Sekunde im Sprint
SPRINT = 8.0          # m/s
STANDING = 0.5        # m/s: darunter steht der Spieler (die gemessene Bahn zittert um einige Dezimeter je Sekunde)
GAIT_RAMP = 0.25      # m/s über STANDING, bis die Beine die volle Kniebeugung des Gangs zeigen


def _quat_matrix(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


class _Glb:
    def __init__(self, path):
        raw = Path(path).read_bytes()
        size = struct.unpack("<I", raw[12:16])[0]
        self.g = json.loads(raw[20:20 + size])
        self.bin = raw[20 + size + 8:]
        self.nodes = self.g["nodes"]
        self.parent = {c: i for i, n in enumerate(self.nodes) for c in n.get("children", [])}
        self.index = {n.get("name"): i for i, n in enumerate(self.nodes)}

    def accessor(self, i):
        a = self.g["accessors"][i]
        view = self.g["bufferViews"][a["bufferView"]]
        width = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}[a["type"]]
        offset = view.get("byteOffset", 0) + a.get("byteOffset", 0)
        return np.frombuffer(self.bin, np.float32, a["count"] * width, offset).reshape(a["count"], width)

    def world(self, local):
        """local: {knoten: (t, q, s)} überschreibt die Ruhehaltung. Rückgabe: je Knoten (Drehung 3×3 samt Maßstab, Ort)."""
        cache = {}

        def solve(i):
            if i in cache:
                return cache[i]
            n = self.nodes[i]
            t, q, s = local.get(i, (n.get("translation", [0, 0, 0]), n.get("rotation", [0, 0, 0, 1]), n.get("scale", [1, 1, 1])))
            m, t = _quat_matrix(q) * np.asarray(s, float), np.asarray(t, float)
            if i in self.parent:
                pm, pt = solve(self.parent[i])
                m, t = pm @ m, pm @ t + pt
            cache[i] = (m, t)
            return cache[i]
        return solve

    def clip(self, name):
        """Rückgabe: Zeiten (n) und je Zeit ein dict knoten -> (t, q, s)."""
        anim = next(a for a in self.g["animations"] if a["name"] == name)
        times, tracks = None, {}
        for ch in anim["channels"]:
            sampler = anim["samplers"][ch["sampler"]]
            t = self.accessor(sampler["input"])[:, 0]
            times = t if times is None or len(t) > len(times) else times
            tracks.setdefault(ch["target"]["node"], {})[ch["target"]["path"]] = (t, self.accessor(sampler["output"]))
        frames = []
        for now in times:
            local = {}
            for node, paths in tracks.items():
                n = self.nodes[node]
                value = {}
                for path, default in (("translation", [0, 0, 0]), ("rotation", [0, 0, 0, 1]), ("scale", [1, 1, 1])):
                    if path in paths:
                        t, v = paths[path]
                        k = int(np.clip(np.searchsorted(t, now), 0, len(t) - 1))
                        value[path] = v[k]
                    else:
                        value[path] = n.get(path, default)
                local[node] = (value["translation"], value["rotation"], value["scale"])
            frames.append(local)
        return times, frames


def _joints(glb, local, rest_foot):
    """20 Gelenke im Körpersystem (x vorwärts, y links, z hoch) aus einer Haltung des Modells."""
    solve = glb.world(local)
    to_body = np.array([[0, 0, 1.0], [1.0, 0, 0], [0, 1.0, 0]])  # glTF: x links, y hoch, z vorwärts

    def at(name):
        return to_body @ solve(glb.index[PREFIX + name])[1]

    def turn(name):
        m = solve(glb.index[PREFIX + name])[0]
        return to_body @ (m / np.linalg.norm(m[:, 0]))
    out = np.zeros((20, 3))
    out[I["lHip"]], out[I["rHip"]] = at("LeftUpLeg"), at("RightUpLeg")
    out[I["pelvis"]] = (out[I["lHip"]] + out[I["rHip"]]) / 2
    out[I["neck"]] = at("Neck")
    out[I["head"]] = at("Head") + 0.45 * (at("HeadTop_End") - at("Head"))
    out[I["nose"]] = out[I["head"]] + turn("Head") @ np.array([0, 0, 0.1]) / 1.0
    for s, side in (("l", "Left"), ("r", "Right")):
        out[I[s + "Shoulder"]], out[I[s + "Elbow"]], out[I[s + "Wrist"]] = at(side + "Arm"), at(side + "ForeArm"), at(side + "Hand")
        out[I[s + "Knee"]], out[I[s + "Ankle"]] = at(side + "Leg"), at(side + "Foot")
        # Sohle: in der Ruhehaltung waagerecht; Ferse 6 cm hinter, Spitze 19 cm vor dem Knöchel, beide 7 cm tiefer
        r = turn(side + "Foot") @ rest_foot[side].T
        out[I[s + "Heel"]] = out[I[s + "Ankle"]] + r @ np.array([-0.06, 0, -0.07])
        out[I[s + "Toe"]] = out[I[s + "Ankle"]] + r @ np.array([0.19, 0, -0.07])
    return out


def _directions(joints):
    d = np.zeros(joints.shape)
    for name in ORDER:
        v = joints[..., I[name], :] - joints[..., I[PARENT[name]], :]
        d[..., I[name], :] = v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9)
    return d


def _cycle(glb, name, rest_foot):
    """Ein Doppelschritt, auf SAMPLES Stützstellen gebracht, Phase 0 = linker Fuß setzt vorn auf. Rückgabe: Gelenke, Tempo, Dauer."""
    times, frames = glb.clip(name)
    joints = np.array([_joints(glb, f, rest_foot) for f in frames])
    if np.allclose(joints[0], joints[-1], atol=0.02):   # letztes Bild wiederholt das erste
        times, joints = times[:-1], joints[:-1]
        period = float(times[-1] - times[0] + (times[1] - times[0]))
    else:
        period = float(times[-1] - times[0] + (times[1] - times[0]))
    rel = joints - joints[:, :1]
    start = int(np.argmax(rel[:, I["lAnkle"], 0]))
    joints = np.roll(joints, -start, axis=0)
    n = len(joints)
    src = np.arange(SAMPLES) * n / SAMPLES
    a = src.astype(int) % n
    w = (src - src.astype(int))[:, None, None]
    even = joints[a] * (1 - w) + joints[(a + 1) % n] * w
    # Tempo: so schnell wandert der stehende Fuß gegenüber dem Becken nach hinten
    rel = even - even[:, :1]
    back = []
    for foot in ("lAnkle", "rAnkle"):
        x, z = rel[:, I[foot], 0], even[:, I[foot], 2]
        v = (np.roll(x, -1) - np.roll(x, 1)) / (2 * period / SAMPLES)
        low = z < np.percentile(z, 35)
        back.append(-np.median(v[low]))
    return even, float(np.mean(back)), period


class Clips:
    def __init__(self, path=MODEL):
        glb = _Glb(path)
        rest_solve = glb.world({})
        to_body = np.array([[0, 0, 1.0], [1.0, 0, 0], [0, 1.0, 0]])
        rest_foot = {}
        for side in ("Left", "Right"):
            m = rest_solve(glb.index[PREFIX + side + "Foot"])[0]
            rest_foot[side] = to_body @ (m / np.linalg.norm(m[:, 0]))
        walk, self.walk_speed, walk_period = _cycle(glb, "walk", rest_foot)
        run, self.run_speed, run_period = _cycle(glb, "run", rest_foot)
        _, idle = glb.clip("idle")
        stand = np.mean([_joints(glb, f, rest_foot) for f in idle], axis=0)
        self.walk, self.run = _directions(walk), _directions(run)
        self.idle = _directions(stand)
        self.walk_cadence, self.run_cadence = 1 / walk_period, 1 / run_period
        self.run_mean = self.run.mean(axis=0)

    def cadence(self, speed):
        """Doppelschritte je Sekunde bei diesem Tempo (m/s)."""
        speed = np.asarray(speed, float)
        return np.interp(speed, [0.0, self.walk_speed, self.run_speed, SPRINT],
                         [0.75 * self.walk_cadence, self.walk_cadence, self.run_cadence, MAX_CADENCE])

    def directions(self, phase, speed):
        """Knochenrichtungen (..., 20, 3) im Körpersystem für Phase (rad) und Tempo (m/s); beide gleich geformt."""
        phase, speed = np.asarray(phase, float), np.asarray(speed, float)
        pos = (phase % (2 * math.pi)) / (2 * math.pi) * SAMPLES
        a = pos.astype(int) % SAMPLES
        w = (pos - np.floor(pos))[..., None, None]
        walk = self.walk[a] * (1 - w) + self.walk[(a + 1) % SAMPLES] * w
        run = self.run[a] * (1 - w) + self.run[(a + 1) % SAMPLES] * w
        s = speed[..., None, None]
        to_run = np.clip((s - self.walk_speed) / (self.run_speed - self.walk_speed), 0, 1)
        # über dem Tempo der Vorlage: Ausschlag um die mittlere Laufhaltung vergrößern
        extra = np.clip((s - self.run_speed) / self.run_speed, 0, 1) * 0.35
        fast = run + extra * (run - self.run_mean)
        slow = self._slow(walk, s)
        d = np.where(s <= self.walk_speed, slow, walk * (1 - to_run) + fast * to_run)
        d = d / np.maximum(np.linalg.norm(d, axis=-1, keepdims=True), 1e-9)
        d[..., I["pelvis"], :] = 0
        return d

    def _slow(self, walk, s):
        """Langsames Gehen: kürzere Schritte, aber dieselbe Kniebeugung im Schwung wie beim Gehen.

        Mischt man Stehen und Gehen einfach, wird jeder Winkel kleiner, auch die Beugung des Knies; das Bein
        schwingt dann steif wie eine Stelze. Hier wird nur der Ausschlag der Oberschenkel (und der Arme) auf
        die kürzere Schrittlänge verkleinert. Unterschenkel und Fuß folgen mit den Winkeln des Gangs."""
        def unit(v):
            return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9)

        def carry(u, v, w):  # dreht w mit der kürzesten Drehung, die u auf v legt
            k, c = np.cross(u, v), (u * v).sum(axis=-1, keepdims=True)
            return w * c + np.cross(k, w) + k * (k * w).sum(axis=-1, keepdims=True) / np.maximum(1 + c, 1e-6)

        gait = np.clip((s - STANDING) / GAIT_RAMP, 0, 1)
        gait = gait * gait * (3 - 2 * gait)
        stride = (s / self.cadence(s[..., 0, 0])[..., None, None]) / (self.walk_speed / self.walk_cadence)
        swing = np.clip(stride, 0, 1) * gait
        idle = np.broadcast_to(self.idle, walk.shape)
        d = unit(idle * (1 - swing) + walk * swing)
        for side in "lr":
            hip, knee, ankle = I[side + "Knee"], I[side + "Ankle"], [I[side + "Heel"], I[side + "Toe"]]
            thigh = d[..., hip, :]
            shank = carry(walk[..., hip, :], walk[..., knee, :], thigh)
            shank = unit(idle[..., knee, :] * (1 - gait[..., 0, :]) + shank * gait[..., 0, :])
            d[..., knee, :] = shank
            for f in ankle:
                foot = carry(walk[..., knee, :], shank, walk[..., f, :])
                d[..., f, :] = unit(idle[..., f, :] * (1 - gait[..., 0, :]) + foot * gait[..., 0, :])
        return d


@lru_cache(maxsize=1)
def load():
    return Clips()


if __name__ == "__main__":
    c = load()
    print(f"Gehen: {c.walk_speed:.2f} m/s bei {c.walk_cadence:.2f} Doppelschritten/s; Laufen: {c.run_speed:.2f} m/s bei {c.run_cadence:.2f}")
    print("Schrittfrequenz bei 0/2/4/6/8 m/s:", np.round(c.cadence([0, 2, 4, 6, 8]), 2))
