#!/usr/bin/env python3
"""Wandelt Metrica-Sports-Beispieldaten (CSV, Spiel 1 und 2) in das
MatchSpace-Track-Format um (meta.json + tracks.bin).

Aufruf:
    python3 tools/convert_metrica.py HOME.csv AWAY.csv web/data/game1
"""
import csv
import json
import math
import sys
from array import array
from pathlib import Path

MISSING = -32768
SCALE = 0.01  # 1 Einheit = 1 cm
PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0


def open_team(path):
    handle = open(path, newline="")
    reader = csv.reader(handle)
    next(reader)  # Zeile 1: Teamname je Spalte
    numbers = next(reader)
    names = next(reader)
    players = [(i, numbers[i]) for i in range(3, len(names)) if names[i] and names[i] != "Ball"]
    ball = names.index("Ball")
    return handle, reader, players, ball


def quantize(metres):
    return max(-32767, min(32767, round(metres / SCALE)))


def push(out, row, col, z=0.0):
    """Metrica: (0,0) oben links, (1,1) unten rechts. MatchSpace: Ursprung im
    Mittelpunkt, x entlang der Länge, y entlang der Breite, z nach oben, Meter."""
    x, y = float(row[col]), float(row[col + 1])
    if math.isnan(x) or math.isnan(y):
        out.extend((MISSING, MISSING, MISSING))
    else:
        out.extend((quantize((x - 0.5) * PITCH_LENGTH), quantize((0.5 - y) * PITCH_WIDTH), quantize(z)))


def main(home_csv, away_csv, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fh, home, home_players, home_ball = open_team(home_csv)
    fa, away, away_players, _ = open_team(away_csv)

    entities = (
        [{"id": f"home-{n}", "kind": "player", "team": "home", "number": int(n)} for _, n in home_players]
        + [{"id": f"away-{n}", "kind": "player", "team": "away", "number": int(n)} for _, n in away_players]
        + [{"id": "ball", "kind": "ball"}]
    )

    data = array("h")
    periods = []
    times = []
    frames = 0
    for rh, ra in zip(home, away, strict=True):
        if rh[1] != ra[1]:
            sys.exit(f"Frames laufen auseinander: {rh[1]} / {ra[1]}")
        period = int(rh[0])
        if not periods or periods[-1]["id"] != period:
            periods.append({"id": period, "startFrame": frames, "endFrame": frames})
        periods[-1]["endFrame"] = frames
        if frames < 2:
            times.append(float(rh[2]))
        for col, _ in home_players:
            push(data, rh, col)
        for col, _ in away_players:
            push(data, ra, col)
        push(data, rh, home_ball)  # Metrica liefert keine Ballhöhe
        frames += 1
    fh.close()
    fa.close()

    if sys.byteorder != "little":
        data.byteswap()
    with open(out_dir / "tracks.bin", "wb") as f:
        data.tofile(f)

    meta = {
        "format": "matchspace-track",
        "version": 0,
        "fps": round(1 / (times[1] - times[0])),
        "frames": frames,
        "pitch": {"length": PITCH_LENGTH, "width": PITCH_WIDTH, "markings": "standard"},
        "teams": {
            "home": {"name": "Heim", "color": "#d7263d"},
            "away": {"name": "Gast", "color": "#1b65d6"},
        },
        "periods": periods,
        "entities": entities,
        "tracks": {
            "file": "tracks.bin",
            "dtype": "int16le",
            "layout": "frame, entity, [x, y, z]",
            "scale": SCALE,
            "missing": MISSING,
        },
        "source": {
            "name": "Metrica Sports Sample Data, Sample Game 1",
            "url": "https://github.com/metrica-sports/sample-data",
            "notes": "Anonymisiert. Keine Ballhöhe, keine Körperposen.",
        },
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    print(f"{frames} Frames, {len(entities)} Objekte -> {out_dir}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
