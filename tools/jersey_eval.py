#!/usr/bin/env python3
"""Nur zum Prüfen: Wie gut sind Identität und Rückennummern einer Szene? Gemessen gegen die eigene Referenz.

Die Wahrheit ist die Zuordnung der Auswertung ({det}.identity.json), korrigiert an den strittigen Stellen, die der
Nutzer im Markierwerkzeug entschieden hat ({det}.reference.json; tools/review_spots.py, tools/reference.py).
Gemessen wird je Erkennung, nicht über die Lage der Szene (specs/003-eigene-referenz/contracts/eval-report.md):
  - Identitäten je Person (in wie viele Spieler zerfällt sie), falsch zugeordnete Zeit, Personenwechsel ≥ 1 s;
  - Nummern: richtig, falsch, unbekannt, für Personen mit vom Nutzer angegebener Nummer;
  - Abdeckung: offene, unklare und verwaiste Stellen, Schätzung aus den Kontrollstellen, Wiederholungen.
Veo ist nur zweite Meinung (--veo): dieselben Kennzahlen gegen Veo, Abgleich über die rohen Bodenpunkte (ohne
Versatz), und eine Liste der Stellen, an denen Veo und die Referenz verschiedene Wechsel sehen. Schreibt nichts in
die Szene.

Aufruf:
    .venv/bin/python tools/jersey_eval.py DETEKTIONEN.json KAMERA.json [--veo VEO_ORDNER VEO_ALIGN.json START_S] [--bericht BERICHT.json] [--lesezeit S]
"""
import argparse
import json
import sys
from array import array
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import jersey_reader  # noqa: E402
import reference as ref  # noqa: E402

TEAMS = ("own", "opponent")
NEAR_SWITCH_S = 1.0   # s: Wechsel laut Referenz und laut Veo, die so nah beieinander liegen, sind derselbe


def duplicate_frames(present: Mapping[str, set[int]], numbers: Mapping[str, int | None],
                     teams: Mapping[str, str]) -> int:
    """Bilder, in denen zwei Spieler einer Mannschaft dieselbe Nummer tragen."""
    holders: dict[tuple[str, int], list[str]] = {}
    for name, number in numbers.items():
        if number is not None:
            holders.setdefault((teams[name], number), []).append(name)
    bad: set[int] = set()
    for names in holders.values():
        for a in range(len(names)):
            for b in range(a + 1, len(names)):
                bad |= present[names[a]] & present[names[b]]
    return len(bad)


def _references(frames: Mapping[int, tuple | None]) -> list[tuple]:
    return [ref for _, ref in sorted(frames.items()) if ref is not None]


def wrong_time_share(matched: Mapping[str, Mapping[int, tuple | None]]) -> float:
    """Anteil der zugeordneten Spieler-Bilder, deren Referenz nicht die Hauptperson des Spielers ist."""
    total = wrong = 0
    for frames in matched.values():
        refs = _references(frames)
        if refs:
            total += len(refs)
            wrong += len(refs) - Counter(refs).most_common(1)[0][1]
    return wrong / total if total else 0.0


def switches(matched: Mapping[str, Mapping[int, tuple | None]], fps: float) -> int:
    """Wechsel der Referenzperson innerhalb eines Spielers; Abschnitte unter 1 s zählen nicht."""
    count = 0
    for frames in matched.values():
        runs: list[list] = []
        for ref in _references(frames):
            if runs and runs[-1][0] == ref:
                runs[-1][1] += 1
            else:
                runs.append([ref, 1])
        stable = [ref for ref, n in runs if n >= fps]
        count += sum(1 for a, b in zip(stable, stable[1:]) if a != b)
    return count


def load_scene(scene_dir: Path) -> tuple[dict, np.ndarray]:
    meta = json.loads((scene_dir / "meta.json").read_text())
    tr = meta["tracks"]
    data = array("h")
    with open(scene_dir / tr["file"], "rb") as f:
        data.frombytes(f.read())
    xy = np.array(data, float).reshape(meta["frames"], len(meta["entities"]), 3)[:, :, :2]
    return meta, np.where(xy == tr["missing"], np.nan, xy * tr["scale"])


def reference(veo_dir: str, align_path: str):
    import veo_tracks   # Veo nur hier, im Prüfwerkzeug
    align = json.loads(Path(align_path).read_text())
    tracks = veo_tracks.build_tracks(veo_tracks.load_export(veo_dir), align["H"])

    def at(t: float) -> dict:
        return {(tracks[k]["team"], tracks[k]["jersey"]): p
                for k, p in veo_tracks.positions_at(tracks, t + align["timeOffsetS"]) if tracks[k]["jersey"] >= 0}
    return at


