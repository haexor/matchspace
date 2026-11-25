"""Mindestabstand zwischen Spielern: Körper dürfen sich berühren, aber nicht durchdringen (Hilfsmodul für tools/veo_scene.py).

Zwei Körper in Kontakt (Schulter an Schulter, Rücken an Brust, Zweikampf) haben Beckenmitten, die rund 0,3 bis 0,5 m auseinander liegen. Näher geht nicht:
Ein Oberkörper ist breiter, und die Beckenmitten würden ineinander stecken. Aus den Bildern gemessene Bahnen können im Zweikampf darunter fallen (die
Boxen beider Spieler überdecken sich, die Messung verwechselt sie). Hier werden zu nahe Paare symmetrisch auseinandergeschoben, nur so weit, wie der
Mindestabstand fehlt, und die Verschiebung wird über die Zeit geglättet, damit nichts springt. Wer weiter auseinander steht, wird nicht angefasst:
Es wird kein Abstand hergestellt, nur Durchdringung verhindert.
"""
import numpy as np

MIN_DISTANCE = 0.30      # m: kleinster Abstand zweier Beckenmitten
SMOOTH_FRAMES = 3.0      # Bilder (Gauß) für die Glättung der Verschiebung
ROUNDS = 6               # mehrere Spieler gleichzeitig: Schieben des einen kann ein neues Paar verletzen


def keep_apart(xy: np.ndarray, entities, min_distance=MIN_DISTANCE, rounds=ROUNDS, sigma=SMOOTH_FRAMES):
    """xy: Bahnen (Bilder, Figuren, 2), NaN = nicht da; entities: Indizes der Spieler. Verändert xy an Ort und Stelle.
    Rückgabe: (Zahl der Bilder mit Eingriff, größte Verschiebung in m)."""
    from scipy.ndimage import gaussian_filter1d
    idx = list(entities)
    shift = np.zeros((xy.shape[0], len(idx), 2))
    for _ in range(rounds):
        pos = xy[:, idx] + shift
        moved = False
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                d = pos[:, b] - pos[:, a]
                dist = np.linalg.norm(d, axis=1)
                close = np.flatnonzero(~np.isnan(dist) & (dist < min_distance))
                if not len(close):
                    continue
                # Richtung: wie die Spieler zueinander stehen; fallen sie zusammen, ist die Richtung unbestimmt: dann entlang der x-Achse
                direction = np.where(dist[close, None] > 1e-6, d[close] / np.maximum(dist[close, None], 1e-6), [[1.0, 0.0]])
                push = 0.5 * (min_distance - dist[close])[:, None] * direction
                shift[close, a] -= push
                shift[close, b] += push
                moved = True
        if not moved:
            break
    touched = np.linalg.norm(shift, axis=2) > 1e-9
    if not touched.any():
        return 0, 0.0
    # Verschiebung glätten, aber nie unter das hinaus, was zur Trennung nötig war
    smooth = gaussian_filter1d(shift, sigma, axis=0, mode="constant")
    result = np.where(np.abs(smooth) >= np.abs(shift), smooth, shift)
    for k, e in enumerate(idx):
        present = ~np.isnan(xy[:, e, 0])
        xy[present, e] += result[present, k]
    return int(touched.any(axis=1).sum()), float(np.linalg.norm(result, axis=2).max())
