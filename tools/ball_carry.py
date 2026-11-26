"""Ball in der Hand: Einwurf, Torwart fängt, Spieler trägt den Ball.

Die Ballbahn (tools/ball_motion.py) kennt nur Rollen und Flug. Ein Ball in den Händen über dem Kopf (Einwurf) liegt auf einem Sehstrahl, dessen Schnitt mit dem
Boden weit hinter dem Spieler liegt; die Spur zeigt dann einen Ball, der am Boden entlang rollt oder fehlt. Hier wird das Gegenteil geprüft: Geht der Sehstrahl durch
die Hände eines Spielers (Abstand höchstens HELD_TOL), ist der Ball in dessen Händen. Das gilt nur, wenn die Hände höher als MIN_HAND_Z sind: Ein Ball am Fuß liegt
auf einem Strahl, der an den Händen vorbeigeht.

Die Lage ist die Mitte zwischen beiden Handgelenken (der Ball liegt zwischen den Händen), nicht der Schnitt mit dem Strahl: Die Haltung der Hände ist genauer als die Tiefe
des Strahls. Lücken im Strahl (Ball nicht erkannt) innerhalb eines Laufs folgen den Händen weiter.
"""
import numpy as np

HELD_TOL = 0.45        # m: so nah geht der Sehstrahl an den Händen vorbei (Handgelenk des Modells liegt bis ~0,3 m daneben)
MIN_HAND_Z = 0.9       # m: Hände mindestens so hoch (sonst ist es ein Ball am Fuß)
MIN_FRAMES = 6         # Bilder (0,24 s) mindestens, sonst Zufall
MAX_GAP = 8            # Bilder ohne Strahl oder Treffer, die einen Lauf nicht beenden
EXTEND = 25            # Bilder (0,5 s): so weit wird ein Lauf in unbekannte Ballbilder davor und danach verlängert (Aufnehmen, Abwurf)
WRONG_M = 2.0          # m: so weit ist die Ballspur von den Händen weg: dann gilt sie in verlängerten Bildern als falsch (z. B. ein Ball daneben am Boden)
BALL_IN_HANDS_DZ = 0.05  # m: der Ball liegt etwas über der Mitte der Handgelenke


def ray_distance(origin: np.ndarray, direction: np.ndarray, point: np.ndarray) -> float:
    """Abstand eines Punkts vom Sehstrahl (nur nach vorn); inf, wenn der Punkt hinter dem Ursprung liegt."""
    v = np.asarray(point, float) - origin
    t = float(v @ direction)
    if t <= 0:
        return float("inf")
    return float(np.linalg.norm(v - t * direction))


def hand_distances(origin, direction, hands: np.ndarray) -> np.ndarray:
    """Für ein Bild: je Spieler der kleinste Abstand des Sehstrahls zu einer Hand über MIN_HAND_Z (inf, wenn keine da ist). hands: (P, 2, 3), NaN = nicht da."""
    out = np.full(len(hands), np.inf)
    for p in range(len(hands)):
        for w in range(2):
            h = hands[p, w]
            if not np.isnan(h).any() and h[2] >= MIN_HAND_Z:
                out[p] = min(out[p], ray_distance(origin, direction, h))
    return out


def held_by(origin, direction, hands: np.ndarray) -> tuple:
    """Für ein Bild: (Index des Spielers, Abstand), dessen Hand dem Strahl am nächsten ist, oder (-1, Abstand), wenn keine näher als HELD_TOL liegt."""
    d = hand_distances(origin, direction, hands)
    k = int(np.argmin(d)) if len(d) else -1
    return (k, float(d[k])) if k >= 0 and d[k] <= HELD_TOL else (-1, float(d[k]) if k >= 0 else float("inf"))


def runs(owner: np.ndarray, min_frames: int = MIN_FRAMES, max_gap: int = MAX_GAP) -> list:
    """Läufe gleichen Besitzers (Index >= 0; -1 = keiner, -2 = kein Strahl): (von, bis ausschließlich, Spieler). Lücken bis max_gap Bilder derselben Person
    werden überbrückt, Läufe unter min_frames Treffern verworfen."""
    out, n = [], len(owner)
    f = 0
    while f < n:
        if owner[f] < 0:
            f += 1
            continue
        p, start, last, hits, g = owner[f], f, f, 0, f
        while g < n and g - last <= max_gap:
            if owner[g] == p:
                last, hits = g, hits + 1
            elif owner[g] >= 0:       # ein anderer Spieler hat den Ball
                break
            g += 1
        if hits >= min_frames:
            out.append((start, last + 1, int(p)))
        f = last + 1
    return out


