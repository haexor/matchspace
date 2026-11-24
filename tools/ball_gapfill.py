"""Lokale Nachsuche des Balls in den Lücken der Ballspur.

Die Suche über das ganze Linsenbild (tools/veo_ball.py) übersieht den Ball häufig: am Fuß halb verdeckt, vor Spielern,
im Flug unscharf. In einem kleinen Ausschnitt um die erwartete Stelle findet derselbe Detektor ihn dagegen oft doch
(Probe an 80 Lückenbildern: die Hälfte, alle sichtbar der echte Ball). Hier wird deshalb von jedem gefundenen Bild aus
Bild für Bild weitergesucht: erwartete Stelle aus Nachbarn (Mitte zwischen zwei Funden oder letzte Geschwindigkeit),
Ausschnitt dort, nächster Treffer innerhalb eines Suchradius zählt. Runde für Runde wachsen die Funde in die Lücken.

Nur eigene Messungen, keine Veo-Daten. Was so gefunden wurde, trägt in `source` die Kennung 3 (siehe veo_ball.py).
"""
import numpy as np

CROP = 130              # Pixel: halbe Kantenlänge des Ausschnitts
CONF = 0.05             # niedrigere Schwelle als die Suche über das ganze Bild: der Ort ist hier schon bekannt
BASE_RADIUS = 30.0      # Pixel Suchradius direkt am Fund
GROW_RADIUS = 10.0      # Pixel mehr je Bild Abstand vom nächsten Fund
MAX_RADIUS = 120.0
SPAN = 60               # Bilder: so weit darf die Mitte zwischen zwei Funden reichen
REACH = 8               # Bilder je Runde in die Lücke hinein
ROUNDS = 8
VEL_FRAMES = 3          # Geschwindigkeit aus Funden höchstens so weit davor


def anchors(known: np.ndarray, f: int) -> tuple:
    """Nächster Fund vor und nach Bild f (oder None)."""
    before = np.flatnonzero(known[:f])
    after = np.flatnonzero(known[f + 1:])
    return (int(before[-1]) if len(before) else None, int(after[0]) + f + 1 if len(after) else None)


def expected(pix: np.ndarray, known: np.ndarray, f: int):
    """Erwartete Stelle (Linse, u, v) und Suchradius für das Lückenbild f; None, wenn nichts Brauchbares in der Nähe ist."""
    a, b = anchors(known, f)
    near = [x for x in (a, b) if x is not None and abs(x - f) <= REACH]
    if not near:
        return None
    dist = min(abs(x - f) for x in near)
    radius = min(MAX_RADIUS, BASE_RADIUS + GROW_RADIUS * dist)
    if a is not None and b is not None and b - a <= SPAN and pix[a, 0] == pix[b, 0]:
        t = (f - a) / (b - a)
        return int(pix[a, 0]), *(pix[a, 1:] * (1 - t) + pix[b, 1:] * t), radius
    x = a if (a is not None and (b is None or f - a <= b - f)) else b
    lens, p = int(pix[x, 0]), pix[x, 1:].copy()
    step = 1 if x == a else -1   # Geschwindigkeit aus dem Fund davor (oder danach), vom Rand der Lücke weg
    y = x - step
    if 0 <= y < len(known) and known[y] and abs(y - x) <= VEL_FRAMES and pix[y, 0] == lens:
        p = p + (pix[x, 1:] - pix[y, 1:]) * (f - x) / (x - y)
    return lens, float(p[0]), float(p[1]), radius


def crop_box(u: float, v: float, width: int, height: int) -> tuple:
    """Ausschnitt (x0, y0) mit 2*CROP Kantenlänge, in das Linsenbild geschoben."""
    return int(np.clip(u - CROP, 0, max(0, width - 2 * CROP))), int(np.clip(v - CROP, 0, max(0, height - 2 * CROP)))


def pick(hits: list, u: float, v: float, radius: float):
    """Treffer (u, v, Sicherheit) nächster zur erwarteten Stelle innerhalb des Radius."""
    best = None
    for hu, hv, conf in hits:
        d = float(np.hypot(hu - u, hv - v))
        if d <= radius and (best is None or d < best[0]):
            best = (d, hu, hv, conf)
    return None if best is None else best[1:]


def search_round(pix, known, width, height):
    """Je Lückenbild nah an einem Fund: (Bild, Linse, u, v, Radius, x0, y0)."""
    todo = []
    for f in np.flatnonzero(~known):
        e = expected(pix, known, int(f))
        if e is None:
            continue
        lens, u, v, radius = e
        x0, y0 = crop_box(u, v, width, height)
        todo.append((int(f), lens, u, v, radius, x0, y0))
    return todo


def fill(cut_crops, detect_crops, pix: np.ndarray, width: int = 2048, height: int = 1024, rounds: int = ROUNDS) -> np.ndarray:
    """Füllt Lücken von pix (n, 3 = Linse, u, v; NaN = kein Fund) durch lokale Suche.
    cut_crops(todo) -> Ausschnitte (2*CROP Kantenlänge) zu den Einträgen (Bild, Linse, ..., x0, y0) von todo;
    detect_crops(ausschnitte) -> je Ausschnitt Treffer [(u, v, Sicherheit)] in dessen Koordinaten.
    Rückgabe: Maske der neu gefundenen Bilder; pix wird an Ort und Stelle ergänzt."""
    known = ~np.isnan(pix[:, 0])
    added = np.zeros(len(pix), bool)
    for _ in range(rounds):
        todo = search_round(pix, known, width, height)
        if not todo:
            break
        found = 0
        for (f, lens, u, v, radius, x0, y0), hits in zip(todo, detect_crops(cut_crops(todo))):
            got = pick([(hu + x0, hv + y0, c) for hu, hv, c in hits], u, v, radius)
            if got is not None:
                pix[f] = (lens, got[0], got[1])
                known[f] = added[f] = True
                found += 1
        if not found:
            break
    return added
