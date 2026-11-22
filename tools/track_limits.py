#!/usr/bin/env python3
"""Hält Laufwege im Bereich dessen, was ein Mensch kann.

Zwei Schritte je Spieler:

1. Sprünge trennen. Wo eine Bahn schneller als 12 m/s wäre, hat die Quelle zwei Spieler vertauscht
   oder sich vermessen. Dort wird die Bahn unterbrochen: Die Figur verschwindet kurz und erscheint
   am neuen Ort, statt über den Platz zu fliegen. Reste unter einer halben Sekunde entfallen.
2. Tempo und Beschleunigung begrenzen. Jedes Stück wird so wenig wie möglich geglättet, aber so
   weit, dass es nie schneller als 8,7 m/s (31 km/h) und nie mit mehr als 8 m/s² unterwegs ist
   (Beschleunigung über 0,4 s gemittelt). Wo die Messung das einhält, bleibt sie fast unverändert.

Aufruf (schreibt tracks.bin des Spiels neu; danach tools/synth_poses.py):
    .venv/bin/python tools/track_limits.py SPIELORDNER

veo_scene.py nutzt physical() für die selbst gemessenen Positionen.
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.linalg import solveh_banded

V_MAX = 8.7        # m/s
A_MAX = 8.0        # m/s², über 2 * A_SPAN gemittelt
A_SPAN = 0.2       # s
TELEPORT = 12.0    # m/s: darüber ist es kein Lauf mehr
MIN_PIECE = 0.5    # s
BASE = 2.0         # Grundglättung (Gewicht der zweiten Differenzen)


def pieces(mask, minimum=1):
    edges = np.flatnonzero(np.diff(np.concatenate([[0], mask.astype(int), [0]])))
    return [(a, b) for a, b in zip(edges[::2], edges[1::2]) if b - a >= minimum]


def acceleration(pos, fps):
    """Beschleunigung (m/s²) je Bild, über ±A_SPAN gemittelt; so rechnet auch tools/check_motion.py."""
    w = max(int(round(A_SPAN * fps)), 1)
    acc = np.zeros(len(pos))
    if len(pos) > 2 * w + 1:
        vel = np.gradient(pos, axis=0) * fps
        acc[w:-w] = np.linalg.norm(vel[2 * w:] - vel[:-2 * w], axis=1) / (2 * w / fps)
    return acc


def _solve(z, lam, mu):
    """Minimiert Σ|x - z|² + Σ lam·|zweite Differenz|² + Σ mu·|erste Differenz|²."""
    n = len(z)
    ab = np.zeros((3, n))
    ab[0] = 1.0
    ab[0, :-2] += lam
    ab[0, 1:-1] += 4 * lam
    ab[0, 2:] += lam
    ab[1, :-2] -= 2 * lam
    ab[1, 1:-1] -= 2 * lam
    ab[2, :-2] += lam
    ab[0, :-1] += mu
    ab[0, 1:] += mu
    ab[1, :-1] -= mu
    return solveh_banded(ab, z, lower=True)


def physical(pos, fps, v_max=V_MAX, a_max=A_MAX):
    """Glättet ein lückenloses Bahnstück (n, 2) gerade so weit, dass Tempo und Beschleunigung möglich sind."""
    n = len(pos)
    if n < 6:
        return pos.copy()
    lam, mu = np.full(n - 2, BASE), np.zeros(n - 1)
    spread = max(int(round(A_SPAN * fps)), 1)
    x = pos
    for _ in range(80):
        x = _solve(pos, lam, mu)
        fast = np.linalg.norm(np.diff(x, axis=0), axis=1) * fps > v_max
        hard = acceleration(x, fps) > a_max
        if not fast.any() and not hard.any():
            break
        if hard.any():
            wide = np.convolve(hard, np.ones(2 * spread + 1), "same") > 0
            lam[wide[1:-1]] *= 3.0
        if fast.any():
            wide = np.convolve(fast, np.ones(5), "same") > 0
            mu[wide] = np.maximum(mu[wide] * 2.5, 2.0)
    return x


def split_teleports(pos, fps):
    """Unterbricht eine Bahn (n, 2; NaN = nicht da) an Stellen, an denen sie über TELEPORT schnell wäre."""
    out = pos.copy()
    step = np.linalg.norm(np.diff(pos, axis=0), axis=1) * fps
    jump = np.zeros(len(pos), bool)
    with np.errstate(invalid="ignore"):
        bad = np.flatnonzero(step > TELEPORT)
    jump[bad] = jump[bad + 1] = True
    jump = np.convolve(jump, np.ones(5), "same") > 0          # samt der Übergangsbilder daneben
    out[jump] = np.nan
    for a, b in pieces(~np.isnan(out[:, 0])):
        if b - a < MIN_PIECE * fps:
            out[a:b] = np.nan
    return out


def clean(pos, fps):
    """Beide Schritte für eine ganze Bahn mit Lücken."""
    out = split_teleports(pos, fps)
    for a, b in pieces(~np.isnan(out[:, 0])):
        out[a:b] = physical(out[a:b], fps)
    return out


def main(folder):
    folder = Path(folder)
    meta = json.loads((folder / "meta.json").read_text())
    fps, frames, entities = meta["fps"], meta["frames"], meta["entities"]
    tracks = np.fromfile(folder / meta["tracks"]["file"], "<i2").reshape(frames, len(entities), 3)
    missing, scale = meta["tracks"]["missing"], meta["tracks"]["scale"]
    cut = moved = 0
    worst = 0.0
    for i, e in enumerate(entities):
        if e["kind"] != "player":
            continue
        here = tracks[:, i, 0] != missing
        if not here.any():
            continue
        pos = np.where(here[:, None], tracks[:, i, :2] * scale, np.nan)
        with np.errstate(invalid="ignore"):
            worst = max(worst, float(np.nanmax(np.linalg.norm(np.diff(pos, axis=0), axis=1), initial=0.0)) * fps)
        new = clean(pos, fps)
        gone = here & np.isnan(new[:, 0])
        cut += int(gone.sum())
        moved += int((np.linalg.norm(np.nan_to_num(new - pos), axis=1) > 0.3).sum())
        tracks[:, i, :2] = np.where(np.isnan(new), missing, np.round(new / scale))
        tracks[gone, i, 2] = missing
    tracks.tofile(folder / meta["tracks"]["file"])
    print(f"{folder}: höchstes Tempo vorher {worst:.0f} m/s; {cut} Spieler-Bilder an Sprüngen entfernt, {moved} um mehr als 0,3 m verschoben")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
