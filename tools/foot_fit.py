"""Füße aus dem Bild: Fußpunkte (Zehe, Ferse) aus tools/veo_feet.py in die Haltung einsetzen (Hilfsmodul).

Bisher standen Ferse und Fußspitze nach der Laufrichtung und zeigten oft quer zum echten Schuh. RTMPose (Halpe26) liest beide im Bild. Hier wird daraus
die Fußstellung im Raum: Der Fuß hat feste Längen (Knöchel zu Ferse, Ferse zu Zehe). Ein Bildpunkt legt nur den Sehstrahl fest; die Tiefe ergibt sich aus
der Länge: Der gesuchte Punkt liegt dort, wo der Strahl die Kugel um den Knöchel (Ferse) bzw. um die Ferse (Zehe) schneidet. Von zwei Schnittpunkten
gilt der näher an der bisherigen Stellung. Trifft der Strahl die Kugel nicht, wird der Punkt am nächsten Punkt der Kugel gesetzt. Nichts geht unter den
Rasen. Wo kein sicherer Bildpunkt vorliegt, bleibt die bisherige Stellung; Übergänge werden geglättet.

Außerdem: Die 17 COCO-Punkte von RTMPose und ViTPose werden zusammengeführt (merge_keypoints): Bei den Beinen zählt RTMPose mehr.
"""
import numpy as np

CONF = 0.3                        # darunter gilt ein Punkt als nicht gesehen
LEG_JOINTS = (13, 14, 15, 16)     # Knie und Knöchel: RTMPose liegt dort genauer
LEG_WEIGHT = 2.0                  # Gewicht von RTMPose gegenüber ViTPose bei den Beinen
RTM = {"lBigToe": 20, "rBigToe": 21, "lSmallToe": 22, "rSmallToe": 23, "lHeel": 24, "rHeel": 25}
SMOOTH = 2                        # Bilder je Seite beim Glätten der Fußvektoren
GROUND = 0.0                      # m: tiefster Fußpunkt


def merge_keypoints(vit: np.ndarray, rtm: np.ndarray) -> np.ndarray:
    """Führt zwei Schätzungen der 17 COCO-Punkte (n, 17, 3: x, y, Sicherheit) zusammen. Beide sicher: nach Sicherheit gemittelt, bei den Beinen
    zählt RTMPose doppelt; nur eine sicher: diese; keine sicher: ViTPose unverändert."""
    out = np.array(vit, float)
    r = np.asarray(rtm, float)[:, :17]
    cv, cr = out[..., 2], r[..., 2]
    wv = cv.copy()
    wr = cr * np.where(np.isin(np.arange(17), LEG_JOINTS), LEG_WEIGHT, 1.0)
    both = (cv >= CONF) & (cr >= CONF)
    only_r = (cr >= CONF) & ~(cv >= CONF)
    total = np.where(both, wv + wr, 1.0)
    out[..., :2] = np.where(both[..., None], (out[..., :2] * wv[..., None] + r[..., :2] * wr[..., None]) / total[..., None], out[..., :2])
    out[..., :2] = np.where(only_r[..., None], r[..., :2], out[..., :2])
    out[..., 2] = np.where(both, np.maximum(cv, cr), np.where(only_r, cr, cv))
    return out


def foot_points(kp26: np.ndarray) -> np.ndarray:
    """(n, 26, 3) -> (n, 4, 3): linke Zehe, rechte Zehe, linke Ferse, rechte Ferse (x, y, Sicherheit). Die Zehe ist die Mitte von großer und kleiner
    Zehe, wo beide sicher sind, sonst die sichere; nicht gesehen: Sicherheit 0."""
    kp26 = np.asarray(kp26, float)
    out = np.zeros((len(kp26), 4, 3))
    for k, side in enumerate("lr"):
        big, small = kp26[:, RTM[side + "BigToe"]], kp26[:, RTM[side + "SmallToe"]]
        heel = kp26[:, RTM[side + "Heel"]]
        ok_b, ok_s = big[:, 2] >= CONF, small[:, 2] >= CONF
        both = ok_b & ok_s
        toe = np.where(both[:, None], (big + small) / 2, np.where(ok_b[:, None], big, small))
        toe[:, 2] = np.where(both, np.minimum(big[:, 2], small[:, 2]), np.where(ok_b, big[:, 2], np.where(ok_s, small[:, 2], 0.0)))
        out[:, k], out[:, 2 + k] = toe, heel
    return out


