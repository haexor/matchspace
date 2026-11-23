#!/usr/bin/env python3
"""Strittige Stellen einer Szene finden und für das Markierwerkzeug ablegen ({det}.reference.json).

Gründe (specs/003-eigene-referenz/research.md R1):
  - Verdeckung: Boxen zweier Spieler derselben Linse überlappen um mehr als OCCLUDE der kleineren Box;
  - Spurende oder -beginn mitten auf dem Platz (mehr als INSIDE_M innerhalb der Linien, nicht am Szenenrand);
  - Trennung oder Verbindung der Auswertung (Feature 002);
  - Nummer prüfen (jeder Spieler mit Nummer, an seiner besten Rückenlesung) und Nummer unsicher;
  - Veo sieht eine andere Person (nur mit --veo).
Dazu Kontrollstellen ohne Grund, zufällig mit festem Startwert. Stellen mit gemeinsamen Spielern, die höchstens
MERGE_S auseinanderliegen, werden eine, solange sie nicht länger als LONGEST_S wird. Vorhandene Antworten bleiben und werden über ihre Anker wiedergefunden.

Aufruf:
    .venv/bin/python tools/review_spots.py DETEKTIONEN.json KAMERA.json [--veo VEO_ORDNER VEO_ALIGN.json START_S] [--kontrolle 5]
"""
import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import reference as ref  # noqa: E402

