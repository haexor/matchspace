#!/usr/bin/env python3
"""Stehende Füße am Boden festhalten (Hilfsmodul zu tools/pose_limits.py).

Ein Fuß, der aufsteht, bleibt an seiner Stelle auf dem Rasen, bis er abhebt (kein Rutschen); das Bein wird dazu neu
gestellt. Wo die Vorlage gerade keinen Gang zeigt (Stand, Schleichen), macht die Figur einzelne Schritte, statt mit
festgehaltenen Füßen über den Rasen zu gleiten oder das Bein zu überdehnen.

  contacts:   Bilder, in denen ein Fuß steht (Knöchel tief und langsamer als der Körper);
  body_pace:  Tempo des Körpers, daraus ob die Vorlage einen Gang zeigt;
  step_plan:  Schritte, wo kein Gang zu sehen ist;
  plant_feet: Gelenke einer Figur mit festgehaltenen Füßen, samt Rutschmaß vorher und nachher.
Achsen: x, y waagerecht, z hoch; Positionen relativ zum Becken.
"""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from pose_limits import CLEARANCE, DEG, I, dot, runs, unit  # noqa: E402

CONTACT_ON, CONTACT_OFF = 0.105, 0.14   # Knöchelhöhe (m), unter der ein Fuß aufsetzt bzw. über der er abhebt
# Ein stehender Fuß ruht auf dem Rasen, ein schwingender ist etwa doppelt so schnell wie der Körper.
# Grenzen für das Tempo des Fußes über dem Rasen: Anteil des Körpertempos plus fester Betrag (m/s).
SLOW_ON, SLOW_OFF = (0.5, 0.3), (0.9, 0.5)
MAX_SLIP = 0.4                         # m: so weit darf ein stehender Fuß von seiner geschätzten Lage abweichen
STILL_PACE = 0.5                        # m/s: darunter zeigt die Vorlage keinen Gang (tools/motion_clips.STANDING); dort einzelne Schritte
STEP_REACH = 0.22                       # m: so weit darf sich der Körper von einem stehenden Fuß entfernen, dann tritt er nach
STEP_TAKES = 0.35                       # s: Dauer eines solchen Schritts
STEP_LIFT = 0.08                        # m: so hoch hebt sich der Fuß dabei
MIN_CONTACT = 3                         # Bilder
FADE = 5                                # Bilder, über die eine Korrektur vor und nach dem Aufsetzen ausläuft


def _speed(xy, fps, span=1):
    v = np.zeros(len(xy))
    if len(xy) > 2 * span:
        v[span:-span] = np.linalg.norm(xy[2 * span:] - xy[:-2 * span], axis=1) * fps / (2 * span)
        v[:span], v[-span:] = v[span], v[-span - 1]
    return v


def contacts(ankle, body, fps):
    """Bilder, in denen ein Fuß steht: Knöchel tief und über dem Rasen deutlich langsamer als der Körper.

    ankle: (n, 3) im Feld, body: (n, 2) Bodenposition des Spielers."""
    foot, pace = _speed(ankle[:, :2], fps), _speed(body, fps, 3)
    on = (ankle[:, 2] < CONTACT_ON) & (foot < SLOW_ON[0] * pace + SLOW_ON[1])
    keep = (ankle[:, 2] < CONTACT_OFF) & (foot < SLOW_OFF[0] * pace + SLOW_OFF[1])
    state, out = False, np.zeros(len(ankle), bool)
    for t in range(len(ankle)):
        state = bool(on[t] or (state and keep[t]))
        out[t] = state
    for a, b in runs(~out):  # kurze Aussetzer von ein, zwei Bildern mitten im Stand schließen
        if 0 < a and b < len(out) and b - a <= 2 and keep[a:b].all():
            out[a:b] = True
    return out


def _lock_intervals(xy, a, b, out):
    """Teilt ein Stück Bodenkontakt so, dass der Fuß je Teilstück höchstens MAX_SLIP versetzt werden muss."""
    if b - a < MIN_CONTACT:
        return
    mid = (a + b) // 2
    if np.linalg.norm(xy[a:b] - xy[mid], axis=1).max() <= MAX_SLIP:
        out.append((a, b, mid))
        return
    _lock_intervals(xy, a, mid - 1, out)
    _lock_intervals(xy, mid + 1, b, out)


