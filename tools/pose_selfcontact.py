"""Arme und Hände nicht durch den eigenen Rumpf (Hilfsmodul für tools/scene_poses.py).

Aus dem Video gelesene Haltungen kennen den Rumpf nur als Linie: Hände vor dem Bauch, hinter dem Rücken oder an der Hüfte liegen darin oft im Rumpf. Der
Avatar zeigt dann den Unterarm mitten durch das Trikot (Zacken, dunkle Flammen an Saum und Hüfte). Hier wird der Rumpf als Ellipsenzylinder um die Linie
Becken–Hals gelegt (Maße aus dem Avatarnetz), jeder Arm bekommt seine Dicke, und Ellbogen und Handgelenk werden nach außen gedreht, bis nichts mehr im Rumpf
liegt. Knochenlängen bleiben, nur die Richtung ändert sich, und nur so viel wie nötig.

Achsen wie in tools/pose_limits.py: Haltungen (T, 20, 3) in der Reihenfolge synth_poses.NAMES, z hoch.
"""
import numpy as np

from synth_poses import NAMES

I = {n: i for i, n in enumerate(NAMES)}
TORSO_REF = 0.57              # m: Becken bis Hals beim Avatarnetz; Maße unten gelten dafür und werden mit der Rumpflänge des Spielers skaliert
HALF_WIDTH = 0.135            # m: halbe Rumpfbreite (Taille, Brust)
HIP_HALF_WIDTH = 0.18         # m: halbe Breite im Hüftbereich (Oberschenkel stehen seitlich heraus)
HIP_ZONE = 0.12               # m: bis zu dieser Höhe über dem Becken gilt die Hüftbreite
HALF_DEPTH = 0.10             # m: halbe Rumpftiefe
CENTRE = 0.01                 # m: Mitte des Rumpfs liegt so viel vor der Linie Becken–Hals
TOP = 0.42                    # m: darüber ist es die Schulter, der Arm setzt dort an
UPPER_RADIUS = 0.05           # m: Dicke von Oberarm samt Ärmel
FORE_RADIUS = 0.04            # m: Dicke von Unterarm und Hand
HAND = 0.5                    # Handlänge als Anteil des Unterarms: die Hand ragt über das Handgelenk hinaus
UPPER = (0.35, 0.65, 1.0)     # Messpunkte entlang des Oberarms (Anteil der Länge ab der Schulter)
FORE = (0.25, 0.5, 0.75, 1.0, 1.0 + HAND)
PASSES = 6
MAX_STEP = 0.15               # m: so weit rückt ein Gelenk je Durchgang höchstens


def unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9)


def frame(p):
    """Rumpfachsen je Bild: (oben, links, vorn, Skalierung) aus Becken, Hals und Hüftlinie; p: (T, 20, 3)."""
    up = unit(p[:, I["neck"]] - p[:, I["pelvis"]])
    left = p[:, I["lHip"]] - p[:, I["rHip"]]
    left = unit(left - (left * up).sum(-1, keepdims=True) * up)
    fwd = np.cross(left, up)
    scale = np.linalg.norm(p[:, I["neck"]] - p[:, I["pelvis"]], axis=-1) / TORSO_REF
    return up, left, fwd, scale


def locate(points, p, axes):
    """Punkte (T, 3) im Rumpfsystem: (links, vorn − Mitte, Höhe) in Metern des Avatarnetzes (durch die Rumpfskalierung geteilt)."""
    up, left, fwd, scale = axes
    r = points - p[:, I["pelvis"]]
    return np.stack([(r * left).sum(-1), (r * fwd).sum(-1), (r * up).sum(-1)], axis=-1) / scale[:, None] - np.array([0, CENTRE, 0])


