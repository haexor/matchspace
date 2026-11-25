"""Saubere Fußkacheln: Schuhfarbe aus dem Video, ohne Rasen und Socke (Hilfsmodul für tools/jersey_decal.py).

Der Schuh ist im Video nur wenige Pixel groß. Die Fußkachel einer Videotextur (tools/veo_looks.py) ist deshalb ein Mosaik aus Schuh, Socke und
Rasen, und der Schuh verschwimmt mit dem Boden. Hier wird die Farbe des Schuhs bestimmt (die häufigste Farbe unter allen Texeln, die weder Rasen noch
Sockenfarbe sind) und die Kachel in dieser Farbe neu gemalt; Hell und Dunkel (Licht, Schnürung, Naht) bleiben aus dem Video erhalten, geglättet.
Ist kein Schuh auszumachen (zu wenige Texel), bleibt die Kachel, wie sie ist.
"""
import cv2
import numpy as np

GRASS_HUE = (30, 95)        # OpenCV-Farbton 0..180
GRASS_SAT = 45              # Sättigung 0..255, ab der Grün als Rasen gilt
SOCK_DIST = 45.0            # Abstand zur Sockenfarbe (BGR), unter dem ein Texel Socke ist
MIN_BOOT = 24               # so viele Schuh-Texel braucht eine 16 × 16-Kachel mindestens
SHADE = (0.6, 1.35)         # Grenzen des übernommenen Hell/Dunkel (Faktor auf die Schuhfarbe)


def boot_colour(tile, sock):
    """Schuhfarbe (BGR) und Zahl der Schuh-Texel in einer Fußkachel (h, w, 3); sock: Farbe der Socke (BGR). (None, 0), wenn keine auszumachen ist."""
    px = tile.reshape(-1, 3).astype(np.float32)
    hsv = cv2.cvtColor(tile.astype(np.uint8), cv2.COLOR_BGR2HSV).reshape(-1, 3)
    grass = (hsv[:, 0] >= GRASS_HUE[0]) & (hsv[:, 0] <= GRASS_HUE[1]) & (hsv[:, 1] >= GRASS_SAT)
    is_sock = np.linalg.norm(px - np.asarray(sock, np.float32), axis=1) < SOCK_DIST
    rest = px[~grass & ~is_sock]
    if len(rest) < MIN_BOOT:
        return None, int(len(rest))
    k = 2 if len(rest) >= 2 * MIN_BOOT else 1
    _, labels, centres = cv2.kmeans(rest, k, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5), 3, cv2.KMEANS_PP_CENTERS)
    main = int(np.bincount(labels.ravel(), minlength=k).argmax())
    return centres[main], int(len(rest))


def shared_colour(tile_l, tile_r, sock):
    """Gemeinsame Schuhfarbe beider Füße (beide Schuhe eines Spielers sind gleich, einer ist im Video oft besser zu sehen): die deutlichere Farbe, also die
    mit dem größeren Farbabstand zwischen den Kanälen; bei gleichem Abstand die mit mehr Schuh-Texeln. None, wenn an keinem Fuß ein Schuh auszumachen ist."""
    (cl, nl), (cr, nr) = boot_colour(tile_l, sock), boot_colour(tile_r, sock)
    if cl is None or cr is None:
        return cl if cr is None else cr
    chroma = lambda c: float(c.max() - c.min())  # noqa: E731
    if abs(chroma(cl) - chroma(cr)) < 10:
        return cl if nl >= nr else cr
    return cl if chroma(cl) > chroma(cr) else cr


def clean_foot(tile, sock, colour=None):
    """Neu gemalte Fußkachel (gleiche Form) oder dieselbe Kachel, wenn kein Schuh auszumachen war. colour: Schuhfarbe (BGR); sonst aus der Kachel."""
    if colour is None:
        colour, _ = boot_colour(tile, sock)
    if colour is None:
        return tile
    lum = tile.astype(np.float32) @ np.array([0.114, 0.587, 0.299], np.float32)
    shade = cv2.GaussianBlur(lum, (0, 0), 1.0) / max(float(colour @ np.array([0.114, 0.587, 0.299], np.float32)), 1.0)
    shade = np.clip(shade, *SHADE)
    return np.clip(colour[None, None, :] * shade[..., None], 0, 255).astype(np.uint8)