def body_pace(positions, fps):
    """Tempo (m/s) wie in tools/pose_fit.heading_speed: über ±0,4 s gemessen und nachgeglättet."""
    span = max(1, round(0.4 * fps))
    T = len(positions)
    out, smooth = np.zeros(T), 0.0
    for t in range(T):
        a, b = max(0, t - span), min(T - 1, t + span)
        v = np.linalg.norm(positions[b] - positions[a]) / max((b - a) / fps, 1e-9) if b > a else 0.0
        smooth += (min(v, 12.0) - smooth) * 0.3
        out[t] = smooth
    return out


def step_plan(natural, fps, still):
    """Schritte im Stand und beim Schleichen: Wo die Vorlage keinen Gang zeigt (still), stehen die Füße fest.
    Entfernt sich der Körper mehr als STEP_REACH von einem Fuß, hebt die Figur ihn an und setzt ihn neben die
    Stelle, an die er gehört, etwas in Bewegungsrichtung voraus; immer nur ein Fuß zugleich.

    natural: {Seite: (n, 2)} Lage der Knöchel ohne Festhalten. Rückgabe: {Seite: (n, 2) Lage, (n,) Anhebung}."""
    n = len(still)
    took = max(2, round(STEP_TAKES * fps))
    out = {side: (natural[side].copy(), np.zeros(n)) for side in "lr"}
    for a, b in runs(still, 2):
        plant = {side: natural[side][a].copy() for side in "lr"}
        swing = None                                     # (Seite, Beginn, Ende, von, nach)
        for t in range(a, b):
            if swing is None:
                error = {side: np.linalg.norm(natural[side][t] - plant[side]) for side in "lr"}
                side = max(error, key=error.get)
                if error[side] > STEP_REACH and t + 2 < b:
                    end = min(t + took, b - 1)
                    ahead = natural[side][min(end + took // 2, b - 1)]
                    swing = (side, t, end, plant[side].copy(), ahead.copy())
            for side in "lr":
                if swing is not None and swing[0] == side:
                    _, t0, t1, frm, to = swing
                    u = (t - t0) / max(t1 - t0, 1)
                    w = u * u * (3 - 2 * u)
                    out[side][0][t] = frm * (1 - w) + to * w
                    out[side][1][t] = STEP_LIFT * math.sin(math.pi * u)
                    if t >= t1:
                        plant[side] = to
                        swing = None
                else:
                    out[side][0][t] = plant[side]
    return out


def plant_feet(joints, positions, fps, lengths, skip=None):
    """Hält stehende Füße an ihrer Stelle auf dem Rasen fest und stellt das Bein passend (Knie neu berechnet).

    Wo die Vorlage gerade keinen Gang zeigt (Stand, Schleichen unter 0,5 m/s), macht die Figur einzelne
    Schritte (step_plan), statt mit festgehaltenen Füßen über den Rasen zu gleiten oder das Bein zu überdehnen.

    joints: (T, 20, 3) relativ zur Bodenposition, positions: (T, 2); skip: Bilder, in denen
    nichts festgehalten wird (Spieler am Boden). Rückgabe: neue Gelenke und das
    mittlere Rutschen stehender Füße vorher und nachher (m/s) samt Zahl der Bilder mit Bodenkontakt."""
    out = joints.copy()
    before, after, count = 0.0, 0.0, 0
    for a, b in runs(~np.isnan(joints[:, 0, 0]) & ~np.isnan(positions[:, 0]), 4):
        world = joints[a:b].copy()
        world[:, :, :2] += positions[a:b, None]
        n = b - a
        still = body_pace(positions[a:b], fps) < STILL_PACE
        if skip is not None:
            still &= ~skip[a:b]
        offsets, lift, stands = {}, {}, {}
        for side in "lr":
            ankle = I[side + "Ankle"]
            stand = contacts(world[:, ankle], positions[a:b], fps)
            if skip is not None:
                stand &= ~skip[a:b]
            intervals = []
            for s0, s1 in runs(stand & ~still, MIN_CONTACT):
                _lock_intervals(world[:, ankle, :2], s0, s1, intervals)
            offset = np.full((n, 2), np.nan)
            for s0, s1, mid in intervals:
                offset[s0:s1] = world[mid, ankle, :2] - world[s0:s1, ankle, :2]
            offsets[side], lift[side], stands[side] = offset, np.zeros(n), stand
        plan = step_plan({side: world[:, I[side + "Ankle"], :2] for side in "lr"}, fps, still)
        for side in "lr":
            ankle = I[side + "Ankle"]
            offset = offsets[side]
            offset[still] = plan[side][0][still] - world[still, ankle, :2]
            lift[side][still] = plan[side][1][still]
            stands[side] = (stands[side] & ~still) | (still & (plan[side][1] == 0))
            known = np.flatnonzero(~np.isnan(offset[:, 0]))
            if not len(known):          # nie Bodenkontakt in diesem Stück: Bein bleibt, wie es ist
                offset[:] = 0.0
                continue
            for i, j in zip(known[:-1], known[1:]):  # Schwungphase: weich von einer Korrektur zur nächsten
                if j - i > 1:
                    w = (np.arange(i + 1, j) - i) / (j - i)
                    w = (w * w * (3 - 2 * w))[:, None]
                    offset[i + 1:j] = offset[i] * (1 - w) + offset[j] * w
            first, last = known[0], known[-1]
            lead = np.clip((np.arange(first) - (first - FADE)) / FADE, 0, 1)[:, None]
            offset[:first] = offset[first] * lead
            tail = np.clip(((last + FADE) - np.arange(last + 1, n)) / FADE, 0, 1)[:, None]
            offset[last + 1:] = offset[last] * tail

        for side in "lr":
            hip, knee, ankle = I[side + "Hip"], I[side + "Knee"], I[side + "Ankle"]
            target = world[:, ankle].copy()
            target[:, :2] += offsets[side]
            target[:, 2] += lift[side]
            l1, l2 = lengths[side + "Knee"], lengths[side + "Ankle"]
            d = target - world[:, hip]
            dist = np.linalg.norm(d, axis=1, keepdims=True)
            dn = d / np.maximum(dist, 1e-9)
            reach = np.clip(dist, abs(l1 - l2) + 1e-3, l1 + l2 - 1e-3)
            along = (l1 ** 2 - l2 ** 2 + reach ** 2) / (2 * reach)
            side_len = np.sqrt(np.maximum(l1 ** 2 - along ** 2, 0))
            # Das Knie liegt vor der Linie Hüfte-Knöchel (es beugt nur nach hinten), höchstens 45° zur Seite gedreht.
            across = world[:, I["lHip"]] - world[:, I["rHip"]]
            across = unit(across - dot(across, dn) * dn)
            front = -np.cross(across, dn)
            pole = world[:, knee] - world[:, hip]
            pole = pole - dot(pole, dn) * dn
            turn = np.where(np.linalg.norm(pole, axis=1, keepdims=True) > 0.01, np.arctan2(dot(pole, across), dot(pole, front)), 0.0)
            turn = np.clip(turn, -45 * DEG, 45 * DEG)
            pole = np.cos(turn) * front + np.sin(turn) * across
            new_knee = world[:, hip] + dn * along + pole * side_len
            new_ankle = world[:, hip] + dn * reach
            moved = new_ankle - world[:, ankle]

            stand = stands[side]
            both = stand[1:] & stand[:-1]  # aufeinanderfolgende Bilder, in denen der Fuß steht

            def slip(points):
                return float((np.linalg.norm(points[1:, :2] - points[:-1, :2], axis=1) * fps)[both].sum())
            before += slip(world[:, ankle])
            after += slip(new_ankle)
            count += int(both.sum())
            for name in (side + "Ankle", side + "Heel", side + "Toe"):
                out[a:b, I[name]] = joints[a:b, I[name]] + moved
            out[a:b, knee] = new_knee - np.column_stack([positions[a:b], np.zeros(n)])
        low = (out[a:b, :, 2] - CLEARANCE).min(axis=1)
        out[a:b, :, 2] -= np.minimum(low, 0)[:, None]  # ein gestrecktes Bein darf nichts unter den Rasen drücken
    return out, before, after, count
