"""Überdeckung zweier Spieler im Bild: Gelenkpunkte dort sind unsicher (Hilfsmodul).

Stehen zwei Spieler im Bild übereinander (Zweikampf, Foul), mischt der Gelenkpunkt-Schätzer Punkte beider Körper; die Skelette verheddern sich. Wo die Box
eines Spielers stark von der Box eines anderen überdeckt wird, zählen seine Gelenkpunkte deshalb weniger: Die natürliche Bewegung als Vorlage trägt dann
mehr, statt dass ein falsch zugeordneter Punkt ein Bein quer durch den anderen Spieler zieht.
"""
import numpy as np

START = 0.25      # Überdeckung (Anteil der kleineren Box), ab der das Gewicht sinkt
SLOPE = 1.6       # Gewichtsverlust je Anteil über START
FLOOR = 0.15      # kleinster Faktor: ganz ohne Gelenkpunkte bliebe nur die Vorlage


def covered_share(a: np.ndarray, b: np.ndarray) -> float:
    """Anteil der Schnittfläche an der kleineren Box; a, b: x1, y1, x2, y2."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return float(w * h / small) if small > 0 else 0.0


def weight_factor(obs: dict, key) -> np.ndarray:
    """Faktor (n,) je Bild für die Gelenkpunkte von key: 1 ohne Überdeckung, bis FLOOR bei voller. obs: Spieler -> (n, 9) mit Linse in Spalte 0,
    Box in 1 bis 4 (NaN ohne Erkennung)."""
    mine = obs[key]
    factor = np.ones(len(mine))
    for fi in np.flatnonzero(~np.isnan(mine[:, 0])):
        worst = 0.0
        for other, rows in obs.items():
            if other == key or np.isnan(rows[fi, 0]) or rows[fi, 0] != mine[fi, 0]:
                continue
            worst = max(worst, covered_share(mine[fi, 1:5], rows[fi, 1:5]))
        factor[fi] = float(np.clip(1.0 - SLOPE * max(worst - START, 0.0), FLOOR, 1.0))
    return factor