def identity_metrics(matched: Mapping[str, Mapping[int, object]], fps: float) -> dict:
    """Identitäten je Person (Spieler, die ihr mindestens 1 s folgen), falsch zugeordnete Zeit, Wechsel ≥ 1 s."""
    shared: dict = {}
    for name, frames in matched.items():
        for person, count in Counter(k for k in frames.values() if k is not None).items():
            if count >= fps:
                shared.setdefault(person, Counter())[name] = count
    identities = [len(v) for v in shared.values()]
    return {"identitiesPerPerson": round(float(np.mean(identities)), 2) if identities else None,
            "persons": len(shared), "wrongTimeShare": round(wrong_time_share(matched), 4), "switches": switches(matched, fps)}


def own_matched(identity: Mapping, persons: ref.Persons) -> dict[str, dict[int, object]]:
    """Spieler der Auswertung -> {Bild: Person der Referenz oder None (unklar, offen)}."""
    return {name: {d[0]: persons.of.get(tuple(d)) for d in p["detections"]}
            for name, p in identity["players"].items() if p["team"] in TEAMS}


def number_report(identity: Mapping, matched: Mapping, persons: ref.Persons, fps: float) -> dict:
    """Nummern gegen die Referenz: je Mannschaft Personen (≥ 1 s), davon mit Nutzernummer richtig, falsch, unbekannt."""
    cover: dict = {}
    for name, frames in matched.items():
        for person, count in Counter(k for k in frames.values() if k is not None).items():
            cover.setdefault(person, Counter())[name] = count
    teams = {t: {"persons": 0, "correct": 0, "wrong": 0, "unknown": 0} for t in TEAMS}
    mismatches = []
    for person, c in cover.items():
        team = persons.team.get(person)
        if team not in teams or c.most_common(1)[0][1] < fps:
            continue
        teams[team]["persons"] += 1
        truth = persons.number.get(person)
        if truth is None:
            continue
        player = c.most_common(1)[0][0]
        number = identity["players"][player]["number"]
        key = "unknown" if number is None else ("correct" if number == truth else "wrong")
        teams[team][key] += 1
        if key == "wrong":
            mismatches.append({"player": player, "reference": truth, "read": number})
    wrong_players = []
    for name, frames in matched.items():
        number = identity["players"][name]["number"]
        main = Counter(k for k in frames.values() if k is not None).most_common(1)
        if number is not None and main and persons.number.get(main[0][0]) not in (None, number):
            wrong_players.append({"player": name, "reference": persons.number[main[0][0]], "read": number})
    return {"teams": teams, "playersWithNumber": sum(1 for p in identity["players"].values() if p["number"] is not None),
            "wrongPlayers": wrong_players, "mismatches": mismatches}


def coverage(spots: Sequence[ref.Spot], answers: Sequence[ref.Answer], persons: ref.Persons) -> dict:
    """Wie vollständig die Referenz ist: Stellen, entschieden, unklar, offen, verwaist; Kontrollstellen; Wiederholungen."""
    ids = {s.id for s in spots}
    latest = {}
    for a in answers:
        if not a.repeat and a.spot in ids:
            latest[a.spot] = a
    by_id = {s.id: s for s in spots}
    controls = [s for s in spots if "control" in s.kinds]
    answered = [s for s in controls if s.id in latest]
    errors = sum(1 for s in answered if ref.mapping_of(s, latest[s.id]).get(s.after[0].letter) != s.before[0].letter)
    repeats = [a for a in answers if a.repeat and a.spot in latest]
    agree = sum(1 for a in repeats if ref.mapping_of(by_id[a.spot], a) == ref.mapping_of(by_id[a.spot], latest[a.spot])
                and a.numbers == latest[a.spot].numbers)
    unclear = sum(1 for a in latest.values() if a.choice == "unclear" or "unclear" in a.mapping.values())
    return {"spots": len(spots), "decided": len(latest) - unclear, "unclear": unclear, "open": len(spots) - len(latest),
            "orphaned": sum(1 for a in answers if a.spot not in ids),
            "control": {"spots": len(controls), "answered": len(answered), "errorsFound": errors,
                        "missedRateEstimate": round(errors / len(answered), 3) if answered else None},
            "repeat": {"spots": len(repeats), "agree": agree}}


