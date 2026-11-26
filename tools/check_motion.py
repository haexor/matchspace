#!/usr/bin/env python3
"""Prüft ein Spiel im Viewer-Format auf Bewegungen, die ein Mensch nicht machen kann.

Gezählt werden Bilder je Spieler, in denen eine Regel verletzt ist:

    Tempo          schneller als 9 m/s (32 km/h)
    Antritt        Beschleunigung über 9 m/s², über 0,2 s gemittelt
    Sprung         Ortswechsel über 0,5 m von einem Bild zum nächsten
    Knochenlänge   ein Knochen weicht mehr als 3 % von seiner üblichen Länge ab
    Boden          ein Gelenk liegt mehr als 4 cm unter dem Rasen
    Knie           Knie nach vorn durchgedrückt (mehr als 15° überstreckt)
    Hüfte          Oberschenkel mehr als 130° nach vorn oder 40° nach hinten, mehr als 60° abgespreizt oder 30° über die Mitte
    Gleichgewicht  aufrecht, aber der Körper hängt über 0,6 s im Mittel mehr als 30 cm neben den Füßen
                   (um das bereinigt, was Beschleunigung und Kurvenlauf an Schräglage verlangen)
    Hals           Kopf mehr als 60° gegen den Rumpf abgeknickt
    Rumpfdrehung   Schultern mehr als 60° gegen das Becken verdreht
    Körperdrehung  Becken dreht schneller als 720°/s
    Knochendrehung ein Knochen dreht schneller als 2000°/s
    Arm im Rumpf   Unterarm oder Hand mehr als 3 cm tief im eigenen Rumpf (Ellipsenzylinder um die Linie Becken–Hals, tools/pose_selfcontact.py)
    Schweben       beide Füße länger als 0,6 s mehr als 15 cm über dem Rasen

Aufruf:
    .venv/bin/python tools/check_motion.py SPIELORDNER [START_S ENDE_S] [--liste N]

Gibt je Regel die Zahl der Spieler-Bilder und die schlimmsten Stellen aus (Spieler, Sekunde), damit man
sie im Viewer ansehen kann: ?match=...&t=SEKUNDE&mode=follow&player=SPIELER
"""
import json
import sys
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import pose_selfcontact  # noqa: E402

DEG = np.pi / 180
MAX_SPEED, MAX_ACCEL, MAX_STEP = 9.0, 9.0, 0.5
ARM_IN_TORSO = 0.03          # m: so tief darf ein Arm in den Rumpf ragen
RULES = ("Tempo", "Antritt", "Sprung", "Knochenlänge", "Boden", "Knie", "Hüfte", "Hals", "Rumpfdrehung", "Körperdrehung", "Knochendrehung", "Schweben", "Gleichgewicht", "Arm im Rumpf")
MASS = (("pelvis", "neck", 0.50), ("head", "head", 0.08), ("lShoulder", "lElbow", 0.027), ("rShoulder", "rElbow", 0.027), ("lElbow", "lWrist", 0.022),
        ("rElbow", "rWrist", 0.022), ("lHip", "lKnee", 0.10), ("rHip", "rKnee", 0.10), ("lKnee", "lAnkle", 0.047), ("rKnee", "rAnkle", 0.047),
        ("lAnkle", "lToe", 0.014), ("rAnkle", "rToe", 0.014))     # Körperteile: von, bis, Anteil an der Masse


def unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9)


def angle(a, b):
    return np.arccos(np.clip((unit(a) * unit(b)).sum(axis=-1), -1, 1))


def runs(mask, least):
    """Markiert nur Abschnitte, die mindestens least Bilder lang sind."""
    out = np.zeros_like(mask)
    edges = np.flatnonzero(np.diff(np.concatenate([[0], mask.astype(int), [0]])))
    for a, b in zip(edges[::2], edges[1::2]):
        if b - a >= least:
            out[a:b] = True
    return out


def average(x, w):
    """Gleitendes Mittel über w Bilder entlang der Zeit, NaN zählt nicht mit; NaN, wo weniger als 60 % gültig sind."""
    good = ~np.isnan(x)
    kernel = np.ones(w)
    total = np.apply_along_axis(lambda c: np.convolve(c, kernel, "same"), 0, np.where(good, x, 0.0))
    count = np.apply_along_axis(lambda c: np.convolve(c, kernel, "same"), 0, good.astype(float))
    return np.where(count >= 0.6 * w, total / np.maximum(count, 1), np.nan)


