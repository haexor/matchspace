"""Körperbau je Spieler aus dem Körpermodell (Hilfsmodul): Schulter- und Hüftbreite, Längen von Oberschenkel, Unterschenkel, Rumpf und Armen.

Die Größe eines Spielers kommt aus der Messung im Bild (tools/scene_positions.py), die Proportionen bisher aus einer einzigen Schablone
(pose_limits.SHARE). Jeder Spieler ist aber anders breit und gebaut. tools/veo_body.py liefert je Bild 70 Punkte; ihre Abstände sind unabhängig von
der Drehung des Körpers und damit je Bild ein Maß für den Bau. Hier: Abstände im Verhältnis zur Körperlänge (Oberschenkel + Unterschenkel + Rumpf),
Median über alle Bilder des Spielers, dann im Verhältnis zum Median aller Spieler. Das Körpermodell schätzt den Bau aus rund 100 Pixeln und neigt
zum Durchschnitt; gemeinsame Verzerrungen (etwa erwachsene Proportionen) fallen durch den Vergleich der Spieler untereinander heraus, und wenige
Bilder ziehen den Wert zur Schablone hin.
"""
import numpy as np

from body_pose import (L_ELBOW, L_HIP, L_KNEE, L_ANKLE, L_SHOULDER, L_WRIST, NECK, R_ELBOW, R_HIP, R_KNEE, R_ANKLE, R_SHOULDER,
                       R_WRIST)

PARTS = ("shoulder", "hip", "thigh", "shank", "torso", "upperArm", "foreArm")
MIN_ROWS = 15        # Bilder, ab denen ein Spieler zum Vergleichswert (Median aller Spieler) beiträgt
MIN_BOX = 60.0       # Pixel Boxhöhe: darunter ist der Bau im Bild nicht zu erkennen
SHRINK = 40.0        # Bilder: so viele Bilder wiegen so viel wie die Schablone (n / (n + SHRINK) Anteil der Messung)
WIDTH_RANGE = (0.85, 1.2)    # Faktor auf Schulter- und Hüftbreite
LENGTH_RANGE = (0.93, 1.07)  # Faktor auf Längen der Knochen


def _ratios(kp: np.ndarray) -> np.ndarray:
    """(n, 70, 3) -> (n, 7): PARTS, jeweils geteilt durch die Körperlänge (Oberschenkel + Unterschenkel + Rumpf)."""
    d = lambda a, b: np.linalg.norm(kp[:, a] - kp[:, b], axis=1)
    mean = lambda a, b: (a + b) / 2
    pelvis = (kp[:, L_HIP] + kp[:, R_HIP]) / 2
    thigh = mean(d(L_HIP, L_KNEE), d(R_HIP, R_KNEE))
    shank = mean(d(L_KNEE, L_ANKLE), d(R_KNEE, R_ANKLE))
    torso = np.linalg.norm(kp[:, NECK] - pelvis, axis=1)
    length = thigh + shank + torso
    parts = np.stack([d(L_SHOULDER, R_SHOULDER), d(L_HIP, R_HIP), thigh, shank, torso,
                      mean(d(L_SHOULDER, L_ELBOW), d(R_SHOULDER, R_ELBOW)), mean(d(L_ELBOW, L_WRIST), d(R_ELBOW, R_WRIST))], axis=1)
    return parts / np.maximum(length, 1e-6)[:, None]


def measure(body: dict, min_box=MIN_BOX) -> dict:
    """Bau je Spieler: {Kennung: {"rows": n, PARTS...: Faktor gegen den Durchschnitt aller Spieler (1 = durchschnittlich)}}.
    body: Inhalt von veo_body.py mit ids. Spieler ohne verwertbare Bilder fehlen im Ergebnis."""
    if not len(body["player"]):
        return {}
    kp = np.asarray(body["kp3d"], float)
    ratio = _ratios(kp)
    box_h = body["box"][:, 3] - body["box"][:, 1]
    ok = (box_h >= min_box) & np.isfinite(ratio).all(axis=1) & (ratio > 0.02).all(axis=1) & (ratio < 1.2).all(axis=1)
    per, ids = {}, list(body["ids"])
    for p in np.unique(body["player"]):
        rows = ok & (body["player"] == p)
        if rows.any():
            per[ids[p]] = (np.median(ratio[rows], axis=0), int(rows.sum()))
    solid = [r for r, n in per.values() if n >= MIN_ROWS]
    if not solid:
        return {}
    population = np.median(solid, axis=0)
    out = {}
    for pid, (r, n) in per.items():
        weight = n / (n + SHRINK)
        dev = 1 + weight * (r / population - 1)
        build = {"rows": n}
        for i, name in enumerate(PARTS):
            lo, hi = WIDTH_RANGE if name in ("shoulder", "hip") else LENGTH_RANGE
            build[name] = float(np.clip(dev[i], lo, hi))
        out[pid] = build
    return out


def apply(lengths: dict, build: dict | None) -> dict:
    """Knochenlängen (pose_limits.bone_lengths) mit dem Bau des Spielers. Die Körperhöhe (Oberschenkel + Unterschenkel + Rumpf) bleibt die gemessene:
    Was ein Teil länger ist, wird den anderen abgezogen. Ohne Bau unverändert."""
    if not build:
        return lengths
    out = dict(lengths)
    chain = [("lKnee", "rKnee", "thigh"), ("lAnkle", "rAnkle", "shank"), ("neck", None, "torso")]
    before = sum(lengths[a] for a, _, _ in chain)
    after = sum(lengths[a] * build[part] for a, _, part in chain)
    keep = before / after if after > 0 else 1.0
    for a, b, part in chain:
        for name in (a, b):
            if name:
                out[name] = lengths[name] * build[part] * keep
    for sides, part in ((("lShoulder", "rShoulder"), "shoulder"), (("lHip", "rHip"), "hip"), (("lElbow", "rElbow"), "upperArm"), (("lWrist", "rWrist"), "foreArm")):
        for name in sides:
            out[name] = lengths[name] * build[part]
    return out
