"""Sieht ein Treffer aus wie ein Ball? Der Spielball ist weiß (mit Muster), die häufigsten Fehltreffer nicht: orangene
Markierungen, Hände, Schuhe, Linienstücke. Gemessen wird der Anteil heller, farbarmer Bildpunkte um den Treffer."""
import cv2
import numpy as np

RADIUS = 6          # Pixel: halbe Kantenlänge des geprüften Ausschnitts
BRIGHT, GREY = 110, 80   # Helligkeit mindestens, Farbsättigung höchstens
MIN_WHITE = 0.06    # darunter ist es kein Ball (an Bällen gemessen ab rund 0,16, an Fehltreffern bis 0,03)


def white_share(image: np.ndarray, u: float, v: float, r: int = RADIUS) -> float:
    """Anteil heller, farbarmer Bildpunkte im Quadrat um (u, v); image: BGR-Linsenbild oder Ausschnitt."""
    h, w = image.shape[:2]
    x0, x1, y0, y1 = max(0, int(u) - r), min(w, int(u) + r), max(0, int(v) - r), min(h, int(v) + r)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    hsv = cv2.cvtColor(np.ascontiguousarray(image[y0:y1, x0:x1]), cv2.COLOR_BGR2HSV)
    return float(((hsv[..., 2] > BRIGHT) & (hsv[..., 1] < GREY)).mean())
