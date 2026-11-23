"""Rückennummern je Spur und Spieler aus einzelnen Lesungen (tools/jersey_reader.py), ohne Fremddaten.

Reine Logik ohne Datei-, Video- oder Netzzugriff (außer load_squad):
  1. vote: Je Spur stimmen die Lesungen über die Nummer ab. Eine Nummer gilt nur, wenn sie klar überwiegt,
     von mehreren Zeitfenstern über mindestens eine Sekunde gestützt wird und die meisten Fenster sie lesen;
     sonst bleibt die Spur „unbekannt“ (lieber unbekannt als falsch).
  2. assign: Je Mannschaft trägt eine Nummer zur selben Zeit höchstens ein Spieler.
  3. merge_by_number: Stücke einer Mannschaft mit derselben Nummer, die sich zeitlich nicht überlappen und
     deren Lücke körperlich machbar ist, sind ein Spieler. Ein Stück mit schwächeren, aber klaren Lesungen
     schließt sich einem schon sicher erkannten Spieler mit dieser Nummer an.
"""
import json
from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

CLASSES = 100            # Klasse 0 = keine Nummer lesbar, Klasse n = Nummer n (1–99)
NO_NUMBER = 0
TEAMS = ("own", "opponent")
NO_NUMBER_TEAMS = ("referee",)
MAX_NO_NUMBER = 0.5      # Lesungen, die eher „keine Nummer“ sagen, zählen nicht
WINDOW_S = 0.4           # Nachbarbilder sind kaum unabhängig: je Fenster zählt nur die beste Lesung
EPS = 0.01               # Untergrenze der Wahrscheinlichkeit: eine einzelne Lesung kann eine Nummer nicht ausschließen
MIN_CONFIDENCE = 0.9     # normierte Sicherheit, ab der eine Nummer vergeben wird
MIN_WINDOWS = 5          # so viele Fenster müssen die Nummer als beste lesen (an Szene 705 eingestellt)
MIN_SPAN_S = 1.0         # und zwischen dem ersten und letzten davon so viel Zeit liegen
MIN_AGREEMENT = 0.7      # Anteil der zählenden Fenster, die die Nummer als beste lesen (15 gegen 1); an Szene 705 eingestellt
MERGE_SPEED = 8.0        # m/s: schneller kann ein Spieler eine Lücke zwischen zwei Stücken nicht überbrücken
POSITION_NOISE = 1.5     # m: so ungenau ist die Lage am Boden in Blickrichtung (Wechsel zwischen zwei Stücken)
OVERLAP_S = 0.5          # s: so lange dürfen zwei Stücke gleichzeitig zu sehen sein und doch eine Person sein
                         # (das Tracking übergibt einen Spieler oft mit ein paar Bildern Überschneidung)
JOIN_CONFIDENCE = 0.9    # Ein Stück schließt sich einem schon sicher erkannten Spieler mit derselben Nummer an,
JOIN_AGREEMENT = 0.5     # wenn seine eigenen Lesungen diese Nummer so klar stützen (weniger als für eine neue Nummer:
JOIN_WINDOWS = 2         # dass es die Nummer in der Szene gibt, ist schon belegt)


class SquadError(ValueError):
    """Die Kaderdatei ist kein gültiger Kader (siehe specs/001-rueckennummern/contracts/squad-list.md)."""


@dataclass(frozen=True)
class Reading:
    """Eine Lesung eines Rückens: Wahrscheinlichkeiten über CLASSES Klassen (Summe 1), Gewicht 0,3 bis 1."""
    track: str
    frame: int
    probs: np.ndarray
    weight: float


@dataclass(frozen=True)
class TrackNumber:
    """Ergebnis der Abstimmung einer Spur."""
    track: str
    team: str
    ranked: list[tuple[int, float]]   # Nummern mit normierter Sicherheit, absteigend
    windows: int                      # Fenster, deren beste Lesung die beste Nummer ist
    span_s: float                     # Zeit zwischen dem ersten und letzten dieser Fenster
    agreement: float                  # Anteil dieser Fenster an allen zählenden Fenstern

    @property
    def supported(self) -> bool:
        return (bool(self.ranked) and self.ranked[0][1] >= MIN_CONFIDENCE and self.windows >= MIN_WINDOWS
                and self.span_s >= MIN_SPAN_S and self.agreement >= MIN_AGREEMENT)

    @property
    def number(self) -> int | None:
        return self.ranked[0][0] if self.supported else None

    @property
    def confidence(self) -> float:
        return self.ranked[0][1] if self.supported else 0.0


