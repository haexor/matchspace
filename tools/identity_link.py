#!/usr/bin/env python3
"""Eine Identität je Spieler: Spurstücke derselben Person vorsichtig verbinden, ohne Fremddaten.

Reine Logik ohne Datei-, Video- oder Netzzugriff (außer der Kommandozeile):
  split_by_colour: Trägt eine Spur mindestens MIN_FOREIGN_S lang das Trikot der anderen Mannschaft, folgt sie
        dort nicht mehr ihrer Person (Spurwechsel im Gedränge, research.md R3). Sie wird getrennt; der fremde
        Abschnitt wird ein Stück der anderen Mannschaft, außer dort läuft schon eine Spur dieser Mannschaft.
  split_by_numbers: Lesen sich die Rücken vor und nach einem Kontakt zweier Spuren derselben Mannschaft als
        verschiedene sichere Nummern, wird dort getrennt.
  link: Endet ein Stück und beginnt später ein anderes, werden beide verbunden, wenn genau ein Kandidat klar
        passt. Hauptmerkmal ist der Laufweg (wohin konnte der Spieler in der Lücke kommen), dazu dieselbe
        sichere Rückennummer; Aussehen und Größe entscheiden nur mit (research.md R1, R2). Ist der zweitbeste
        Kandidat nicht deutlich schlechter, bleiben die Stücke getrennt: lieber getrennt als vertauscht.
Verboten (specs/002-spieler-identitaet/data-model.md): andere Mannschaft, Torwart mit Feldspieler,
Schiedsrichter untereinander, länger als OVERLAP_S gleichzeitig zu sehen, Beginn mitten in einem anderen Stück,
unerreichbar, verschiedene sichere Nummern.

Aufruf (zum Prüfen):
    .venv/bin/python tools/identity_link.py SZENENVIDEO DETEKTIONEN.json KAMERA.json
"""
import math
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import jersey_identity  # noqa: E402

MERGE_SPEED = 8.0       # m/s: schneller überbrückt kein Spieler eine Lücke (wie jersey_identity)
POSITION_NOISE = 1.5    # m: Messrauschen der Lage am Boden
OVERLAP_S = 0.5         # s: so lange dürfen zwei Stücke einer Person gleichzeitig zu sehen sein (Übergabe)
SPREAD = 2.0            # m/s: so schnell wächst die Unsicherheit der erwarteten Lage mit der Lücke
HEADING_S = 0.5         # s: Laufrichtung aus dem Ende des Stücks
PREDICT_S = 2.0         # s: höchstens so lange wird die Laufrichtung fortgeschrieben (danach bremst jeder)
BASE_COST = 0.5         # Grundkosten jeder Verbindung: Kosten nahe null machten den Verhältnistest beliebig
MAX_COST = 2.5          # teurer wird nie verbunden, auch ohne Konkurrenz
MIN_MARGIN = 1.5        # der zweitbeste Kandidat muss mindestens so viel teurer sein (an 705 eingestellt, an 722 geprüft)
LOOK_WEIGHT = 5.0       # Gewicht von 1 − Kosinus der Bildmerkmale
HEIGHT_WEIGHT = 3.0     # Gewicht des relativen Größenunterschieds
NUMBER_FACTOR = 0.1     # dieselbe sichere Nummer: Kosten mal diesem Faktor
MIN_LOOK = 8            # Erkennungen, ab denen das Aussehen eines Stücks zählt
NO_LINK_TEAMS = ("referee",)
CONTACT_M = 1.5         # m: so nah kommen sich zwei Spuren derselben Mannschaft bei einem Kontakt
CONTACT_JOIN_S = 0.5    # s: Kontakte mit kürzerer Pause dazwischen sind einer
COLOUR_SMOOTH_S = 0.2   # s: Farbe je Erkennung über ± so lange geglättet (Mehrheit)
MIN_FOREIGN_S = 1.0     # s: so lange muss eine Spur fremde Trikots tragen, bevor getrennt wird
SWAP_NEAR_M = 3.0       # m: so nah muss beim Beginn der fremden Farbe eine andere Spur sein, sonst ist es keine Verwechslung
SWAP_WINDOW_S = 0.5     # s: um den Beginn der fremden Farbe so lange wird nach der zweiten Person gesucht
COVERED = 0.5           # Anteil der Bilder, in denen schon eine Spur der anderen Mannschaft dort läuft


@dataclass
class Piece:
    """Ein Spurstück: Bilder -> Zeile wie aus track_players (Lage r[:2], Linse r[3], Box r[4:8], Boxnummer r[8])."""
    id: str
    team: str
    keeper: bool
    frames: Mapping[int, Sequence[float]]

    @property
    def start(self) -> int:
        return min(self.frames)

    @property
    def end(self) -> int:
        return max(self.frames)

    def at(self, f: int) -> np.ndarray:
        return np.asarray(self.frames[f][:2], float)


