"""Klare Stellen von der Auswertung selbst beantworten, damit der Nutzer nur noch Unklares sehen muss.

An einer Stelle mit mindestens zwei Beteiligten vorher gilt: Sieht jede Box nachher einer Box von vorher um mindestens
MARGIN ähnlicher als allen anderen (Kosinus der gelernten Bildmerkmale, appearance.learn_fingerprint), ist die Zuordnung
eindeutig und wird als Antwort mit Herkunft "auto" eingetragen. An manuell beantworteten Stellen ändert das nichts.
Offen bleiben: Stellen mit einem Beteiligten vorher, Kontrollstellen, Nummernstellen und alle mit zu geringem Abstand.
Gemessen an den ersten 29 Antworten von Hand traf das Aussehen bei Abstand ab 0,3 in 32 von 32 Fällen
(specs/003-eigene-referenz/research.md R13). Hinweis: Dasselbe Merkmal entscheidet beim Verbinden mit; die Referenz
ist an diesen Stellen deshalb keine unabhängige Prüfung des Aussehens.

Reine Logik ohne Datei- und Netzzugriff.
"""
import datetime
from collections.abc import Mapping, Sequence

import numpy as np

import reference as ref

MARGIN = 0.3                       # Abstand zwischen bester und zweitbester Box von vorher (Kosinus)
MIN_IMAGES = 2                     # Erkennungen mit Merkmalen, ab denen eine Seite einer Stelle zählt
SKIP = ("control", "number", "number-unsure")   # unabhängige Prüfung bzw. nur Nummer: nie automatisch


def _mean(rows: Sequence[int], embedding: np.ndarray) -> np.ndarray | None:
    if len(rows) < MIN_IMAGES:
        return None
    v = embedding[list(rows)].astype(np.float32).mean(0)
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else None


def decide(spot: ref.Spot, rows: Mapping[str, Mapping[int, int]], embedding: np.ndarray, margin: float = MARGIN):
    """Zuordnung Buchstabe nachher -> Buchstabe vorher oder None, wenn nicht eindeutig. rows: Spieler -> Bild -> Zeile
    im Merkmalsfeld."""
    if any(k in SKIP for k in spot.kinds) or len(spot.before) < 2 or not spot.after:
        return None
    mine = lambda name, lo, hi: [i for f, i in rows.get(name, {}).items() if lo <= f < hi]   # noqa: E731
    before = {p.letter: _mean(mine(p.player, spot.start, spot.frame), embedding) for p in spot.before}
    before = {k: v for k, v in before.items() if v is not None}
    if len(before) < 2:
        return None
    mapping = {}
    for p in spot.after:
        v = _mean(mine(p.player, spot.frame, spot.end + 1), embedding)
        if v is None:
            return None
        sims = sorted(((float(v @ b), k) for k, b in before.items()), reverse=True)
        if sims[0][0] - sims[1][0] < margin:
            return None
        mapping[p.letter] = sims[0][1]
    if len(set(mapping.values())) != len(mapping):   # zwei Boxen auf derselben Person: nicht eindeutig
        return None
    return mapping


def answers(spots: Sequence[ref.Spot], rows: Mapping[str, Mapping[int, int]], embedding: np.ndarray,
            decided: set[str] = frozenset(), margin: float = MARGIN) -> list[ref.Answer]:
    """Automatische Antworten für alle klaren Stellen, außer den bereits von Hand entschiedenen (decided)."""
    at = datetime.datetime.now().isoformat(timespec="seconds")
    out = []
    for s in spots:
        if s.id in decided:
            continue
        m = decide(s, rows, embedding, margin)
        if m is not None:
            out.append(ref.Answer(s.id, "mapped", m, {}, {}, at, False, "auto"))
    return out