def _best_per_window(readings: Sequence[Reading], fps: float) -> list[Reading]:
    best: dict[int, Reading] = {}
    for r in readings:
        if r.probs[NO_NUMBER] >= MAX_NO_NUMBER:
            continue
        w = int(r.frame // (WINDOW_S * fps))
        if w not in best or r.weight * r.probs[1:].max() > best[w].weight * best[w].probs[1:].max():
            best[w] = r
    return [best[w] for w in sorted(best)]


def _vote_track(track: str, team: str, readings: Sequence[Reading], fps: float,
                allowed: frozenset[int] | None) -> TrackNumber:
    counted = _best_per_window(readings, fps)
    numbers = np.array(sorted(allowed) if allowed else range(1, CLASSES))
    if not counted:
        return TrackNumber(track, team, [], 0, 0.0, 0.0)
    p = np.stack([r.probs[numbers] for r in counted])
    p = p / p.sum(axis=1, keepdims=True)                 # nur erlaubte Nummern, je Lesung neu normiert
    w = np.array([r.weight for r in counted])
    score = (w[:, None] * np.log(p + EPS)).sum(axis=0)
    post = np.exp(score - score.max())
    post /= post.sum()
    order = np.argsort(-post)[:5]
    ranked = [(int(numbers[k]), float(post[k])) for k in order]
    top = order[0]
    agree = [r.frame for r, row in zip(counted, p) if int(np.argmax(row)) == top]
    span = (agree[-1] - agree[0]) / fps if agree else 0.0
    return TrackNumber(track, team, ranked, len(agree), float(span), len(agree) / len(counted))


def vote(readings: Sequence[Reading], teams: Mapping[str, str], fps: float,
         squad: Mapping[str, frozenset[int]] | None = None) -> dict[str, TrackNumber]:
    """Nummer je Spur. teams: Spur -> Mannschaft; Spuren von Schiedsrichtern bekommen kein Ergebnis.
    squad: erlaubte Nummern je Mannschaft (fehlt eine Mannschaft, sind alle 1–99 erlaubt)."""
    by_track: dict[str, list[Reading]] = {}
    for r in readings:
        by_track.setdefault(r.track, []).append(r)
    out = {}
    for track, team in teams.items():
        if team in NO_NUMBER_TEAMS:
            continue
        allowed = (squad or {}).get(team)
        out[track] = _vote_track(track, team, by_track.get(track, []), fps, allowed)
    return out


def load_squad(path: str | Path) -> dict[str, frozenset[int]]:
    """Liest einen Kader {"own": [...], "opponent": [...]}; leere oder fehlende Listen erlauben alle Nummern."""
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as err:
        raise SquadError(f"Kader {path} nicht lesbar: {err}") from err
    if not isinstance(data, dict):
        raise SquadError("Kader muss ein Objekt mit den Schlüsseln own und opponent sein")
    unknown = set(data) - set(TEAMS)
    if unknown:
        raise SquadError(f"Kader: unbekannte Schlüssel {sorted(unknown)} (erlaubt: own, opponent)")
    out = {}
    for team, numbers in data.items():
        if not isinstance(numbers, list) or not all(isinstance(n, int) and not isinstance(n, bool) for n in numbers):
            raise SquadError(f"Kader {team}: nur eine Liste ganzer Zahlen, keine Namen")
        if any(not 1 <= n <= 99 for n in numbers):
            raise SquadError(f"Kader {team}: Nummern müssen zwischen 1 und 99 liegen")
        if len(set(numbers)) != len(numbers):
            raise SquadError(f"Kader {team}: Nummer doppelt")
        if numbers:
            out[team] = frozenset(numbers)
    return out


@dataclass
class Player:
    """Ein Spieler: ein oder mehrere Spurstücke derselben Person, zeitlich ohne Überlappung."""
    id: str
    team: str
    tracks: list[str] = field(default_factory=list)
    number: int | None = None
    confidence: float = 0.0


def _overlap(a: Set[int], b: Set[int], fps: float) -> bool:
    """Gleichzeitig zu sehen, länger als OVERLAP_S?"""
    return len(a & b) > OVERLAP_S * fps


def assign(votes: Mapping[str, TrackNumber], present: Mapping[str, Set[int]], fps: float) -> dict[str, int | None]:
    """Nummer je Spur, ohne dass zwei zeitlich überlappende Spuren einer Mannschaft dieselbe tragen.

    Je Mannschaft der Sicherheit nach absteigend: Eine Spur bekommt ihre Nummer, wenn keine überlappende Spur sie
    schon hat; sonst bleibt sie unbekannt (eine zweite Nummer kann nach vote die Schwelle nie erreichen, weil die
    Sicherheiten zusammen 1 ergeben). Spuren ohne Ergebnis (Schiedsrichter) bleiben unbekannt.
    ponytail: gierig statt optimaler Zuordnung über alle Spuren; reicht bei rund 20 Spuren je Mannschaft, sonst
    ganzzahlige Optimierung."""
    out: dict[str, int | None] = {track: None for track in present}
    taken: dict[tuple[str, int], list[str]] = {}
    for track, v in sorted(votes.items(), key=lambda kv: -kv[1].confidence):
        if v.number is None or track not in present:
            continue
        holders = taken.setdefault((v.team, v.number), [])
        if any(_overlap(present[track], present[h], fps) for h in holders):
            continue
        holders.append(track)
        out[track] = v.number
    return out


def merge_by_number(numbers: Mapping[str, int | None], votes: Mapping[str, TrackNumber],
                    positions: Mapping[str, Mapping[int, np.ndarray]], teams: Mapping[str, str],
                    fps: float) -> list[Player]:
    """Spieler aus Spuren: Stücke einer Mannschaft mit derselben Nummer werden einer, wenn der Spieler an jedem
    Wechsel zwischen ihnen nicht schneller als MERGE_SPEED laufen müsste (positions: Spur -> {Bild: Lage am Boden
    in m}). Passt ein Stück nicht dazu, verliert es die Nummer und bleibt ein eigener, unbekannter Spieler."""
    present = {t: set(f) for t, f in positions.items()}
    spans = {t: (min(f), max(f)) for t, f in present.items()}

    def feasible(a: str, b: str) -> bool:
        if _overlap(present[a], present[b], fps):
            return False
        seq = sorted([(f, a) for f in present[a] - present[b]] + [(f, b) for f in present[b] - present[a]])
        for (f0, t0), (f1, t1) in zip(seq, seq[1:]):
            if t0 != t1:   # Wechsel: so weit, wie er in der Zeit kommt, plus Messrauschen
                d = float(np.linalg.norm(np.asarray(positions[t1][f1], float) - np.asarray(positions[t0][f0], float)))
                if d > MERGE_SPEED * (f1 - f0) / fps + POSITION_NOISE:
                    return False
        return True

    groups: dict[tuple[str, int], list[str]] = {}
    players: list[Player] = []
    for track, number in numbers.items():
        if number is None:
            players.append(Player(track, teams[track], [track]))
        else:
            groups.setdefault((teams[track], number), []).append(track)
    for (team, number), tracks in groups.items():
        chain: list[str] = []
        for track in sorted(tracks, key=lambda t: -votes[t].confidence):
            if all(feasible(track, other) for other in chain):
                chain.append(track)
            else:
                players.append(Player(track, team, [track]))
        chain.sort(key=lambda t: spans[t][0])
        players.append(Player(chain[0], team, chain, number, max(votes[t].confidence for t in chain)))
    _join_fragments(players, votes, spans, feasible)
    return sorted(players, key=lambda p: spans[p.tracks[0]][0])


def _join_fragments(players: list[Player], votes: Mapping[str, TrackNumber], spans: Mapping[str, tuple[int, int]],
                    feasible) -> None:
    """Unbekannte Stücke an sicher erkannte Spieler hängen (ändert players): Die beste Nummer des Stücks muss
    JOIN_* erfüllen, ein Spieler dieser Mannschaft mit der Nummer existieren, und das Stück darf keines seiner
    Stücke zeitlich überlappen und muss von jedem erreichbar sein."""
    known = {(p.team, p.number): p for p in players if p.number is not None}
    for p in [p for p in players if p.number is None and len(p.tracks) == 1]:
        v = votes.get(p.tracks[0])
        if v is None or not v.ranked:
            continue
        number, confidence = v.ranked[0]
        target = known.get((p.team, number))
        if target is None or confidence < JOIN_CONFIDENCE or v.agreement < JOIN_AGREEMENT or v.windows < JOIN_WINDOWS:
            continue
        track = p.tracks[0]
        if not all(feasible(track, t) for t in target.tracks):
            continue
        target.tracks = sorted(target.tracks + [track], key=lambda t: spans[t][0])
        target.id = target.tracks[0]
        players.remove(p)
