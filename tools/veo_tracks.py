#!/usr/bin/env python3
"""Liest Veos Positionsdaten als Spuren in Metern (Hilfsmodul, kein eigenes Werkzeug).

Veo liefert Positionen als Anteil eines Vierecks (0..1 in Länge und Breite), das aus vier
angeklickten Ecken stammt. Diese Ecken liegen bis zu mehreren Metern neben den echten, und
Veo nimmt 105 m Länge an. Deshalb werden die Anteile hier mit einer eigenen Abbildung in
Meter umgerechnet, die tools/veo_align.py an unseren Erkennungen bestimmt.
"""
import json
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

COLOR_CLASS = {"red": 0, "green": 1}
REFEREE_CLASS = 2


def load_export(veo_dir):
    return json.loads((Path(veo_dir) / "export.json").read_text())


def to_metres(H, xy):
    """Veo-Anteile (n, 2) -> Meter auf dem echten Platz (Ursprung Anstoßpunkt, y von der Kamera weg)."""
    xy = np.asarray(xy, float).reshape(-1, 2)
    p = np.column_stack([xy, np.ones(len(xy))]) @ np.asarray(H, float).T
    return p[:, :2] / p[:, 2:3]


def build_tracks(export, H):
    """Veo-Spuren: {Spurnummer: {pts (t, x, y in Metern), cls, team, jersey}}.

    cls ist die Farbklasse des Trikots je Halbzeit; Torhüter tragen andere Farben (-1)."""
    periods = sorted(export["periods"], key=lambda p: p["timeframe"][0])
    match = export.get("match", {})
    own, opp = COLOR_CLASS.get(match.get("ownColor"), -1), COLOR_CLASS.get(match.get("opponentColor"), -1)
    tracks = {}
    for key, objs in export["tracking"].items():
        t = float(key)
        period = next((p for p in periods if p["timeframe"][0] <= t <= p["timeframe"][1]), None)
        if period is None:
            continue
        for o in objs:
            if o[1] not in (0, 1, 2, 3, 4):
                continue
            if o[1] == 4:
                cls, team = REFEREE_CLASS, "referee"
            else:
                is_own = (o[1] in (0, 1)) == (period["own_side"] == "left")
                team = "own" if is_own else "opponent"
                cls = -1 if o[1] in (0, 2) else (own if is_own else opp)
            tr = tracks.setdefault(o[0], {"pts": [], "cls": cls, "team": team, "jersey": int(o[4])})
            tr["pts"].append((t, o[2], o[3]))
    for tr in tracks.values():
        pts = np.array(sorted(tr["pts"]))
        tr["pts"] = np.column_stack([pts[:, 0], to_metres(H, pts[:, 1:])])
    return tracks


def assign_ground(people, tracks, ground, classes, gate):
    """Ordnet in einem Bild Veo-Spuren und erkannte Personen am Boden eindeutig zu, getrennt nach Trikotfarbe.

    people: Liste (Spurnummer, Position); ground: Fußpunkte der Boxen in Metern (NaN = ungültig);
    classes: Farbklasse je Box. Rückgabe: Liste (Spurnummer, Boxindex, Abstand in Metern)."""
    pairs = []
    if not people or not len(ground):
        return pairs
    valid = ~np.isnan(ground[:, 0])
    for cls in set(tracks[tid]["cls"] for tid, _ in people):
        rows = [i for i, (tid, _) in enumerate(people) if tracks[tid]["cls"] == cls]
        # Spuren ohne Farbklasse (Torhüter) dürfen nur Boxen ohne Mannschaftsfarbe nehmen
        cols = [j for j in range(len(ground)) if valid[j] and classes[j] == cls]
        if not rows or not cols:
            continue
        cost = np.linalg.norm(np.array([people[i][1] for i in rows])[:, None] - ground[cols][None], axis=2)
        r, c = linear_sum_assignment(np.minimum(cost, gate * 2))
        pairs += [(people[rows[i]][0], cols[j], float(cost[i, j])) for i, j in zip(r, c) if cost[i, j] < gate]
    return pairs


def positions_at(tracks, t):
    """Alle Spuren zur Videozeit t: Liste (Spurnummer, Position), linear zwischen Messpunkten."""
    out = []
    for tid, tr in tracks.items():
        pts = tr["pts"]
        i = np.searchsorted(pts[:, 0], t)
        if i == 0 or i == len(pts):
            continue
        a, b = pts[i - 1], pts[i]
        if b[0] - a[0] > 0.7:
            continue
        out.append((tid, a[1:] + (b[1:] - a[1:]) * (t - a[0]) / (b[0] - a[0])))
    return out