OCCLUDE = 0.3        # Anteil der kleineren Box, ab dem eine Überlappung als Verdeckung zählt
GAP_S = 0.5          # s: kürzere Pausen einer Verdeckung gehören dazu
WINDOW_S = 1.5       # s: Ausschnitt vor und nach der Stelle
MERGE_S = 1.0        # s: Stellen mit gemeinsamen Spielern, die höchstens so weit auseinanderliegen, sind eine
INSIDE_M = 1.0       # m: so weit innerhalb der Linien muss ein Spurende liegen
NEAR_M = 5.0         # m: Spieler so nah an einem Spurende sind beteiligt
LONGEST_S = 6.0      # s: Stellen wachsen beim Zusammenfassen höchstens auf diese Länge
MAX_PLAYERS = 3      # und auf so viele Beteiligte; mehr überblickt man nicht, größere Gedränge werden mehrere Fragen
SPLIT_FROM = 3       # Wären an einem Spurende mehr als so viele Spieler beteiligt, wird je Spieler eine Frage daraus
CONTROL_AWAY_S = 2.0  # s: Kontrollstellen so weit weg von Stellen desselben Spielers
CROP_MIN = 400       # px: kleinste Breite des Bildausschnitts (Spieler sind nur rund 25 × 60 px groß)
CROP_PAD = 60        # px: Rand um die Boxen
CROP_ASPECT = 1.6    # Breite : Höhe des Ausschnitts, immer gleich, damit die Ansicht groß und ruhig bleibt
LENS_SIZE = (2048, 1024)
PRIORITY = {"split": 3.0, "link": 3.0, "veo": 3.0, "occlusion": 2.0, "end": 2.0, "start": 2.0,
            "number-unsure": 1.5, "number": 1.0, "control": 0.5}
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _overlap(a: Sequence[float], b: Sequence[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return ix * iy / small if small > 0 else 0.0


def _runs(frames: Sequence[int], gap: int) -> list[tuple[int, int]]:
    out = []
    for f in sorted(frames):
        if out and f - out[-1][1] <= gap:
            out[-1][1] = f
        else:
            out.append([f, f])
    return [tuple(r) for r in out]


class _Scene:
    """Hilfsdaten: Erkennungen je Spieler, Spieler je Bild."""

    def __init__(self, identity: Mapping, boxes: Mapping, ground: Mapping, n_frames: int, lens_size=LENS_SIZE):
        self.fps = identity["fps"]
        self.lens_size = tuple(lens_size)
        self.n = n_frames
        self.boxes, self.ground = boxes, ground
        self.dets = {name: [tuple(d) for d in p["detections"]] for name, p in identity["players"].items()}
        self.team = {name: p["team"] for name, p in identity["players"].items()}
        self.at: dict[int, list[tuple[str, tuple]]] = {}
        for name, dets in self.dets.items():
            for d in dets:
                self.at.setdefault(d[0], []).append((name, d))

    def near(self, frame: int, where, exclude: str) -> list[str]:
        """Wer an einem Spurende übernommen haben könnte: Spieler, deren eigene Spur im Ausschnitt (± WINDOW_S)
        näher als NEAR_M beginnt oder endet, der nächste zuerst. Wer einfach weiterläuft, gehört nicht dazu; ein
        Tausch mit ihm wäre eine Verdeckung und damit eine eigene Stelle."""
        found, w = {}, int(WINDOW_S * self.fps)
        for name, dets in self.dets.items():
            for d in (dets[0], dets[-1]):
                dist = float(np.hypot(*(np.asarray(self.ground[d]) - where)))
                if name != exclude and abs(d[0] - frame) <= w and dist < NEAR_M:
                    found[name] = min(dist, found.get(name, dist))
        return sorted(found, key=lambda n: (found[n], n))


def _crop(shown: Sequence[float], lens_size: Sequence[int]) -> list[int]:
    """Bildausschnitt [x, y, Breite, Höhe] um die Boxen: festes Seitenverhältnis, mit Rand, innerhalb des Linsenbilds."""
    x1, y1, x2, y2 = shown
    lw, lh = lens_size
    cw = max(CROP_MIN, x2 - x1 + 2 * CROP_PAD, (y2 - y1 + 2 * CROP_PAD) * CROP_ASPECT)
    cw = min(cw, lw, lh * CROP_ASPECT)
    ch = cw / CROP_ASPECT
    x = min(max((x1 + x2 - cw) / 2, 0), lw - cw)
    y = min(max((y1 + y2 - ch) / 2, 0), lh - ch)
    return [round(x), round(y), round(cw), round(ch)]


def _spot(sc: _Scene, kinds: Sequence[str], frame: int, lo: int, hi: int, players: set[str], number=None) -> ref.Spot | None:
    w = int(WINDOW_S * sc.fps)
    start, end = max(0, lo - w), min(sc.n - 1, hi + w)
    window = {name: [d for d in sc.dets[name] if start <= d[0] <= end] for name in sorted(players)}
    seen = [d[1] for dets in window.values() for d in dets]
    if not seen:
        return None
    lens = Counter(seen).most_common(1)[0][0]   # gezeigt wird eine Linse; Boxen der anderen fehlen dort
    before, after, letters = [], [], {}
    for name, dets in window.items():
        b = [d for d in dets if d[0] < frame]
        a = [d for d in dets if d[0] >= frame]
        if not b and not a:
            continue
        letter = letters.setdefault(name, LETTERS[len(letters) % len(LETTERS)])
        boxes = {d[0]: list(sc.boxes[d]) for d in dets if d[1] == lens}
        if b:
            before.append(ref.Participant(name, letter, [*b[-1], *sc.boxes[b[-1]]], boxes))
        if a:
            after.append(ref.Participant(name, letter, [*a[0], *sc.boxes[a[0]]], boxes))
    shown = [b for p in before + after for b in p.boxes.values()]
    if not shown:
        return None
    x1, y1 = min(b[0] for b in shown), min(b[1] for b in shown)
    x2, y2 = max(b[2] for b in shown), max(b[3] for b in shown)
    crop = _crop((x1, y1, x2, y2), sc.lens_size)
    before_letters = {p.letter for p in before}
    proposal = {p.letter: (p.letter if p.letter in before_letters else None) for p in after}
    key = json.dumps([frame, sorted(p.anchor[:3] for p in before), sorted(p.anchor[:3] for p in after), sorted(kinds)])
    sid = hashlib.sha1(key.encode()).hexdigest()[:12]
    priority = max(PRIORITY[k] for k in kinds) + (0.5 if len({sc.team[p] for p in players}) > 1 else 0.0)
    return ref.Spot(sid, sorted(set(kinds)), frame, start, end, int(lens), crop, before, after, proposal, priority, number)


def find_spots(identity: Mapping, boxes: Mapping, ground: Mapping, pitch: tuple[float, float], n_frames: int,
               best_back: Mapping[str, int] | None = None, unsure: Mapping[str, int] | None = None,
               veo: Sequence[tuple[int, str]] = (), lens_size: Sequence[int] = LENS_SIZE) -> list[ref.Spot]:
    """Strittige Stellen, zeitlich geordnet. boxes, ground: (Bild, Linse, Box) -> Box im Bild bzw. Lage am Boden;
    best_back: Spieler mit Nummer -> Bild der besten Rückenlesung; unsure: Spieler -> Bild; veo: (Bild, Spieler)."""
    sc = _Scene(identity, boxes, ground, n_frames, lens_size)
    fps, events = sc.fps, []                       # [lo, hi, Gründe, Spieler]
    pairs: dict[tuple[str, str], list[int]] = {}
    for f, here in sc.at.items():
        for i, (a, da) in enumerate(here):
            for b, db in here[i + 1:]:
                if da[1] == db[1] and a != b and _overlap(boxes[da], boxes[db]) > OCCLUDE:
                    pairs.setdefault(tuple(sorted((a, b))), []).append(f)
    for pair, frames in pairs.items():
        for lo, hi in _runs(frames, int(GAP_S * fps)):
            events.append([lo, hi, {"occlusion"}, set(pair)])
    half_l, half_w = pitch[0] / 2 - INSIDE_M, pitch[1] / 2 - INSIDE_M
    edge = int(0.5 * fps)
    for name, dets in sc.dets.items():
        for kind, d in (("start", dets[0]), ("end", dets[-1])):
            x, y = sc.ground[d]
            if abs(x) > half_l or abs(y) > half_w or d[0] < edge or d[0] > n_frames - 1 - edge:
                continue
            f = d[0] if kind == "start" else d[0] + 1
            others = sc.near(d[0], np.asarray((x, y)), name)
            groups = [others] if 1 + len(others) <= SPLIT_FROM else [[o] for o in others]   # Gedränge: Paare
            events += [[f, f, {kind}, {name, *g}] for g in groups]
    for e in identity.get("events", []):
        events.append([e["frame"], e["frame"], {e["kind"]}, {p for p in e.get("players", []) if p in sc.dets}])
    for f, name in veo:
        events.append([f, f, {"veo"}, {name}])
    merged: list[list] = []                        # [lo, hi, Gründe, Spieler, Mitte des ersten Ereignisses]
    for e in sorted(events, key=lambda e: (e[0] + e[1]) / 2):
        mid = (e[0] + e[1]) / 2
        for m in merged:
            if ((m[3] & e[3]) and e[0] <= m[1] + MERGE_S * fps and m[0] <= e[1] + MERGE_S * fps
                    and max(m[1], e[1]) - min(m[0], e[0]) <= LONGEST_S * fps and len(m[3] | e[3]) <= MAX_PLAYERS):
                m[0], m[1] = min(m[0], e[0]), max(m[1], e[1])
                m[2] |= e[2]
                m[3] |= e[3]
                break
        else:
            merged.append([e[0], e[1], set(e[2]), set(e[3]), mid])
    spots = [_spot(sc, sorted(m[2]), (m[0] + m[1] + 1) // 2, m[0], m[1], m[3]) for m in merged if m[3]]
    # Ohne Beteiligte vorher oder nachher gibt es nichts zuzuordnen (eine Spur endet, niemand übernimmt)
    spots = [s for s in spots if s is not None and s.before and s.after]
    players = identity["players"]
    for name, f in (best_back or {}).items():
        if players.get(name, {}).get("number") is not None:
            spots.append(_spot(sc, ["number"], f, f, f, {name}, players[name]["number"]))
    for name, f in (unsure or {}).items():
        spots.append(_spot(sc, ["number-unsure"], f, f, f, {name}))
    return sorted((s for s in spots if s is not None), key=lambda s: (s.frame, s.id))


def control_spots(identity: Mapping, boxes: Mapping, spots: Sequence[ref.Spot], n_frames: int, seed: int,
                  n: int = 5, lens_size: Sequence[int] = LENS_SIZE) -> list[ref.Spot]:
    """n zufällige Stellen ohne Grund: ein Spieler, der 1,5 s vorher und nachher zu sehen ist, nicht nahe an einer
    Stelle mit ihm. Mit demselben Startwert dieselben Stellen."""
    sc = _Scene(identity, boxes, {}, n_frames, lens_size)
    w, away = int(WINDOW_S * sc.fps), CONTROL_AWAY_S * sc.fps
    busy: dict[str, list[int]] = {}
    for s in spots:
        for p in s.before + s.after:
            busy.setdefault(p.player, []).append(s.frame)
    rng = random.Random(seed)
    names = sorted(sc.dets)
    out, used = [], set()
    for _ in range(2000):
        if len(out) >= n or not names:
            break
        name = rng.choice(names)
        frames = [d[0] for d in sc.dets[name]]
        f = rng.randrange(w, max(w + 1, n_frames - w))
        if (name, f // w) in used or any(abs(f - g) <= away for g in busy.get(name, [])):
            continue
        if not any(f - w <= g < f for g in frames) or not any(f <= g <= f + w for g in frames):
            continue
        spot = _spot(sc, ["control"], f, f, f, {name})
        if spot is not None and spot.before and spot.after:
            used.add((name, f // w))
            busy.setdefault(name, []).append(f)
            out.append(spot)
    return out


def update(path: Path, scene: str, identity: Mapping, spots: list[ref.Spot], seed: int) -> tuple[int, list[ref.Answer]]:
    """Schreibt oder ergänzt die Referenzdatei; vorhandene Antworten werden wiedergefunden. Rückgabe (offen, verwaist)."""
    answers, orphaned = [], []
    if path.exists():
        old_spots, old_answers, seed = ref.from_json(json.loads(path.read_text()))
        answers, orphaned = ref.refind(old_spots, old_answers, spots)
    data = ref.to_json(scene, identity.get("stamp", ""), spots, answers, seed)
    tmp = Path(f"{path}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False) + "\n")
    tmp.replace(path)
    decided = {a.spot for a in answers if not a.repeat}
    return sum(1 for s in spots if s.id not in decided), orphaned


def load_scene(det_path: str, camera_path: str, identity: Mapping):
    """Boxen und Bodenlagen (Mitte der Boxunterkante) aller Erkennungen der Zuordnung."""
    import veo_camera
    det = json.loads(Path(det_path).read_text())
    cam = veo_camera.load(camera_path)
    boxes, ground = {}, {}
    for p in identity["players"].values():
        for f, lens, box in p["detections"]:
            boxes[(f, lens, box)] = det["frames"][f][veo_camera.LENSES[lens]][box][:4]
    keys = list(boxes)
    for li, lens in enumerate(veo_camera.LENSES):
        mine = [k for k in keys if k[1] == li]
        if mine:
            b = np.array([boxes[k] for k in mine], float)
            g, _ = veo_camera.to_ground(cam, lens, np.column_stack([(b[:, 0] + b[:, 2]) / 2, b[:, 3]]))
            ground.update({k: tuple(v) for k, v in zip(mine, g)})
    return det, cam, boxes, ground


def number_frames(det_path: str, identity: Mapping) -> tuple[dict, dict]:
    """Bild der besten Rückenlesung je Spieler mit Nummer, und je Spieler mit unsicherer Nummer."""
    import jersey_reader
    cache = Path(f"{det_path}.numbers.npz")
    if not cache.exists():
        return {}, {}
    c = np.load(cache)
    owner = {tuple(d): name for name, p in identity["players"].items() for d in p["detections"]}
    best, unsure = {}, {}
    candidates = {}
    for name, ranked in identity.get("numbers", {}).items():
        number, confidence = ranked[0]
        if identity["players"].get(name, {}).get("number") is not None:
            candidates[name] = (number, best)
        elif 0.5 <= confidence < 0.9:
            candidates[name] = (number, unsure)
    score: dict[str, float] = {}
    for f, lens, box, probs, height in zip(c["frame"], c["lens"], c["box"], c["probs"], c["height"]):
        name = owner.get((int(f), int(lens), int(box)))
        if name in candidates:
            number, target = candidates[name]
            s = float(probs[number]) * jersey_reader.reading_weight(float(height))
            if s > score.get(name, 0.0):
                score[name], target[name] = s, int(f)
    return best, unsure


def main(argv: list[str] | None = None) -> None:
    import jersey_reader
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("det")
    ap.add_argument("camera")
    ap.add_argument("--veo", nargs=3, metavar=("VEO_ORDNER", "VEO_ALIGN", "START_S"))
    ap.add_argument("--kontrolle", type=int, default=5)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args(argv)
    path = jersey_reader.check_private_dir(f"{args.det}.reference.json")
    identity = json.loads(Path(f"{args.det}.identity.json").read_text())
    det, cam, boxes, ground = load_scene(args.det, args.camera, identity)
    best, unsure = number_frames(args.det, identity)
    veo = veo_changes(identity, ground, det, *args.veo) if args.veo else []
    n = len(det["frames"])
    spots = find_spots(identity, boxes, ground, (cam["pitch"]["length"], cam["pitch"]["width"]), n, best, unsure, veo,
                       det.get("lensSize", LENS_SIZE))
    spots += control_spots(identity, boxes, spots, n, args.seed, args.kontrolle, det.get("lensSize", LENS_SIZE))
    spots.sort(key=lambda s: (s.frame, s.id))
    open_, orphaned = update(path, Path(args.det).name.split(".")[0], identity, spots, args.seed)
    kinds = Counter(k for s in spots for k in s.kinds)
    print(f"{len(spots)} Stellen ({', '.join(f'{k} {v}' for k, v in sorted(kinds.items()))}); offen {open_}"
          + (f"; verwaiste Antworten {len(orphaned)}" if orphaned else ""))
    print(f"-> {path}")


def veo_changes(identity: Mapping, ground: Mapping, det: Mapping, veo_dir: str, align: str, start: str) -> list[tuple[int, str]]:
    """Zweite Meinung: Bilder, an denen laut Veo ein Spieler für mindestens 1 s die Person wechselt."""
    import jersey_eval
    import track_players
    at = jersey_eval.reference(veo_dir, align)
    truth = [at(float(start) + fr["t"]) for fr in det["frames"]]
    positions = {name: {d[0]: np.asarray(ground[tuple(d)]) for d in p["detections"]} for name, p in identity["players"].items()}
    matched = track_players.match_reference(positions, truth)
    fps = identity["fps"]
    out = []
    for name, frames in matched.items():
        runs: list[list] = []
        for f in sorted(frames):
            r = frames[f]
            if r is None:
                continue
            if runs and runs[-1][0] == r:
                runs[-1][2] = f
            else:
                runs.append([r, f, f])
        stable = [r for r in runs if r[2] - r[1] >= fps]
        out += [(b[1], name) for a, b in zip(stable, stable[1:]) if a[0] != b[0]]
    return out


if __name__ == "__main__":
    main()