def balance(j, n, xy, fps):
    """Abstand (m) zwischen dem Punkt, über dem der Körper im Gleichgewicht wäre, und der Mitte der stehenden Füße.

    j: Gelenke (T, P, 20, 3) relativ zum Bodenpunkt, n: Name -> Index, xy: Bodenpunkte (T, P, 2).
    Der Gleichgewichtspunkt ist der Schwerpunkt, verschoben um Höhe mal Beschleunigung durch Erdbeschleunigung
    (wer beschleunigt oder eine Kurve läuft, muss sich hineinlegen). Rückgabe: (Abstand, Vektor Füße -> Punkt)."""
    com = sum(share * (j[:, :, n[a]] + j[:, :, n[b]]) / 2 for a, b, share in MASS)
    world = com[..., :2] + xy
    # Beschleunigung aus der über eine Sekunde gemittelten Bahn: Kürzere Schwankungen sind bei der Genauigkeit
    # der Positionen (in Blickrichtung rund 0,3 m) Messrauschen und kein Antritt.
    w = max(int(round(1.0 * fps)) | 1, 3)
    smooth = average(average(world.reshape(len(world), -1), w), w).reshape(world.shape)
    acc = np.gradient(np.gradient(smooth, axis=0), axis=0) * fps * fps
    zmp = world - com[..., 2:3] / 9.81 * acc
    feet, weight = np.zeros_like(world), np.zeros(world.shape[:2] + (1,))
    for s in "lr":
        down = (j[:, :, n[s + "Ankle"], 2] < 0.13)[..., None]
        feet += np.where(down, (j[:, :, n[s + "Heel"], :2] + j[:, :, n[s + "Toe"], :2]) / 2 + xy, 0)
        weight += down
    support = np.where(weight > 0, feet / np.maximum(weight, 1), np.nan)
    off = (zmp - support).reshape(len(world), -1)
    off = average(off, max(int(round(0.6 * fps)), 1)).reshape(world.shape)
    upright = j[:, :, n["pelvis"], 2] > 0.55 * np.nanmedian(j[:, :, n["pelvis"], 2], axis=0)
    off = np.where(upright[..., None], off, np.nan)
    return np.linalg.norm(off, axis=2), off