def extend(runs_: list, unknown: np.ndarray, reach: int = EXTEND) -> list:
    """Läufe in unbekannte Ballbilder davor und danach verlängern (der Ball ist dort weder gesehen noch bekannt, aber noch in der Hand)."""
    out = []
    for a, b, p in runs_:
        lo = a
        while lo > 0 and unknown[lo - 1] and a - lo < reach:
            lo -= 1
        hi = b
        while hi < len(unknown) and unknown[hi] and hi - b < reach:
            hi += 1
        out.append((lo, hi, p))
    return out


def ray_point(origin: np.ndarray, direction: np.ndarray, point: np.ndarray) -> np.ndarray:
    """Punkt auf dem Sehstrahl, der `point` am nächsten liegt."""
    return origin + float((np.asarray(point, float) - origin) @ direction) * direction


def ball_in_hands(hands: np.ndarray) -> np.ndarray:
    """Lage des Balls je Bild: Mitte der Handgelenke, etwas darüber. hands: (T, 2, 3); NaN, wo eine Hand fehlt."""
    mid = hands.mean(axis=1)
    mid[:, 2] += BALL_IN_HANDS_DZ
    return mid


def carry(origins, directions, observed: np.ndarray, hands: np.ndarray, unknown: np.ndarray, track_xy: np.ndarray | None = None) -> tuple:
    """Alle Läufe, in denen ein Spieler den Ball hält. origins/directions (T, 3) Sehstrahl je Ausgabebild (NaN ohne Fund), observed (T,) Ball erkannt,
    hands (P, T, 2, 3) Handgelenke, unknown (T,) Ball in der Bahn nicht bekannt, track_xy (T, 2) Lage der Ballspur (dort, wo sie über WRONG_M von den Händen
    abweicht, wird ebenfalls verlängert: Die Spur zeigt dann einen anderen Ball am Boden).
    Je Spieler wird für sich nach Läufen gesucht (ein anderer Spieler, dessen Hand zufällig auch nah am Strahl liegt, beendet ihn nicht); überlappen
    sich Läufe zweier Spieler, bleibt der mit mehr Treffern. Rückgabe: (Läufe [(von, bis, Spieler)], xyz (T, 3) mit der Lage in den Läufen, sonst NaN)."""
    T, P = len(observed), len(hands)
    near = np.full((P, T), np.inf)
    for f in range(T):
        if observed[f] and not np.isnan(origins[f]).any():
            near[:, f] = hand_distances(origins[f], directions[f], hands[:, f])
    cand = []
    for p in range(P):
        owner = np.where(near[p] <= HELD_TOL, p, -2)
        cand += [(a, b, p, int((owner[a:b] == p).sum())) for a, b, _ in runs(owner)]
    taken, chosen = np.zeros(T, bool), []
    for a, b, p, hits in sorted(cand, key=lambda c: -c[3]):
        if not taken[a:b].any():
            taken[a:b] = True
            chosen.append((a, b, p))
    found = []
    for a, b, p in sorted(chosen):
        mine = ball_in_hands(hands[p])
        far = ~unknown & (np.linalg.norm(track_xy - mine[:, :2], axis=1) > WRONG_M) if track_xy is not None else np.zeros(T, bool)
        found += [(lo, hi, p) for lo, hi, _ in extend([(a, b, p)], unknown | np.nan_to_num(far, nan=False))]
    merged = []
    for a, b, p in sorted(found):          # überlappende Läufe desselben Spielers zusammenfassen
        if merged and merged[-1][2] == p and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]), p)
        else:
            merged.append((a, b, p))
    found = merged
    xyz = np.full((T, 3), np.nan)
    for a, b, p in found:
        mid = ball_in_hands(hands[p])
        shift = np.full((T, 3), np.nan)           # wo der Ball im Bild liegt, ist der Strahl genauer als die Hand (Handgelenk des Modells liegt oft daneben)
        for f in range(a, b):
            if near[p, f] <= HELD_TOL and not np.isnan(mid[f]).any():
                shift[f] = ray_point(origins[f], directions[f], mid[f]) - mid[f]
        seen = np.flatnonzero(~np.isnan(shift[a:b, 0])) + a
        for k in range(3):
            off = np.interp(np.arange(a, b), seen, shift[seen, k]) if len(seen) else np.zeros(b - a)
            xyz[a:b, k] = mid[a:b, k] + off
    return found, xyz
