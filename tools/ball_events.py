"""Ballkontakte, Pässe und Schüsse aus der Ballspur.

Ein Ball ändert sein Tempo nur bei einem Kontakt (Fuß, Kopf, Körper, Pfosten) oder beim Aufspringen; sonst rollt oder fliegt er
glatt. Daran werden Kontakte gesucht: Vor und nach jedem Bild wird je eine gerade Bahn an die gefundenen Lagen
angepasst (Rollen mit Reibung und Flug sehen über so kurze Stücke gerade genug aus); der Sprung der Geschwindigkeit zwischen beiden Bahnen
ist die Stärke des Kontakts. Spitzen darüber, mindestens MIN_DV m/s, mit Mindestabstand, sind Kontakte.

Aus Tempo vor und nach dem Kontakt folgt die Art: leichte Berührung (Dribbling), Pass, Schuss. Die Grenzen sind Anfangswerte für
Jugendfußball und werden an der Referenz gemessen (tools/ball_eval.py). Fuß und Spieler kommen aus tools/ball_events.assign.

Ein Kontakt ist nur so genau wie die Spur im Bild trägt: wo der Ball vor oder nach dem Kontakt nicht zu sehen war, fehlt die
Bahn auf einer Seite, und die Sicherheit sinkt entsprechend.
"""
from dataclasses import dataclass, field

import numpy as np

SIDE_S = 0.25          # s: so viel Spur vor und nach einem Bild geht in die Anpassung ein
MIN_SIDE = 4           # gefundene Lagen je Seite, damit eine Seite zählt
NOISE_FLOOR_M = 0.03   # m: weniger Rauschen der Lagen wird nicht angenommen
MIN_Z = 4.0            # Sprung muss so viele Unsicherheiten groß sein (sonst Rauschen)
MIN_DV = 1.5           # m/s: kleinerer Sprung der Geschwindigkeit ist kein Kontakt
MIN_GAP_S = SIDE_S     # s: kürzerer Abstand gilt als dasselbe Ereignis (ein Kontakt wirft Nebenspitzen im Abstand der Fensterbreite)
TOUCH_MS = 6.0         # m/s: bis hierhin leichte Berührung (Dribbling)
SHOT_MS = 16.0         # m/s: ab hier Schuss
NEAR_FOOT_M = 1.1      # m: so nah muss ein Fuß am Ball sein, damit ein Spieler zugeordnet wird


@dataclass
class Contact:
    frame: int
    time: float
    pos: tuple
    speed_in: float
    speed_out: float
    jump: float                # m/s Sprung der Geschwindigkeit
    kind: str                  # touch, pass, shot
    sides: int                 # 2 = Spur vor und nach dem Kontakt gesehen, 1 = nur eine Seite
    confidence: float
    player: object = None
    foot: object = None
    extra: dict = field(default_factory=dict)


def fit_side(t: np.ndarray, p: np.ndarray, at: float):
    """Gerade Bahn mit gleichbleibender Geschwindigkeit an Lagen p (n, 2) zu den Zeiten t; Lage und Geschwindigkeit bei `at`.
    Gerade statt Parabel: Die Lagen im Bild rauschen um Dezimeter, eine Parabel über so kurze Stücke würde das Rauschen zu
    Geschwindigkeitssprüngen aufblasen; die Verzögerung des Rollens (rund 1 m/s²) fällt über 0,25 s kaum ins Gewicht.
    Rückgabe: Lage, Geschwindigkeit, Unsicherheit der Geschwindigkeit (m/s, aus dem Rauschen der Lagen, mindestens NOISE_FLOOR_M
    angenommen). Weniger als drei Lagen: None."""
    if len(t) < 3:
        return None
    x = t - at
    A = np.column_stack([np.ones_like(x), x])
    coef, *_ = np.linalg.lstsq(A, p, rcond=None)
    resid = p - A @ coef
    sigma = max(NOISE_FLOOR_M, float(np.sqrt((resid ** 2).sum() / max(1, len(t) - 2) / 2)))
    return coef[0], coef[1], sigma / float(np.sqrt(((x - x.mean()) ** 2).sum()))


def jumps(pos: np.ndarray, fps: float) -> tuple:
    """Je Bild: Sprung der Geschwindigkeit (m/s) zwischen der Bahn davor und danach, Tempo davor, Tempo danach, Zahl der Seiten
    mit Spur, Sprung in Einheiten seiner Unsicherheit. Bilder ohne Spur beidseits: NaN."""
    n = len(pos)
    ok = ~np.isnan(pos[:, 0])
    side = max(2, round(SIDE_S * fps))
    jump, z = np.full(n, np.nan), np.full(n, np.nan)
    v_in, v_out = np.full(n, np.nan), np.full(n, np.nan)
    sides = np.zeros(n, int)
    t_all = np.arange(n) / fps
    for f in range(n):
        lo, hi = max(0, f - side), min(n, f + side + 1)
        before = [i for i in range(lo, f + 1) if ok[i]]
        after = [i for i in range(f, hi) if ok[i]]
        a = fit_side(t_all[before], pos[before], f / fps) if len(before) >= MIN_SIDE else None
        b = fit_side(t_all[after], pos[after], f / fps) if len(after) >= MIN_SIDE else None
        sides[f] = (a is not None) + (b is not None)
        if a is not None:
            v_in[f] = np.linalg.norm(a[1])
        if b is not None:
            v_out[f] = np.linalg.norm(b[1])
        if a is not None and b is not None:
            jump[f] = np.linalg.norm(b[1] - a[1])
            z[f] = jump[f] / np.hypot(a[2], b[2])
    return jump, v_in, v_out, sides, z


def classify(speed_out: float) -> str:
    return "shot" if speed_out >= SHOT_MS else "pass" if speed_out > TOUCH_MS else "touch"


def find_contacts(pos: np.ndarray, fps: float) -> list:
    """Kontakte aus der Ballspur pos (n, 2) in Metern (NaN = nicht gefunden); nach Zeit sortiert."""
    jump, v_in, v_out, sides, z = jumps(pos, fps)
    strength = np.where(np.nan_to_num(z, nan=0.0) >= MIN_Z, np.nan_to_num(jump, nan=0.0), 0.0)
    gap = max(1, round(MIN_GAP_S * fps))
    found = []
    for f in np.argsort(-strength):
        if strength[f] < MIN_DV:
            break
        if all(abs(f - c) >= gap for c in found):
            found.append(int(f))
    contacts = []
    for f in sorted(found):
        sure = min(1.0, strength[f] / (3 * MIN_DV), z[f] / (3 * MIN_Z))
        contacts.append(Contact(f, f / fps, tuple(pos[f]), float(v_in[f]), float(v_out[f]), float(strength[f]),
                                classify(float(v_out[f])), int(sides[f]), float(sure)))
    return contacts


def assign(contacts: list, feet: np.ndarray, keys: list) -> list:
    """Ordnet jedem Kontakt den nächsten Fuß zu. feet: (T, F, 2) Fußlagen aller Spieler (NaN = keiner), keys: Spieler je F.
    Ist kein Fuß näher als NEAR_FOOT_M, bleibt der Kontakt ohne Spieler (Ball weit weg von jedem: Kopf, Pfosten oder Spur falsch)."""
    for c in contacts:
        d = np.linalg.norm(feet[c.frame] - np.asarray(c.pos), axis=1)
        if np.isnan(d).all():
            continue
        k = int(np.nanargmin(d))
        if d[k] <= NEAR_FOOT_M:
            c.player = keys[k]
            c.extra["footDistance"] = round(float(d[k]), 2)
    return contacts
