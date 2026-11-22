"""Szenenauswertung ohne Veo: eigene Spuren mit Mannschaft und Name, eigener Ball.

Wird von tools/veo_scene.py aufgerufen, wenn statt Veo-Angaben "-" übergeben wird. Grundlage sind das eigene
Spielertracking (tools/track_players.py) und die eigene Ballspur (tools/veo_ball.py).
"""
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import track_players  # noqa: E402

BALL_GAP = 2.0        # s: so lange Lücken der eigenen Ballspur werden gerade überbrückt
BALL_REACH = 0.9      # m: so nah an einer Fußspitze gilt der Ball als am Fuß
BALL_AT_FOOT = 0.13   # m: Abstand Ballmitte zur Fußspitze bei Ballkontakt
TEAM_OF_COLOUR = {0: "own", 1: "opponent", 2: "referee"}   # Trikotfarben des Heimspiels (tools/veo_colors.py): rot = wir
KEEPER_INSIDE = 1.5   # m: so weit innerhalb der Linien muss eine solche Spur im Mittel liegen (Trainer, Betreuer stehen an der Linie)
KEEPER_MIN = 5.0      # s: so lange muss eine Spur in unbekannter Farbe auf dem Platz sein, um als Torwart zu gelten
MIN_APPEARANCE = 0.5  # s: kürzere Auftritte einer Figur entfallen
OWN_SAME = 0.6        # m: zwei eigene Spuren derselben Mannschaft näher als das sind dieselbe Person
OWN_GAP = 1.0         # s: so lange Lücken einer eigenen Spur werden überbrückt
OWN_ID = 1000         # Spuren ohne Rückennummer: Nummern ab hier (nur intern, nicht auf dem Trikot)


