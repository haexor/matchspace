#!/usr/bin/env python3
"""Eine Identität je Spieler: Spurstücke derselben Person vorsichtig verbinden, ohne Fremddaten.

Reine Logik ohne Datei-, Video- oder Netzzugriff (außer der Kommandozeile):
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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

MERGE_SPEED = 8.0       # m/s: schneller überbrückt kein Spieler eine Lücke (wie jersey_identity)
POSITION_NOISE = 1.5    # m: Messrauschen der Lage am Boden
OVERLAP_S = 0.5         # s: so lange dürfen zwei Stücke einer Person gleichzeitig zu sehen sein (Übergabe)
SPREAD = 2.0            # m/s: so schnell wächst die Unsicherheit der erwarteten Lage mit der Lücke
HEADING_S = 0.5         # s: Laufrichtung aus dem Ende des Stücks
PREDICT_S = 2.0         # s: höchstens so lange wird die Laufrichtung fortgeschrieben (danach bremst jeder)
BASE_COST = 0.5         # Grundkosten jeder Verbindung: Kosten nahe null machten den Verhältnistest beliebig
MAX_COST = 2.5          # teurer wird nie verbunden, auch ohne Konkurrenz
MIN_MARGIN = 2.0        # der zweitbeste Kandidat muss mindestens so viel teurer sein
LOOK_WEIGHT = 5.0       # Gewicht von 1 − Kosinus der Bildmerkmale
HEIGHT_WEIGHT = 3.0     # Gewicht des relativen Größenunterschieds
NUMBER_FACTOR = 0.1     # dieselbe sichere Nummer: Kosten mal diesem Faktor
MIN_LOOK = 8            # Erkennungen, ab denen das Aussehen eines Stücks zählt
NO_LINK_TEAMS = ("referee",)


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
class Link:
    """Verbindung vom Ende eines Spielers zum Anfang eines anderen."""
    end: str
    start: str
    cost: float
    margin: float


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
    return float(np.linalg.norm(b.at(b.start) - expected)) / (POSITION_NOISE + SPREAD * gap)


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
    import argparse
    import json
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    import jersey_identity
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
    fps = det["fps"]
    identities = own_scene.own_identities(det, cam, len(det["frames"]), args.video)
    keys = {f"{key[0]}-{key[1]}": key for key in identities}
    tracks = {name: identities[key][2] for name, key in keys.items()}
    pieces = [Piece(name, key[0], identities[key][1], tracks[name]) for name, key in keys.items()]
    numbers: dict[str, int | None] = {}
    if jersey_reader.MODEL.exists():
        scene = jersey_reader.read_scene(args.video, args.det)
        votes = jersey_identity.vote(jersey_reader.readings_for_tracks(scene, tracks), {n: k[0] for n, k in keys.items()}, fps)
        numbers = {n: v.number for n, v in votes.items()}
    looks = own_scene._piece_looks(args.video, args.det, tracks, cam)
    log: list[Link] = []
    chains = link(pieces, looks, numbers, fps, log)
    print(f"{len(pieces)} Spurstücke, {sum(1 for n in numbers.values() if n is not None)} mit sicherer Nummer, "
          f"Aussehen {'ja' if looks else 'nein'}")
    for item in log:
        print(f"verbunden   {item.end:16s} -> {item.start:16s} Kosten {item.cost:5.2f}, Zweitbester {item.margin:4.1f}-mal so teuer")
    for end, best in open_ends(chains, pieces, looks, numbers, fps):
        if best[0][0] <= MAX_COST * MIN_MARGIN:
            rival = f", Zweitbester {best[1][1]} {best[1][0]:.2f}" if len(best) > 1 else ""
            print(f"getrennt gelassen {end:16s}: bester Anfang {best[0][1]} Kosten {best[0][0]:.2f}{rival}")
    print(f"-> {len(chains)} Spieler")


if __name__ == "__main__":
    main()