def sphere_point(origin, direction, centre, radius, prior):
    """Punkt auf der Kugel (centre, radius), der auf dem Strahl origin + t * direction liegt; von zwei Schnittpunkten der näher an prior.
    Verfehlt der Strahl die Kugel, der Punkt der Kugel, der dem Strahl am nächsten liegt."""
    d = direction / np.linalg.norm(direction)
    oc = origin - centre
    b = float(oc @ d)
    disc = b * b - (float(oc @ oc) - radius * radius)
    if disc < 0:
        closest = origin + (-b) * d
        v = closest - centre
        return centre + v / max(np.linalg.norm(v), 1e-9) * radius
    root = np.sqrt(disc)
    near, far = origin + (-b - root) * d, origin + (-b + root) * d
    return near if np.linalg.norm(near - prior) <= np.linalg.norm(far - prior) else far


def smooth_vectors(v: np.ndarray, valid: np.ndarray, half: int = SMOOTH) -> np.ndarray:
    """Gleitender Mittelwert über gültige Nachbarn (n, 3); ungültige Bilder bleiben NaN."""
    out = np.full_like(v, np.nan)
    for i in np.flatnonzero(valid):
        lo, hi = max(0, i - half), min(len(v), i + half + 1)
        sel = valid[lo:hi]
        out[i] = v[lo:hi][sel].mean(axis=0)
    return out


def apply(joints: np.ndarray, pos: np.ndarray, foot2d: np.ndarray, lens: np.ndarray, cam: dict, names: list, rays) -> tuple:
    """Fußstellung aus den Bildpunkten. joints (n, 20, 3): Gelenke relativ zur Lage pos (n, 2), Höhe absolut; foot2d (n, 4, 3) wie foot_points
    (Pixel der Linse lens (n,), NaN ohne Erkennung); names: Gelenknamen; rays(cam, linsenname, pixel) -> Richtungen (veo_camera.rays).
    Rückgabe: (neue joints, Zahl der Bilder je Fuß, die aus dem Bild gesetzt wurden)."""
    out = joints.copy()
    I = {n: i for i, n in enumerate(names)}
    changed = 0
    for k, side in enumerate("lr"):
        ankle, heel, toe = I[side + "Ankle"], I[side + "Heel"], I[side + "Toe"]
        shift = np.column_stack([pos, np.zeros(len(pos))])
        A = joints[:, ankle] + shift
        r_h = np.linalg.norm(joints[:, heel] - joints[:, ankle], axis=1)
        r_t = np.linalg.norm(joints[:, toe] - joints[:, heel], axis=1)
        new_heel, new_toe = np.full((len(pos), 3), np.nan), np.full((len(pos), 3), np.nan)
        for i in range(len(pos)):
            if np.isnan(lens[i]) or np.isnan(A[i]).any():
                continue
            name = ("left", "right")[int(lens[i])]
            eye = np.asarray(cam["lenses"][name]["centre"], float)
            h2, t2 = foot2d[i, 2 + k], foot2d[i, k]
            if h2[2] >= CONF and not np.isnan(h2[:2]).any():
                d = rays(cam, name, [h2[:2]])[0]
                new_heel[i] = sphere_point(eye, d, A[i], r_h[i], joints[i, heel] + shift[i])
            if t2[2] >= CONF and not np.isnan(t2[:2]).any():
                base = new_heel[i] if not np.isnan(new_heel[i]).any() else joints[i, heel] + shift[i]
                d = rays(cam, name, [t2[:2]])[0]
                new_toe[i] = sphere_point(eye, d, base, r_t[i], joints[i, toe] + shift[i])
        # Fußvektoren (Knöchel -> Ferse, Ferse -> Zehe) glätten, dann einsetzen; nichts unter den Rasen
        vh, vt = new_heel - A, new_toe - np.where(np.isnan(new_heel), joints[:, heel] + shift, new_heel)
        vh_s, vt_s = smooth_vectors(vh, ~np.isnan(vh).any(axis=1)), smooth_vectors(vt, ~np.isnan(vt).any(axis=1))
        for i in range(len(pos)):
            if not np.isnan(vh_s[i]).any():
                out[i, heel] = A[i] + vh_s[i] - shift[i]
            if not np.isnan(vt_s[i]).any():
                out[i, toe] = out[i, heel] + vt_s[i]
            if not (np.isnan(vh_s[i]).any() and np.isnan(vt_s[i]).any()):
                changed += 1
        for j in (heel, toe):
            out[:, j, 2] = np.maximum(out[:, j, 2], GROUND)
    return out, changed