@dataclass
class Look:
    """Aussehen eines Stücks: gemittelte Bildmerkmale (Länge 1), Zahl der Erkennungen, Größe Schulter–Knöchel in m."""
    mean: np.ndarray | None
    count: int
    height_m: float

    @property
    def sure(self) -> bool:
        return self.mean is not None and self.count >= MIN_LOOK


@dataclass
class Contact:
    """Zwei Stücke derselben Mannschaft näher als CONTACT_M; frame: Bild des geringsten Abstands."""
    a: str
    b: str
    frame: int
    distance: float


@dataclass
class Link:
    """Verbindung vom Ende eines Spielers zum Anfang eines anderen."""
    end: str
    start: str
    cost: float
    margin: float


def _cut(p: Piece, at: Sequence[int], teams: Sequence[str] | None = None) -> list[Piece]:
    """Teilt p vor den Bildern at; Namen {id}/{k}; teams: Mannschaft je Teil (sonst die von p)."""
    edges = [p.start] + sorted(at) + [p.end + 1]
    out = []
    for k, (lo, hi) in enumerate(zip(edges, edges[1:])):
        frames = {f: r for f, r in p.frames.items() if lo <= f < hi}
        if frames:
            out.append(Piece(f"{p.id}/{len(out)}", teams[k] if teams else p.team, p.keeper, frames))
    return out


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Abschnitte (erster, letzter Index) mit mask wahr."""
    out, start = [], None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        if not m and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(mask) - 1))
    return out


def contacts(pieces: Sequence[Piece], fps: float) -> list[Contact]:
    """Kontakte zwischen Stücken derselben Mannschaft (Schiedsrichter ausgenommen)."""
    out = []
    for i, a in enumerate(pieces):
        for b in pieces[i + 1:]:
            if a.team != b.team or a.team in NO_LINK_TEAMS:
                continue
            common = sorted(set(a.frames) & set(b.frames))
            if not common:
                continue
            d = np.array([np.linalg.norm(a.at(f) - b.at(f)) for f in common])
            merged: list[list[int]] = []
            for lo, hi in _runs(d < CONTACT_M):
                if merged and common[lo] - common[merged[-1][1]] < CONTACT_JOIN_S * fps:
                    merged[-1][1] = hi
                else:
                    merged.append([lo, hi])
            for lo, hi in merged:
                k = lo + int(np.argmin(d[lo:hi + 1]))
                out.append(Contact(a.id, b.id, common[k], float(d[k])))
    return sorted(out, key=lambda c: c.frame)


def has_company(p: Piece, pieces: Sequence[Piece], frame: int, fps: float) -> bool:
    """Ist um das Bild herum (± SWAP_WINDOW_S) eine andere Spur näher als SWAP_NEAR_M bei p? Ein Wechsel der Spur
    auf eine andere Person braucht eine zweite Person in der Nähe."""
    w = int(SWAP_WINDOW_S * fps)
    for o in pieces:
        if o is p:
            continue
        for g in range(frame - w, frame + w + 1):
            if g in p.frames and g in o.frames and np.linalg.norm(o.at(g) - p.at(g)) < SWAP_NEAR_M:
                return True
    return False


def split_by_colour(pieces: Sequence[Piece], colours: Mapping[str, int], fps: float) -> list[Piece]:
    """Trennt Stücke an Abschnitten fremder Trikotfarbe (Farbe je Erkennung in Zeile r[2]); colours: Farbklasse
    je Mannschaft. Torhüter (eigene Farbe) bleiben ganz. Fremde Farbe ohne eine andere Spur in der Nähe (has_company)
    ist ein Fehler der Farberkennung und trennt nicht."""
    team_of = {c: t for t, c in colours.items()}
    half = max(1, int(COLOUR_SMOOTH_S * fps))
    kept, foreign = [], []
    for p in pieces:
        want = colours.get(p.team)
        if p.keeper or want is None:
            kept.append(p)
            continue
        fs = sorted(p.frames)
        col = np.array([int(p.frames[f][2]) for f in fs])
        smooth = np.array([np.bincount(col[max(0, i - half):i + half + 1] + 1).argmax() - 1 for i in range(len(col))])
        stretches = [(lo, hi) for lo, hi in _runs((smooth != want) & np.isin(smooth, list(team_of)))
                     if (fs[hi] - fs[lo]) / fps >= MIN_FOREIGN_S and has_company(p, pieces, fs[lo], fps)]
        if not stretches:
            kept.append(p)
            continue
        at, teams = [], [p.team]
        for lo, hi in stretches:
            if fs[lo] > p.start:
                at.append(fs[lo])
            else:
                teams.pop()
            teams.append(team_of[int(np.bincount(smooth[lo:hi + 1] + 1).argmax() - 1)])
            if hi + 1 < len(fs):
                at.append(fs[hi + 1])
                teams.append(p.team)
        for part in _cut(p, at, teams):
            (kept if part.team == p.team else foreign).append(part)
    out = list(kept)
    for q in foreign:   # schon von einer Spur der anderen Mannschaft erfasst? Dann doppelt.
        others = [o for o in kept if o.team == q.team]
        near = sum(1 for f in q.frames
                   if any(f in o.frames and np.linalg.norm(o.at(f) - q.at(f)) < CONTACT_M for o in others))
        if near < COVERED * len(q.frames):
            out.append(q)
    return out


def split_by_numbers(pieces: Sequence[Piece], found: Sequence[Contact], readings: Sequence[jersey_identity.Reading],
                     fps: float, squad: Mapping[str, frozenset[int]] | None = None) -> list[Piece]:
    """Trennt ein Stück an einem Kontakt, wenn die Lesungen davor und danach (bis zum vorigen und nächsten
    Kontakt) verschiedene sichere Nummern ergeben (jersey_identity.vote)."""
    by_piece: dict[str, list[jersey_identity.Reading]] = {}
    for r in readings:
        by_piece.setdefault(r.track, []).append(r)
    at: dict[str, list[int]] = {}
    for c in found:
        at.setdefault(c.a, []).append(c.frame)
        at.setdefault(c.b, []).append(c.frame)
    out = []
    for p in pieces:
        frames = sorted(set(at.get(p.id, [])))
        mine = by_piece.get(p.id, [])
        cuts, lo = [], p.start
        for i, f in enumerate(frames):
            hi = frames[i + 1] if i + 1 < len(frames) else p.end + 1

            def number(a: int, b: int) -> int | None:
                part = [r for r in mine if a <= r.frame < b]
                v = jersey_identity.vote(part, {p.id: p.team}, fps, squad).get(p.id) if part else None
                return v.number if v is not None else None
            before, after = number(lo, f), number(f, hi)
            if before is not None and after is not None and before != after:
                cuts.append(f)
                lo = f
        out.extend(_cut(p, cuts) if cuts else [p])
    return out


def heading(p: Piece, fps: float) -> np.ndarray:
    """Tempo (m/s) am Ende des Stücks, aus den letzten HEADING_S."""
    end = p.end
    first = min((f for f in p.frames if f >= end - HEADING_S * fps), default=end)
    if first == end:
        return np.zeros(2)
    return (p.at(end) - p.at(first)) / ((end - first) / fps)


def path_cost(a: Piece, b: Piece, fps: float) -> float:
    """Abstand des Anfangs von b zur erwarteten Lage in Unsicherheiten; inf, wenn unerreichbar."""
    gap = (b.start - a.end) / fps
    if gap <= 0:   # kurze Übergabe: Lage beider zur selben Zeit vergleichen
        f = min(a.frames, key=lambda f: abs(f - b.start))
        return float(np.linalg.norm(a.at(f) - b.at(b.start))) / POSITION_NOISE
    d_end = float(np.linalg.norm(b.at(b.start) - a.at(a.end)))
    if d_end > MERGE_SPEED * gap + POSITION_NOISE:
        return math.inf
    expected = a.at(a.end) + heading(a, fps) * min(gap, PREDICT_S)
    sigma = POSITION_NOISE + SPREAD * gap
    # Der Logarithmus ist der Preis der Unsicherheit: Je länger die Lücke, desto breiter die erwartete Lage und desto
    # weniger Gewicht trägt jeder einzelne Anfang darin. Ohne ihn war jeder späte, ferne Anfang „erreichbar“ und
    # billiger als einer, der ein Bild später am selben Ort beginnt, und sperrte über den Verhältnistest die richtige
    # Verbindung (Szene 705, Bild 122/123).
    return float(np.linalg.norm(b.at(b.start) - expected)) / sigma + math.log(sigma / POSITION_NOISE)


def look_cost(look_a: Look | None, look_b: Look | None) -> float:
    if look_a is None or look_b is None:
        return 0.0
    cost = 0.0
    if look_a.sure and look_b.sure:
        cost += LOOK_WEIGHT * (1.0 - float(np.dot(look_a.mean, look_b.mean)))
    if math.isfinite(look_a.height_m) and math.isfinite(look_b.height_m):
        cost += HEIGHT_WEIGHT * abs(look_a.height_m - look_b.height_m) / ((look_a.height_m + look_b.height_m) / 2)
    return cost


def link_cost(a: Piece, b: Piece, look_a: Look | None, look_b: Look | None, fps: float) -> float:
    """Kosten, das Ende von a mit dem Anfang von b zu verbinden (ohne Nummern); inf bei einem Verbot."""
    if a.team != b.team or a.keeper != b.keeper or a.team in NO_LINK_TEAMS:
        return math.inf
    if len(set(a.frames) & set(b.frames)) > OVERLAP_S * fps or b.start < a.end - OVERLAP_S * fps:
        return math.inf   # gleichzeitig zu sehen, oder b beginnt mitten in a (auch in einer Lücke von a)
    return BASE_COST + path_cost(a, b, fps) + look_cost(look_a, look_b)


def _chain_number(chain: Sequence[str], numbers: Mapping[str, int | None]) -> int | None:
    found = {numbers[p] for p in chain if numbers.get(p) is not None}
    return found.pop() if len(found) == 1 else None


def link(pieces: Sequence[Piece], looks: Mapping[str, Look], numbers: Mapping[str, int | None],
         fps: float, log: list[Link] | None = None) -> list[list[str]]:
    """Spieler als Listen von Stück-Namen (zeitlich geordnet). numbers: sichere Nummer je Stück (oder None).

    Gierig nach Kosten: Ein Ende wird mit einem Anfang verbunden, wenn die Kosten unter MAX_COST liegen und der
    zweitbeste Kandidat für dieses Ende wie für diesen Anfang mindestens MIN_MARGIN-mal so teuer ist.
    ponytail: gierig statt globaler Zuordnung (Netzfluss mit minimalen Kosten); reicht für 5–8 Lücken je
    Szene, bei vielen gleichzeitigen Lücken wäre die globale Lösung besser."""
    by_id = {p.id: p for p in pieces}
    chains = {p.id: [p.id] for p in pieces}   # Spieler, benannt nach seinem ersten Stück

    def cost(x: str, y: str) -> float:
        first, last = chains[y][0], chains[x][-1]
        c = link_cost(by_id[last], by_id[first], looks.get(last), looks.get(first), fps)
        nx, ny = _chain_number(chains[x], numbers), _chain_number(chains[y], numbers)
        if nx is not None and ny is not None:
            c = c * NUMBER_FACTOR if nx == ny else math.inf
        return c

    while True:
        names = list(chains)
        table = {(x, y): cost(x, y) for x in names for y in names if x != y}
        table = {k: v for k, v in table.items() if math.isfinite(v)}
        best = None
        for (x, y), c in sorted(table.items(), key=lambda kv: kv[1]):
            if c > MAX_COST:
                break
            rivals = [v for (x2, y2), v in table.items() if (x2 == x) != (y2 == y)]
            second = min(rivals, default=math.inf)
            if second >= MIN_MARGIN * c:
                best = Link(chains[x][-1], chains[y][0], c, second / c)
                break
        if best is None:
            break
        x = next(k for k, v in chains.items() if v[-1] == best.end)
        y = next(k for k, v in chains.items() if v[0] == best.start)
        chains[x] = chains[x] + chains.pop(y)
        if log is not None:
            log.append(best)
    return list(chains.values())


def open_ends(chains: Sequence[Sequence[str]], pieces: Sequence[Piece], looks: Mapping[str, Look],
              numbers: Mapping[str, int | None], fps: float) -> list[tuple[str, list[tuple[float, str]]]]:
    """Zum Prüfen: je Spielerende die zwei günstigsten Anfänge anderer Spieler (Kosten, Stück)."""
    by_id = {p.id: p for p in pieces}
    out = []
    for x in chains:
        last = by_id[x[-1]]
        found = []
        for y in chains:
            if y is x:
                continue
            first = by_id[y[0]]
            c = link_cost(last, first, looks.get(last.id), looks.get(first.id), fps)
            nx, ny = _chain_number(x, numbers), _chain_number(y, numbers)
            if nx is not None and ny is not None:
                c = c * NUMBER_FACTOR if nx == ny else math.inf
            if math.isfinite(c):
                found.append((c, first.id))
        if found:
            out.append((last.id, sorted(found)[:2]))
    return out


def main(argv: list[str] | None = None) -> None:
    """Prüfausgabe: Kontakte, getrennte Stücke und Verbindungen einer Szene (Ablauf wie tools/own_scene.py)."""
    import argparse
    import json
    import jersey_reader
    import own_scene
    import veo_camera
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("video")
    ap.add_argument("det")
    ap.add_argument("camera")
    args = ap.parse_args(argv)
    det = json.loads(Path(args.det).read_text())
    cam = veo_camera.load(args.camera)
    identities = own_scene.own_identities(det, cam, len(det["frames"]), args.video)
    scene = jersey_reader.read_scene(args.video, args.det) if jersey_reader.MODEL.exists() else None
    report: list[str] = []
    players = own_scene.split_and_link(identities, args.video, args.det, cam, det["fps"], scene, report=report)
    print("\n".join(report))
    print(f"-> {len(players)} Spieler")


if __name__ == "__main__":
    main()
