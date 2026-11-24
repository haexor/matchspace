"""Ballphysik: Flug mit Höhe, Rollen am Boden, Aufspringen.

Das Panorama zeigt den Ball nur als Richtung (Sehstrahl durch das Ballpixel). Am Boden kennt man die Höhe (Balldurchmesser) und
damit den Punkt auf dem Strahl. Im Flug nicht: Dieselbe Richtung passt zu vielen Höhen. Dann hilft die Physik: Zwischen zwei
Kontakten fliegt der Ball auf einer Wurfparabel (Schwerkraft bekannt, Luftwiderstand klein). Lage und Geschwindigkeit zur Startzeit
sind sechs Unbekannte; jeder Strahl gibt zwei Gleichungen (der Punkt muss auf dem Strahl liegen), also ist die Bahn bei rund zehn
Bildern bestimmt, solange der Strahl sich während des Flugs genug dreht. Fliegt der Ball genau auf die Kamera zu oder von ihr weg,
bleibt die Höhe unbestimmt; das wird als Unsicherheit ausgewiesen, nicht verschwiegen.

Rollen: gleichmäßig verzögert am Boden (Höhe = Ballradius), dieselbe Rechnung mit festgehaltener Höhe.
Welches Modell besser passt, entscheidet der Restfehler zu den Strahlen und die Plausibilität (Bahn nie unter dem Boden).
Aufspringen: Erklärt ein Modell den Verlauf schlecht und zwei Modelle deutlich besser, wird am besten Schnitt geteilt.

Eingabe sind Strahlen, keine Pixel: dadurch ist die Rechnung ohne Kameramodell testbar (tools/ball_motion.py bindet sie an die Kamera).
"""
from dataclasses import dataclass

import numpy as np

G = 9.81               # m/s²
RADIUS = 0.11          # m: Ballradius (Mittelpunkt am Boden liegt so hoch)
MIN_OBS = 8            # Beobachtungen, ab denen ein Stück angepasst wird
FLIGHT_GAIN = 0.7      # Flug zählt nur, wenn sein Restfehler unter diesem Anteil des Rollens liegt
MIN_APEX = 0.35        # m: niedrigere Flugbögen gelten als Rollen
MAX_Z_SIGMA = 0.6      # m: unsichere Höhe als „unbestimmt“ ausweisen
MIN_RANGE = 3.0        # m: näher als das vor der Kamera ist keine Ballbahn (Kameralage ist die triviale Lösung aller Strahlen)
MAX_HEIGHT = 15.0      # m
AREA = (65.0, 45.0)    # m: größte Beträge von x und y (Platz mit Rand)
MAX_SPEED = 35.0       # m/s: schneller rollt kein Ball; ein „Rollen“ darüber ist ein falsch angenommener Flug oder eine falsche Spur
BOUNCE_TOL = 0.12      # m: so weit darf eine Flugbahn unter den Boden fallen, bevor sie als unmöglich gilt
SPLIT_MIN_RMS = 0.05   # m: erst bei größerem Restfehler eines Modells wird eine Teilung versucht
SPLIT_GAIN = 0.5       # Teilung gilt nur, wenn der Restfehler unter diesem Anteil bleibt
NOISE_FLOOR_RAD = 1e-4 # rad: Mindestrauschen der Strahlrichtung


@dataclass
class Fit:
    kind: str          # flight, ground
    p0: np.ndarray     # Lage zur Zeit t0 (3)
    v: np.ndarray      # Geschwindigkeit (3)
    a: np.ndarray      # Beschleunigung (3): Schwerkraft im Flug, Reibung am Boden
    t0: float
    rms: float         # m: mittlerer senkrechter Abstand der Bahn von den Strahlen
    z_sigma: float     # m: Unsicherheit der Höhe (größter Wert über die Zeiten)

    def at(self, t):
        x = np.asarray(t, float)[..., None] - self.t0
        return self.p0 + self.v * x + 0.5 * self.a * x * x


def _equations(origins, dirs, t, ranges, mode, t0):
    """Lineares System A θ = b. flight: θ = (p0, v) mit fester Schwerkraft; ground: θ = (p0xy, vxy, axy) mit Höhe RADIUS."""
    n = len(t)
    x = t - t0
    I = np.eye(3)
    rows_A, rows_b = [], []
    for i in range(n):
        d = dirs[i] / np.linalg.norm(dirs[i])
        M = (I - np.outer(d, d)) / max(ranges[i], 1e-3)       # Abstand vom Strahl, als Winkel mal 1 m gewichtet
        e3 = np.array([0.0, 0.0, 1.0])
        if mode == "flight":
            A = np.hstack([M, M * x[i]])
            b = M @ (origins[i] + 0.5 * G * x[i] ** 2 * e3)
        else:
            Mxy = M[:, :2]
            A = np.hstack([Mxy, Mxy * x[i], Mxy * 0.5 * x[i] ** 2])
            b = M @ (origins[i] - RADIUS * e3)
        rows_A.append(A)
        rows_b.append(b)
    return np.vstack(rows_A), np.concatenate(rows_b)


