#!/usr/bin/env python3
"""Eigener Spielordner ohne Veo: aus einer kleinen Spielbeschreibung (spiel.json) und der Kamera.

Ersetzt das Veo-Basisspiel als Grundlage für Szenen (specs/003-eigene-referenz/contracts/match-description.md):
Spielabschnitte mit Anstoß im Video und Uhr, Platzmaße, Mannschaften. Keine Bewegungsdaten und keine Personennamen.
Luftbild und Kulisse schreiben danach tools/veo_ground.py und tools/veo_backdrop.py in denselben Ordner.

Aufruf:
    .venv/bin/python tools/own_match.py SPIEL.json KAMERA.json SPIELORDNER
"""
import json
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

TEAMS = ("own", "opponent", "referee")
KEYS = {"name", "teams", "periods"}
TRACKS = {"file": "tracks.bin", "dtype": "int16le", "layout": "frame, entity, [x, y, z]", "scale": 0.01, "missing": -32768}


class DescriptionError(ValueError):
    """Die Spielbeschreibung ist ungültig."""


def load_description(path: str | Path) -> dict:
    """Liest und prüft spiel.json: nur name, teams (own, opponent, referee mit name und #rrggbb), periods aufsteigend."""
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise DescriptionError(f"Spielbeschreibung {path} nicht lesbar: {error}") from error
    if not isinstance(data, dict) or set(data) != KEYS:
        raise DescriptionError(f"Spielbeschreibung braucht genau die Felder {', '.join(sorted(KEYS))} (keine Personen)")
    if not isinstance(data["name"], str):
        raise DescriptionError("name muss ein Text sein")
    teams = data["teams"]
    if not isinstance(teams, dict) or set(teams) != set(TEAMS):
        raise DescriptionError(f"teams braucht genau {', '.join(TEAMS)}")
    for team, t in teams.items():
        if not isinstance(t, dict) or set(t) != {"name", "color"} or not re.fullmatch(r"#[0-9a-fA-F]{6}", str(t["color"])):
            raise DescriptionError(f"teams.{team}: name und color als #rrggbb")
    periods = data["periods"]
    if not isinstance(periods, list) or not periods:
        raise DescriptionError("periods: mindestens ein Spielabschnitt")
    for p in periods:
        if not isinstance(p, dict) or set(p) != {"id", "videoStartS", "clockStartS"}:
            raise DescriptionError("periods: je id, videoStartS (Anstoß im Video, s), clockStartS (Spielzeit beim Anstoß, s)")
    starts = [p["videoStartS"] for p in periods]
    if starts != sorted(starts) or len(set(starts)) != len(starts):
        raise DescriptionError("periods müssen nach videoStartS aufsteigend sein")
    return data


def period_at(periods: Sequence[Mapping], start: float) -> tuple[Mapping, float]:
    """Spielabschnitt einer Szene ab Videosekunde start (letzter Anstoß davor) und Spielzeit an ihrem Anfang."""
    before = [p for p in periods if p["videoStartS"] <= start]
    if not before:
        raise DescriptionError(f"Videosekunde {start} liegt vor dem ersten Anstoß")
    p = max(before, key=lambda p: p["videoStartS"])
    return p, p.get("clockStartS", 0) + (start - p["videoStartS"])


def build_meta(desc: Mapping, pitch: Mapping) -> dict:
    """meta.json eines eigenen Spielordners (Format matchspace-track 1) ohne Bewegungsdaten."""
    return {
        "format": "matchspace-track", "version": 1, "fps": 25, "frames": 0,
        "pitch": {"length": float(pitch["length"]), "width": float(pitch["width"]), "markings": "standard"},
        "teams": {team: dict(desc["teams"][team]) for team in TEAMS},
        "periods": [{"id": p["id"], "startFrame": 0, "endFrame": 0, "videoStartS": p["videoStartS"], "clockStartS": p["clockStartS"]}
                    for p in desc["periods"]],
        "entities": [{"id": "ball", "kind": "ball"}],
        "tracks": dict(TRACKS),
        "source": {"name": desc["name"], "notes": "Eigener Spielordner ohne Veo (tools/own_match.py); nur Grundlage für Szenen."},
    }


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 3:
        raise SystemExit(__doc__)
    desc = load_description(args[0])
    pitch = json.loads(Path(args[1]).read_text())["pitch"]
    out = Path(args[2])
    out.mkdir(parents=True, exist_ok=True)
    meta = build_meta(desc, pitch)
    old = out / "meta.json"
    if old.exists():   # Luftbild und Kulisse aus einem früheren Lauf behalten
        before = json.loads(old.read_text()).get("pitch", {})
        meta["pitch"].update({k: v for k, v in before.items() if k in ("texture", "backdrop")})
    old.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    print(f"Spielordner {out}: {len(meta['periods'])} Spielabschnitte, Platz {meta['pitch']['length']:.1f} × {meta['pitch']['width']:.1f} m")


if __name__ == "__main__":
    main()