def load(folder, start=None, end=None):
    folder = Path(folder)
    meta = json.loads((folder / "meta.json").read_text())
    fps, frames, entities = meta["fps"], meta["frames"], meta["entities"]
    a = 0 if start is None else int(float(start) * fps)
    b = frames if end is None else min(frames, int(float(end) * fps))
    tracks = np.memmap(folder / meta["tracks"]["file"], "<i2", "r").reshape(frames, len(entities), 3)[a:b]
    present = tracks[:, :, 0] != meta["tracks"]["missing"]
    pos = np.where(present[..., None], tracks * meta["tracks"]["scale"], np.nan)
    poses = meta.get("poses")
    joints = None
    if poses:
        names = [j["name"] for j in poses["skeleton"]["joints"]]
        slots = [i for i, e in enumerate(entities) if e["kind"] == "player"]
        block = poses["chunkFrames"]
        parts = []
        for k in range(a // block, (b - 1) // block + 1):
            raw = np.fromfile(folder / poses["path"].format(chunk=f"{k:03d}"), "<i2").reshape(-1, len(slots), len(names), 3)
            parts.append(raw[max(a - k * block, 0):b - k * block])
        raw = np.concatenate(parts)
        present[:, slots] &= (raw != poses["missing"]).all(axis=(2, 3))
        joints = (raw.astype(np.float32) * poses["scale"], names, slots, poses["skeleton"]["bones"])
    return meta, a, pos, present, joints


def check(folder, start=None, end=None):
    meta, first, pos, present, joints = load(folder, start, end)
    fps, entities = meta["fps"], meta["entities"]
    players = [i for i, e in enumerate(entities) if e["kind"] == "player"]
    found = {}     # Regel -> (Bilder, Spieler) bool

    xy = pos[:, players, :2]
    here = present[:, players]
    step = np.linalg.norm(np.diff(xy, axis=0, prepend=xy[:1]), axis=2)
    step[0] = 0
    with np.errstate(invalid="ignore"):
        found["Tempo"] = step * fps > MAX_SPEED
        found["Sprung"] = step > MAX_STEP
        w = max(int(round(0.2 * fps)), 1)
        vel = np.gradient(xy, axis=0) * fps
        acc = np.zeros(xy.shape[:2])
        acc[w:-w] = np.linalg.norm(vel[2 * w:] - vel[:-2 * w], axis=2) / (2 * w / fps)
        found["Antritt"] = acc > MAX_ACCEL
    values = {"Tempo": step * fps, "Sprung": step, "Antritt": acc}

    if joints is not None:
        j, names, slots, bones = joints
        n = {name: i for i, name in enumerate(names)}
        assert slots == players
        p = lambda name: j[:, :, n[name]]                                            # noqa: E731
        lengths = np.stack([np.linalg.norm(j[:, :, b["to"]] - j[:, :, b["from"]], axis=2) for b in bones], axis=2)
        with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            usual = np.nanmedian(np.where(here[..., None], lengths, np.nan), axis=0)
            dev = np.abs(lengths / np.maximum(usual, 1e-6) - 1).max(axis=2)
        found["Knochenlänge"] = dev > 0.03
        low = -j[..., 2].min(axis=2)
        found["Boden"] = low > 0.04
        spine = unit(p("neck") - p("pelvis"))
        left = unit(p("lHip") - p("rHip"))
        knee, hip = np.zeros(here.shape), np.zeros(here.shape)
        for s in "lr":
            thigh, shank = p(s + "Knee") - p(s + "Hip"), p(s + "Ankle") - p(s + "Knee")
            bend = angle(thigh, shank)
            forward = (np.cross(thigh, shank) * left).sum(axis=2) < 0               # Unterschenkel klappt nach vorn
            knee = np.maximum(knee, np.where(forward, bend, 0))
            fwd = np.cross(left, spine)
            away = left if s == "l" else -left
            spread = np.arcsin(np.clip((unit(thigh) * away).sum(axis=2), -1, 1))               # abspreizen (+) oder über die Mitte (-)
            swing = np.arctan2((thigh * fwd).sum(axis=2), -(thigh * spine).sum(axis=2))        # nach vorn (+) oder hinten (-)
            hip = np.maximum.reduce([hip, swing - 130 * DEG, -40 * DEG - swing, spread - 60 * DEG, -30 * DEG - spread])
        found["Knie"] = knee > 15 * DEG
        found["Hüfte"] = hip > 0
        neck = angle(p("head") - p("neck"), spine)
        found["Hals"] = neck > 60 * DEG
        shoulders = p("lShoulder") - p("rShoulder")
        flat = lambda v: v - (v * spine).sum(axis=2, keepdims=True) * spine          # noqa: E731
        twist = angle(flat(shoulders), flat(left))
        found["Rumpfdrehung"] = twist > 60 * DEG
        turn = np.zeros(here.shape)
        turn[1:] = angle(left[1:], left[:-1]) * fps
        found["Körperdrehung"] = turn > 720 * DEG
        spin = np.zeros(here.shape)
        for b in bones:
            d = unit(j[:, :, b["to"]] - j[:, :, b["from"]])
            spin[1:] = np.maximum(spin[1:], angle(d[1:], d[:-1]) * fps)
        found["Knochendrehung"] = spin > 2000 * DEG
        feet = np.minimum.reduce([j[:, :, n[k], 2] for k in ("lAnkle", "rAnkle", "lToe", "rToe", "lHeel", "rHeel")])
        air = feet > 0.15 + 0.07                                                     # Knöchel liegt rund 7 cm über der Sohle
        found["Schweben"] = np.stack([runs(air[:, k], int(0.6 * fps)) for k in range(air.shape[1])], axis=1)
        with np.errstate(invalid="ignore"):
            lean, _ = balance(j, n, np.where(here[..., None], xy, np.nan), fps)
            found["Gleichgewicht"] = np.nan_to_num(lean) > 0.30
        inner = np.stack([pose_selfcontact.penetration(j[:, k]) for k in range(j.shape[1])], axis=1).max(axis=2)      # tiefster Arm im Rumpf (m)
        found["Arm im Rumpf"] = inner > ARM_IN_TORSO
        values.update({"Arm im Rumpf": inner * 100, "Knochenlänge": dev, "Boden": low, "Knie": knee / DEG, "Hüfte": hip / DEG, "Hals": neck / DEG, "Rumpfdrehung": twist / DEG,
                       "Körperdrehung": turn / DEG, "Knochendrehung": spin / DEG, "Schweben": feet, "Gleichgewicht": np.nan_to_num(lean)})
    # Übergänge an Anfang und Ende der Anwesenheit zählen nicht
    edge = here & np.roll(here, 1, axis=0)
    edge[0] = False
    for k in found:
        found[k] = found[k] & (edge if k in ("Tempo", "Sprung", "Antritt", "Körperdrehung", "Knochendrehung") else here)
    return {"meta": meta, "first": first, "players": players, "present": here, "found": found, "values": values}


def report(result, listing=6):
    meta, here, found, values = result["meta"], result["present"], result["found"], result["values"]
    fps = meta["fps"]
    ids = [meta["entities"][i]["id"] for i in result["players"]]
    total = int(here.sum())
    print(f"{here.shape[0]} Bilder, {int(here.any(axis=0).sum())} Spieler, {total} Spieler-Bilder")
    any_bad = np.zeros_like(here)
    for rule in RULES:
        if rule not in found:
            continue
        bad = found[rule]
        any_bad |= bad
        line = f"  {rule:15s} {int(bad.sum()):7d} Spieler-Bilder ({bad.sum() / max(total, 1):6.2%}), {int(bad.any(axis=0).sum()):2d} Spieler"
        if bad.any() and listing:
            v = np.where(bad, np.nan_to_num(values[rule]), -np.inf)
            worst = []
            for k in np.argsort(-v.max(axis=0))[:listing]:
                if np.isfinite(v[:, k].max()):
                    f = int(v[:, k].argmax())
                    worst.append(f"{ids[k]} {(result['first'] + f) / fps:.1f}s ({v[f, k]:.1f})")
            line += "  schlimmste: " + ", ".join(worst)
        print(line)
    print(f"  mindestens eine Regel verletzt: {int(any_bad.sum())} Spieler-Bilder ({any_bad.sum() / max(total, 1):.2%})")
    return any_bad


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    listing = int(sys.argv[sys.argv.index("--liste") + 1]) if "--liste" in sys.argv else 6
    if "--liste" in sys.argv:
        args.remove(sys.argv[sys.argv.index("--liste") + 1])
    if len(args) not in (1, 3):
        sys.exit(__doc__)
    report(check(*args), listing)