def fit(origins, dirs, t, ranges, mode: str) -> Fit | None:
    """Bahn an Strahlen anpassen. origins, dirs (n, 3), t (n,) in Sekunden, ranges (n,) ungefähre Entfernung (für die Gewichtung)."""
    origins, dirs, t = np.asarray(origins, float), np.asarray(dirs, float), np.asarray(t, float)
    if len(t) < MIN_OBS:
        return None
    t0 = float(t.mean())
    A, b = _equations(origins, dirs, t, np.asarray(ranges, float), mode, t0)
    theta, *_ = np.linalg.lstsq(A, b, rcond=None)
    resid = A @ theta - b
    dof = max(1, len(b) - len(theta))
    s2 = float(resid @ resid) / dof
    s2 = max(s2, (NOISE_FLOOR_RAD) ** 2)
    rms = float(np.sqrt(resid @ resid / len(t))) * float(np.mean(ranges))   # Winkel wieder in Metern (grob, mit mittlerer Entfernung)
    if mode == "flight":
        p0, v, a = theta[:3], theta[3:6], np.array([0.0, 0.0, -G])
        cov = s2 * np.linalg.pinv(A.T @ A)
        zs = np.sqrt(np.maximum([cov[2, 2] + (ti - t0) ** 2 * cov[5, 5] + 2 * (ti - t0) * cov[2, 5] for ti in t], 0.0))
        z_sigma = float(zs.max())
    else:
        p0, v, a = np.append(theta[:2], RADIUS), np.append(theta[2:4], 0.0), np.append(theta[4:6], 0.0)
        z_sigma = 0.0
    return Fit(mode, p0, v, a, t0, rms, z_sigma)


@dataclass
class Segment:
    start: int
    stop: int          # ausschließlich
    kind: str          # flight, ground, unknown
    fit: Fit | None
    rms: float
    z_sigma: float


def inside(f: Fit, origins, dirs, t) -> bool:
    """Bahn liegt vor der Kamera (nicht auf oder hinter ihr), unter MAX_HEIGHT und im Gelände."""
    pts = f.at(t)
    ahead = ((pts - origins) * dirs).sum(axis=1)
    return bool((ahead >= MIN_RANGE).all() and (pts[:, 2] <= MAX_HEIGHT).all() and (np.abs(pts[:, 0]) <= AREA[0]).all()
                and (np.abs(pts[:, 1]) <= AREA[1]).all())


def choose(origins, dirs, t, ranges) -> tuple:
    """Besseres Modell für ein Stück. Rückgabe: (kind, Fit). kind unknown, wenn zu wenig Beobachtungen."""
    ground = fit(origins, dirs, t, ranges, "ground")
    if ground is None:
        return "unknown", None
    flight = fit(origins, dirs, t, ranges, "flight")
    if flight is None:
        return "ground", ground
    z = flight.at(t)[:, 2]
    plausible = (z.max() - RADIUS >= MIN_APEX and z.min() >= RADIUS - BOUNCE_TOL and flight.z_sigma <= MAX_Z_SIGMA
                 and inside(flight, origins, dirs, t))
    if plausible and flight.rms < FLIGHT_GAIN * ground.rms:
        return "flight", flight
    if (np.linalg.norm(ground.v + ground.a * (t - ground.t0)[:, None], axis=1).max() > MAX_SPEED
            or not inside(ground, origins, dirs, t)):
        return "unknown", ground    # kein Rollen und kein plausibler Flug: nichts behaupten
    return "ground", ground


def _rms(kind_fit) -> float:
    return kind_fit[1].rms if kind_fit[1] is not None else float("inf")


def best_split(origins, dirs, t, ranges):
    """Teilung eines Stücks in zwei, wenn zwei Modelle den Verlauf deutlich besser erklären als eines (Aufspringen, ein Kontakt,
    den die Spur nicht gezeigt hat). Rückgabe: (Index, Restfehler beider Teile) oder None."""
    whole = choose(origins, dirs, t, ranges)
    base = _rms(whole)
    if not np.isfinite(base) or base < SPLIT_MIN_RMS:
        return None
    best = None
    for cut in range(MIN_OBS, len(t) - MIN_OBS + 1):
        a = choose(origins[:cut], dirs[:cut], t[:cut], ranges[:cut])
        b = choose(origins[cut:], dirs[cut:], t[cut:], ranges[cut:])
        if a[0] == "unknown" or b[0] == "unknown":
            continue
        both = float(np.sqrt((_rms(a) ** 2 * cut + _rms(b) ** 2 * (len(t) - cut)) / len(t)))
        if best is None or both < best[1]:
            best = (cut, both)
    if best is not None and best[1] < SPLIT_GAIN * base:
        return best
    return None


def segment_track(origins, dirs, t, ranges, frames, depth: int = 2) -> list:
    """Teilt eine Folge von Beobachtungen (zwischen zwei Kontakten) in Stücke mit einem Modell je Stück (Aufspringen teilt)."""
    origins, dirs, t, ranges = (np.asarray(x, float) for x in (origins, dirs, t, ranges))
    cut = best_split(origins, dirs, t, ranges) if depth > 0 else None
    if cut is not None:
        c = cut[0]
        return (segment_track(origins[:c], dirs[:c], t[:c], ranges[:c], frames[:c], depth - 1) +
                segment_track(origins[c:], dirs[c:], t[c:], ranges[c:], frames[c:], depth - 1))
    kind, f = choose(origins, dirs, t, ranges)
    return [Segment(int(frames[0]), int(frames[-1]) + 1, kind, f, f.rms if f else float("nan"), f.z_sigma if f else float("nan"))]