def _changes(matched: Mapping[str, Mapping[int, object]], fps: float) -> list[tuple[int, str, object, object]]:
    """Personenwechsel ≥ 1 s je Spieler: (Bild, Spieler, vorher, nachher)."""
    out = []
    for name, frames in matched.items():
        runs: list[list] = []
        for f in sorted(frames):
            k = frames[f]
            if k is None:
                continue
            if runs and runs[-1][0] == k:
                runs[-1][2] = f
            else:
                runs.append([k, f, f])
        stable = [r for r in runs if r[2] - r[1] >= fps]
        out += [(b[1], name, a[0], b[0]) for a, b in zip(stable, stable[1:]) if a[0] != b[0]]
    return out


def disagreements(own: Mapping, veo: Mapping, fps: float) -> list[dict]:
    """Wechsel, die nur die Referenz oder nur Veo sieht (Bild, Spieler)."""
    a, b = _changes(own, fps), _changes(veo, fps)
    out = []
    for mine, other, who in ((a, b, "reference"), (b, a, "veo")):
        for f, name, before, after in mine:
            if not any(n == name and abs(g - f) <= NEAR_SWITCH_S * fps for g, n, _, _ in other):
                out.append({"frame": f, "player": name, "seenBy": who,
                            "from": before if who == "veo" else str(before), "to": after if who == "veo" else str(after)})
    return sorted(out, key=lambda d: (d["frame"], d["player"]))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("det")
    ap.add_argument("camera")
    ap.add_argument("--veo", nargs=3, metavar=("VEO_ORDNER", "VEO_ALIGN", "START_S"))
    ap.add_argument("--bericht")
    ap.add_argument("--lesezeit", type=float)
    args = ap.parse_args(argv)
    report_path = jersey_reader.check_private_dir(args.bericht) if args.bericht else None
    identity = json.loads(Path(f"{args.det}.identity.json").read_text())
    data = json.loads(Path(f"{args.det}.reference.json").read_text())
    spots, answers, _ = ref.from_json(data)
    if data.get("identityStamp") != identity.get("stamp"):
        print("Hinweis: Die Stellen gehören zu einer älteren Auswertung; erst tools/review_spots.py laufen lassen.", flush=True)
    fps = identity["fps"]
    persons = ref.persons(identity, spots, answers)
    matched = own_matched(identity, persons)
    present = {n: {d[0] for d in p["detections"]} for n, p in identity["players"].items() if p["team"] in TEAMS}
    numbers = {n: identity["players"][n]["number"] for n in present}
    report = {"scene": data["scene"], "reference": coverage(spots, answers, persons),
              "own": {**identity_metrics(matched, fps), **number_report(identity, matched, persons, fps)},
              "duplicateFrames": duplicate_frames(present, numbers, {n: identity["players"][n]["team"] for n in present}),
              "readSeconds": args.lesezeit}
    if args.veo:
        import review_spots
        import track_players
        det, _, _, ground = review_spots.load_scene(args.det, args.camera, identity)
        at = reference(args.veo[0], args.veo[1])
        truth = [at(float(args.veo[2]) + fr["t"]) for fr in det["frames"]]
        positions = {n: {d[0]: np.asarray(ground[tuple(d)]) for d in identity["players"][n]["detections"]} for n in present}
        veo = track_players.match_reference(positions, truth)
        report["veo"] = {**identity_metrics(veo, fps), "disagreements": disagreements(matched, veo, fps)}
    c, o = report["reference"], report["own"]
    print(f"Referenz: {c['spots']} Stellen, entschieden {c['decided']}, unklar {c['unclear']}, offen {c['open']}, verwaist {c['orphaned']}; "
          f"Kontrolle {c['control']['errorsFound']} Fehler in {c['control']['answered']}; Wiederholung {c['repeat']['agree']} von {c['repeat']['spots']} gleich")
    for team, t in o["teams"].items():
        print(f"{team:9s} Personen {t['persons']:2d}; mit bekannter Nummer: richtig {t['correct']}, falsch {t['wrong']}, unbekannt {t['unknown']}")
    print(f"eigene Referenz: Identitäten je Person {o['identitiesPerPerson']}, falsch zugeordnete Zeit {o['wrongTimeShare']:.1%}, "
          f"Wechsel {o['switches']}; Spieler mit Nummer {o['playersWithNumber']}, davon falsch {len(o['wrongPlayers'])}")
    if "veo" in report:
        v = report["veo"]
        print(f"laut Veo:        Identitäten je Person {v['identitiesPerPerson']}, falsch zugeordnete Zeit {v['wrongTimeShare']:.1%}, "
              f"Wechsel {v['switches']}; Widersprüche {len(v['disagreements'])}")
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n")
        print(f"-> {report_path}")


if __name__ == "__main__":
    main()
