#!/usr/bin/env python3
"""Nur zum Prüfen: Wie gut sind die selbst gelesenen Rückennummern einer Szene? Vergleich mit einer Referenz.

Liest die fertige Szene (meta.json, tracks.bin aus tools/veo_scene.py ohne Veo) und als Referenz Veos Spuren
mit Nummern. Schreibt nichts in die Szene: Die Referenz kann das Ergebnis nicht beeinflussen. Gezählt wird
(specs/001-rueckennummern/contracts/eval-report.md):
  - je Mannschaft: Referenzspieler mit mindestens einem gut sichtbaren Rücken, davon richtig, falsch, unbekannt;
  - Identitäten je Referenzspieler (in wie viele eigene Spieler zerfällt er);
  - Bilder, in denen zwei eigene Spieler einer Mannschaft dieselbe Nummer tragen.

Aufruf:
    .venv/bin/python tools/jersey_eval.py SZENE_ORDNER DETEKTIONEN.json KAMERA.json VEO_ORDNER VEO_ALIGN.json START_S [--bericht BERICHT.json] [--lesezeit S]
"""
import argparse
import json
import sys
from array import array
from collections import Counter
from collections.abc import Mapping
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import jersey_reader  # noqa: E402
import track_players  # noqa: E402

TEAMS = ("own", "opponent")
WELL_VISIBLE = jersey_reader.FULL_HEIGHT   # px Schulter bis Hüfte: ab hier gilt ein Rücken als gut sichtbar


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


def evaluate(numbers: Mapping[str, int | None], teams: Mapping[str, str], matched: Mapping[str, Mapping[int, tuple | None]],
             visible: set[tuple[str, int]], fps: float) -> dict:
    """Zählt richtig, falsch, unbekannt je Mannschaft und Identitäten je Referenzspieler.

    matched: eigener Spieler -> {Bild: Referenz (Mannschaft, Nummer) oder None}; visible: Referenzspieler mit gut
    sichtbarem Rücken. Ein eigener Spieler gehört zu einem Referenzspieler, wenn er ihm mindestens 1 s zugeordnet ist."""
    shared: dict[tuple, Counter] = {}
    for name, frames in matched.items():
        for ref, count in Counter(k for k in frames.values() if k is not None).items():
            if count >= fps:
                shared.setdefault(ref, Counter())[name] = count
    out = {team: {"visible": 0, "correct": 0, "wrong": 0, "unknown": 0} for team in TEAMS}
    mismatches = []
    for ref in sorted(visible):
        team, jersey = ref
        if team not in out:
            continue
        out[team]["visible"] += 1
        best = shared.get(ref, Counter()).most_common(1)
        number = numbers.get(best[0][0]) if best else None
        if number is None:
            out[team]["unknown"] += 1
        elif number == jersey:
            out[team]["correct"] += 1
        else:
            out[team]["wrong"] += 1
            mismatches.append({"player": best[0][0], "reference": jersey, "read": number})
    # falsche Nummern über alle eigenen Spieler (auch ohne gut sichtbaren Rücken der Referenz)
    wrong_players = []
    for name, number in numbers.items():
        if number is None:
            continue
        refs = Counter(k for k in matched.get(name, {}).values() if k is not None)
        if refs and refs.most_common(1)[0][0] != (teams[name], number):
            wrong_players.append({"player": name, "reference": refs.most_common(1)[0][0][1], "read": number})
    identities = [len(v) for v in shared.values()]
    return {"teams": out, "identitiesPerPlayer": round(float(np.mean(identities)), 2) if identities else None,
            "referencePlayers": len(shared), "playersWithNumber": sum(1 for v in numbers.values() if v is not None),
            "wrongPlayers": wrong_players, "mismatches": mismatches}


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


def visible_references(det: dict, cam: dict, det_path: str, at, start: float) -> set:
    """Referenzspieler, deren Rücken mindestens einmal gut sichtbar gelesen wurde ({det}.numbers.npz)."""
    cache = np.load(f"{det_path}.numbers.npz")
    rows = track_players.detections(det, cam)
    where = {}
    for f, r in enumerate(rows):
        for row in r:
            where[(f, int(row[3]), int(row[8]))] = row[:2]
    out = set()
    for f, lens, box, h in zip(cache["frame"], cache["lens"], cache["box"], cache["height"]):
        p = where.get((int(f), int(lens), int(box)))
        if p is None or h < WELL_VISIBLE:
            continue
        truth = at(start + det["frames"][int(f)]["t"])
        near = [(float(np.hypot(*(p - q))), k) for k, q in truth.items()]
        if near and min(near)[0] < track_players.REFERENCE_GATE:
            out.add(min(near)[1])
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    for name in ("scene", "det", "camera", "veo", "align"):
        ap.add_argument(name)
    ap.add_argument("start", type=float)
    ap.add_argument("--bericht")
    ap.add_argument("--lesezeit", type=float)
    args = ap.parse_args(argv)
    report_path = jersey_reader.check_private_dir(args.bericht) if args.bericht else None
    import veo_camera
    meta, xy = load_scene(Path(args.scene))
    det = json.loads(Path(args.det).read_text())
    cam = veo_camera.load(args.camera)
    at = reference(args.veo, args.align)
    fps = meta["fps"]
    truth = [at(args.start + i / fps) for i in range(meta["frames"])]
    players = [(i, e) for i, e in enumerate(meta["entities"]) if e["kind"] == "player" and e["team"] in TEAMS]
    positions = {e["id"]: {f: xy[f, i] for f in range(meta["frames"]) if not np.isnan(xy[f, i, 0])} for i, e in players}
    matched = track_players.match_reference(positions, truth)
    numbers = {e["id"]: e.get("number") for _, e in players}
    teams = {e["id"]: e["team"] for _, e in players}
    report = {"scene": Path(args.scene).name,
              **evaluate(numbers, teams, matched, visible_references(det, cam, args.det, at, args.start), fps),
              "duplicateFrames": duplicate_frames({k: set(v) for k, v in positions.items()}, numbers, teams),
              "readSeconds": args.lesezeit}
    for team, c in report["teams"].items():
        print(f"{team:9s} gut sichtbar {c['visible']:2d}: richtig {c['correct']:2d}, falsch {c['wrong']:2d}, unbekannt {c['unknown']:2d}")
    print(f"Spieler mit Nummer {report['playersWithNumber']}, davon falsch {len(report['wrongPlayers'])}; "
          f"Identitäten je Referenzspieler {report['identitiesPerPlayer']}; Bilder mit doppelter Nummer {report['duplicateFrames']}")
    for m in report["mismatches"] + report["wrongPlayers"]:
        print(f"  nachsehen: {m['player']} gelesen {m['read']}, Referenz {m['reference']}")
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        print(f"-> {report_path}")


if __name__ == "__main__":
    main()