def _nan_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Zusammenhängende wahre Abschnitte [a, b) einer Bool-Folge."""
    edges = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def own_ball(out: np.ndarray, max_gap: float) -> np.ndarray:
    """Ballspur aus dem Video im Takt der Ausgabe (NaN = nicht gefunden). Lücken bis max_gap Bilder werden
    gerade überbrückt (der Ball rollt zwischen zwei Berührungen geradeaus; am Fuß zieht ihn später
    attach_ball heran), längere Lücken und Anfang und Ende halten die nächste bekannte Lage."""
    n_out = len(out)
    seen = np.flatnonzero(~np.isnan(out[:, 0]))
    if not len(seen):
        return out
    idx = np.arange(n_out)
    filled = np.column_stack([np.interp(idx, seen, out[seen, a]) for a in range(2)])
    for a, b in _nan_runs(np.isnan(out[:, 0])):
        inner = a > 0 and b < n_out
        if inner and b - a <= max_gap:
            continue
        # lange Lücke: in der ersten Hälfte die letzte, in der zweiten die nächste Lage halten
        before = out[a - 1] if a > 0 else out[b] if b < n_out else filled[a]
        after = out[b] if b < n_out else before
        mid = (a + b) // 2
        filled[a:mid], filled[mid:b] = before, after
    return filled


def attach_ball(ball_xy: np.ndarray, feet: np.ndarray, fps: float) -> np.ndarray:
    """Zieht den Ball an den Fuß, wenn er in Reichweite liegt: Die Ballspur ist in Blickrichtung auf rund einen halben Meter
    genau, ein geführter Ball lag deshalb oft neben dem Spieler. feet: (T, F, 2) Fußspitzen aller Spieler (NaN = keiner)."""
    T = len(ball_xy)
    shift = np.zeros((T, 2))
    for t in range(T):
        if np.isnan(ball_xy[t, 0]):
            continue
        d = np.linalg.norm(feet[t] - ball_xy[t], axis=1)
        if np.isnan(d).all():
            continue
        k = int(np.nanargmin(d))
        if d[k] >= BALL_REACH:
            continue
        toward = (ball_xy[t] - feet[t, k]) / max(d[k], 1e-6)
        target = feet[t, k] + toward * BALL_AT_FOOT
        w = np.clip((BALL_REACH - d[k]) / (BALL_REACH - BALL_AT_FOOT), 0, 1)
        shift[t] = (target - ball_xy[t]) * (w * w * (3 - 2 * w))
    kernel = np.hanning(7)[1:-1]
    kernel /= kernel.sum()
    shift = np.column_stack([np.convolve(shift[:, a], kernel, "same") for a in range(2)])   # nicht von Bild zu Bild springen
    return ball_xy + shift


def own_identities(det, cam, n, video):
    """Eigenes Tracking statt Veo (tools/track_players.py): Spuren auf dem Platz mit Mannschaft und Name.

    Personen, die meist außerhalb der Linien stehen (Auswechselspieler, Trainer, Zuschauer), zählen nicht, ebenso
    Spuren in Leibchen, die im Farbton deutlich vom Trikot ihrer Farbklasse abweichen (tools/track_players.split_bibs).
    Eine Spur in unbekannter Farbe, die lange auf dem Platz ist, gilt als Torwart; er gehört zu der Mannschaft,
    deren Feldspieler im Mittel näher an seinem Tor stehen. Rückgabe: {(Mannschaft, Nummer): (Farbe, Torwart,
    {Bild: Zeile})}."""
    L, W = cam["pitch"]["length"], cam["pitch"]["width"]
    fps = det["fps"]
    kept, centre = [], {}
    result = track_players.track(det, cam)
    team = track_players.split_bibs(result, track_players.track_hues(video, result), fps)   # Leibchen der Auswechselspieler zählen nicht
    for tr in (t for t, ok in zip(result, team) if ok):
        fs = sorted(tr["frames"])
        pts = np.array([tr["frames"][f][:2] for f in fs])
        mid = np.median(pts, axis=0)
        inside = KEEPER_INSIDE if tr["colour"] < 0 else 0.0   # ohne Trikotfarbe: nicht die Leute an der Seitenlinie
        if abs(mid[0]) > L / 2 - inside or abs(mid[1]) > W / 2 - inside:
            continue
        if tr["colour"] < 0 and (fs[-1] - fs[0]) / fps < KEEPER_MIN:
            continue
        kept.append((fs[0], tr, mid))
        if tr["colour"] in (0, 1):
            centre.setdefault(tr["colour"], []).append(pts[:, 0])
    mean_x = {c: float(np.mean(np.concatenate(v))) for c, v in centre.items()}
    out, count = {}, Counter()
    for _, tr, mid in sorted(kept, key=lambda k: k[0]):
        colour, keeper = tr["colour"], tr["colour"] < 0
        if keeper:   # Torwart: Mannschaft, die im Mittel näher an seinem Tor steht
            goal = math.copysign(L / 2, mid[0])
            colour = min(mean_x, key=lambda c: abs(mean_x[c] - goal)) if mean_x else 0
        team = TEAM_OF_COLOUR.get(colour, "opponent")
        count[team] += 1
        out[(team, OWN_ID + count[team])] = (colour, keeper, tr["frames"])
    return out


def drop_same_place(obs: dict, where: list[dict]) -> int:
    """Zwei Spuren derselben Mannschaft an derselben Stelle sind eine Person: In dem Bild weicht die nur
    überbrückte Spur, sind beide gemessen, die kürzere. Ändert obs und where; gibt die Zahl entfernter
    Spieler-Bilder zurück."""
    removed = 0
    length = {key: int((~np.isnan(rows[:, 0])).sum()) for key, rows in obs.items()}
    for fi in range(len(where)):
        keys = list(where[fi])
        for a in range(len(keys)):
            for b in range(a + 1, len(keys)):
                ka, kb = keys[a], keys[b]
                if ka[0] != kb[0] or ka not in where[fi] or kb not in where[fi]:
                    continue
                if np.linalg.norm(where[fi][ka] - where[fi][kb]) >= OWN_SAME:
                    continue
                measured_a, measured_b = not np.isnan(obs[ka][fi, 0]), not np.isnan(obs[kb][fi, 0])
                loser = kb if (measured_a, length[ka]) >= (measured_b, length[kb]) else ka
                del where[fi][loser]
                obs[loser][fi] = np.nan
                removed += 1
    return removed