def inside(local, radius):
    """Eindringtiefe in den Rumpf (m, 0 = außerhalb) und Richtung nach außen (links, vorn) je Punkt; local: (T, 3) aus `locate`."""
    lat, dep, h = local[:, 0], local[:, 1], local[:, 2]
    a = np.where(h < HIP_ZONE, HIP_HALF_WIDTH, HALF_WIDTH) + radius
    b = HALF_DEPTH + radius
    q = (lat / a) ** 2 + (dep / b) ** 2
    active = (h >= 0.0) & (h <= TOP) & (q < 1.0)
    radial = np.hypot(lat, dep)
    # Punkt auf der Mittellinie: Richtung unbestimmt, nach der Seite der größeren Breite schieben
    out = np.stack([np.where(radial > 1e-6, lat, 1.0), np.where(radial > 1e-6, dep, 0.0)], axis=-1)
    out = out / np.maximum(np.linalg.norm(out, axis=-1, keepdims=True), 1e-9)
    depth = np.where(active, radial * (1.0 / np.sqrt(np.maximum(q, 1e-9)) - 1.0), 0.0)
    return depth, out


def penetration(p):
    """Größte Eindringtiefe in den Rumpf je Bild und Arm: (T, 2) in m (links, rechts). NaN-Bilder ergeben 0."""
    axes = frame(p)
    depth = np.zeros((len(p), 2))
    for k, side in enumerate("lr"):
        s, e, w = (p[:, I[side + n]] for n in ("Shoulder", "Elbow", "Wrist"))
        for t in UPPER:
            depth[:, k] = np.maximum(depth[:, k], inside(locate(s + t * (e - s), p, axes), UPPER_RADIUS)[0])
        for t in FORE:
            depth[:, k] = np.maximum(depth[:, k], inside(locate(e + t * (w - e), p, axes), FORE_RADIUS)[0])
    return np.nan_to_num(depth)


def keep_arms_out(p, passes=PASSES):
    """Haltungen (T, 20, 3) mit Armen außerhalb des Rumpfs; NaN-Bilder bleiben. Verändert p nicht, gibt eine Kopie zurück."""
    out = p.copy()
    ok = ~np.isnan(p[:, I["neck"], 0])
    if not ok.any():
        return out
    x = out[ok]
    for _ in range(passes):
        axes = frame(x)
        up, left, fwd, scale = axes
        moved = False
        for side in "lr":
            s, e, w = (x[:, I[side + n]].copy() for n in ("Shoulder", "Elbow", "Wrist"))
            upper, fore = np.linalg.norm(e - s, axis=-1, keepdims=True), np.linalg.norm(w - e, axis=-1, keepdims=True)
            push_e, push_w = np.zeros_like(e), np.zeros_like(w)
            for t in UPPER:
                depth, out_dir = inside(locate(s + t * (e - s), x, axes), UPPER_RADIUS)
                step = (out_dir[:, :1] * left + out_dir[:, 1:] * fwd) * (depth * scale)[:, None] / t
                push_e = np.where(np.linalg.norm(step, axis=-1, keepdims=True) > np.linalg.norm(push_e, axis=-1, keepdims=True), step, push_e)
            for t in FORE:
                depth, out_dir = inside(locate(e + t * (w - e), x, axes), FORE_RADIUS)
                step = (out_dir[:, :1] * left + out_dir[:, 1:] * fwd) * (depth * scale)[:, None] / t
                push_w = np.where(np.linalg.norm(step, axis=-1, keepdims=True) > np.linalg.norm(push_w, axis=-1, keepdims=True), step, push_w)
            if not (np.linalg.norm(push_e, axis=-1).any() or np.linalg.norm(push_w, axis=-1).any()):
                continue
            moved = True
            cap = lambda v: v * np.minimum(1.0, MAX_STEP / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-9))   # noqa: E731
            e2 = s + unit(e + cap(push_e) - s) * upper
            w2 = e2 + unit(w + cap(push_w) - e2) * fore
            x[:, I[side + "Elbow"]], x[:, I[side + "Wrist"]] = e2, w2
        if not moved:
            break
    out[ok] = x
    return out
