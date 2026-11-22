#!/usr/bin/env python3
"""Wandelt einen Veo-Export (Positionsdaten, Halbzeiten) in das MatchSpace-Track-Format um.

Veo misst etwa 2,5-mal pro Sekunde. Die Bahnen werden auf 25 Hz hochgerechnet
(glatte Kurve durch die Messpunkte), damit Bewegung und Posen flüssig laufen.
Spuren mit erkannter Rückennummer werden je Mannschaft und Nummer zusammengeführt,
Spuren ohne Nummer zu anonymen Spielern ("?") verkettet.

Veo gibt Positionen als Anteil eines Vierecks aus vier angeklickten Ecken an und nimmt
105 m Platzlänge an. Mit VEO_ALIGN (tools/veo_align.py) und KAMERA (tools/veo_camera.py)
werden die Positionen auf den echten, selbst ausgemessenen Platz umgerechnet. Ohne die
beiden Dateien gelten Veos Maße; Strecken und Tempo sind dann nur so gut wie Veos Annahme.

Aufruf:
    python3 tools/convert_veo.py data/raw/veo/DATUM/export.json web/data/NAME [VEO_ALIGN.json KAMERA.json]
"""
import json
import math
import sys
from array import array
from collections import Counter, defaultdict
from pathlib import Path

MISSING = -32768
SCALE = 0.01
FPS = 25
MAX_GAP_S = 1.3      # längere Lücken bleiben Lücken
STITCH_GAP_S = 20.0  # anonyme Spuren verketten: höchstens so lange Pause ...
STITCH_SPEED = 8.0   # ... und höchstens dieses Tempo (m/s) dazwischen, plus 3 m


def main(export_path, out_dir, align_path=None, camera_path=None):
    export_path, out_dir = Path(export_path), Path(out_dir)
    export = json.loads(export_path.read_text())
    if align_path:
        H = json.loads(Path(align_path).read_text())["H"]
        pitch = json.loads(Path(camera_path).read_text())["pitch"]
        length, width = pitch["length"], pitch["width"]
        measured = True

        def metres(x, y):
            w = H[2][0] * x + H[2][1] * y + H[2][2]
            return (H[0][0] * x + H[0][1] * y + H[0][2]) / w, (H[1][0] * x + H[1][1] * y + H[1][2]) / w
    else:
        length, width, measured = 105.0, 68.0, False
        veo_path = export_path.with_name("camera_alignment.json")
        if veo_path.exists():
            veo = json.loads(veo_path.read_text())["alignment"]
            length, width = veo["field_length"], veo["field_width"]

        def metres(x, y):
            return (x - 0.5) * length, (y - 0.5) * width

    periods = sorted(export["periods"], key=lambda p: p["timeframe"][0])
    frames = sorted((float(t), objs) for t, objs in export["tracking"].items())

    def period_of(t):
        for i, p in enumerate(periods):
            if p["timeframe"][0] <= t <= p["timeframe"][1]:
                return i
        return None

    # Welche Veo-Teamkennung (Feld 7) ist die eigene Mannschaft?
    votes = Counter()
    for t, objs in frames:
        pi = period_of(t)
        if pi is None:
            continue
        for o in objs:
            if o[1] in (0, 1, 2, 3) and o[7]:
                left = o[1] in (0, 1)
                votes[(o[7], left == (periods[pi]["own_side"] == "left"))] += 1
    own_team = max({k[0] for k in votes}, key=lambda team: votes[(team, True)] - votes[(team, False)])

    # Spuren einsammeln: Veo-Spurnummer -> Messpunkte in Metern
    tracks = defaultdict(lambda: {"pts": [], "jersey": Counter(), "team": Counter(), "gk": 0, "kind": None})
    ball = []
    for t, objs in frames:
        if period_of(t) is None:
            continue
        for o in objs:
            # Veo: x von links nach rechts, y = 0 an der Kameraseite. MatchSpace: y zeigt von der Kamera weg.
            p = (t, *metres(o[2], o[3]))
            if o[1] == 6:
                ball.append(p)
            elif o[1] in (0, 1, 2, 3, 4):
                tr = tracks[o[0]]
                tr["pts"].append(p)
                tr["kind"] = "referee" if o[1] == 4 else "player"
                if o[1] != 4:
                    tr["team"][o[7]] += 1
                    tr["gk"] += 1 if o[1] in (0, 2) else -1
                    if o[4] >= 0:
                        tr["jersey"][int(o[4])] += 1

    # Spuren zu Personen zusammenführen
    people = {}  # Schlüssel -> {"pts": [...], Metadaten}
    anon = defaultdict(list)  # Gruppe -> Liste anonymer Personen

    def group_of(tr):
        if tr["kind"] == "referee":
            return "referee"
        return "own" if tr["team"].most_common(1)[0][0] == own_team else "opponent"

    for tid, tr in sorted(tracks.items(), key=lambda kv: kv[1]["pts"][0][0]):
        group = group_of(tr)
        if tr["jersey"]:
            number = tr["jersey"].most_common(1)[0][0]
            person = people.setdefault((group, number), {"group": group, "number": number, "pts": [], "gk": 0})
        else:
            first = tr["pts"][0]
            person = None
            for cand in anon[group]:
                last = cand["pts"][-1]
                gap = first[0] - last[0]
                if 0 < gap <= STITCH_GAP_S and math.hypot(first[1] - last[1], first[2] - last[2]) <= 3 + STITCH_SPEED * gap:
                    person = cand
                    break
            if person is None:
                person = {"group": group, "number": None, "pts": [], "gk": 0}
                anon[group].append(person)
        person["pts"].extend(tr["pts"])
        person["gk"] += tr["gk"]

    order = {"own": 0, "opponent": 1, "referee": 2}
    listed = sorted(people.values(), key=lambda p: (order[p["group"]], p["number"]))
    for group in ("own", "opponent", "referee"):
        listed.extend(sorted(anon[group], key=lambda p: -len(p["pts"])))
    listed.sort(key=lambda p: order[p["group"]])

    # Zeitraster: nur die Halbzeiten, lückenlos hintereinander
    meta_periods, starts, total = [], [], 0
    for i, p in enumerate(periods):
        t0, t1 = p["timeframe"]
        n = int((t1 - t0) * FPS) + 1
        starts.append((t0, t1, total))
        nominal = round((t1 - t0) / 300) * 300  # Regelspielzeit der Halbzeit, auf 5 min gerundet
        meta_periods.append({"id": i + 1, "startFrame": total, "endFrame": total + n - 1,
                             "videoStartS": t0, "clockStartS": i * nominal})
        total += n

    entities = []
    counters = Counter()
    for person in listed:
        group = person["group"]
        counters[group] += 1
        if group == "referee":
            entities.append({"id": f"referee-{counters[group]}", "kind": "player", "team": "referee", "number": 0, "label": "SR"})
        elif person["number"] is None:
            entities.append({"id": f"{group}-x{counters[(group, 'x')] + 1}", "kind": "player", "team": group, "number": 0, "label": "?"})
            counters[(group, "x")] += 1
        else:
            entity = {"id": f"{group}-{person['number']}", "kind": "player", "team": group, "number": person["number"]}
            if person["gk"] > 0:
                entity["role"] = "goalkeeper"
            entities.append(entity)
    entities.append({"id": "ball", "kind": "ball"})
    all_pts = [p["pts"] for p in listed] + [ball]

    E = len(entities)
    data = array("h", [MISSING]) * (total * E * 3)

    def write(e, frame, x, y):
        i = (frame * E + e) * 3
        data[i] = max(-32767, min(32767, round(x / SCALE)))
        data[i + 1] = max(-32767, min(32767, round(y / SCALE)))
        data[i + 2] = 0

    for e, pts in enumerate(all_pts):
        pts = sorted(set(pts))
        for t0, t1, base in starts:
            seg = [p for p in pts if t0 <= p[0] <= t1]
            for k in range(len(seg) - 1):
                a, b = seg[k], seg[k + 1]
                dt = b[0] - a[0]
                if dt <= 0 or dt > MAX_GAP_S:
                    continue
                # Catmull-Rom: Tangenten aus den Nachbarpunkten, an Lücken aus dem Segment selbst
                prev = seg[k - 1] if k > 0 and a[0] - seg[k - 1][0] <= MAX_GAP_S else None
                nxt = seg[k + 2] if k + 2 < len(seg) and seg[k + 2][0] - b[0] <= MAX_GAP_S else None
                tan = []
                for axis in (1, 2):
                    ma = (b[axis] - prev[axis]) / (b[0] - prev[0]) if prev else (b[axis] - a[axis]) / dt
                    mb = (nxt[axis] - a[axis]) / (nxt[0] - a[0]) if nxt else (b[axis] - a[axis]) / dt
                    tan.append((ma * dt, mb * dt))
                f0 = math.ceil((a[0] - t0) * FPS - 1e-9)
                f1 = math.floor((b[0] - t0) * FPS + 1e-9)
                for f in range(f0, f1 + 1):
                    s = ((t0 + f / FPS) - a[0]) / dt
                    s = min(1.0, max(0.0, s))
                    h00, h10 = 2 * s**3 - 3 * s**2 + 1, s**3 - 2 * s**2 + s
                    h01, h11 = -2 * s**3 + 3 * s**2, s**3 - s**2
                    write(e, base + f,
                          h00 * a[1] + h10 * tan[0][0] + h01 * b[1] + h11 * tan[0][1],
                          h00 * a[2] + h10 * tan[1][0] + h01 * b[2] + h11 * tan[1][1])

    out_dir.mkdir(parents=True, exist_ok=True)
    if sys.byteorder != "little":
        data.byteswap()
    with open(out_dir / "tracks.bin", "wb") as f:
        data.tofile(f)

    match = export.get("match", {})
    colors = {"red": "#d7263d", "green": "#1f9d55", "blue": "#1b65d6", "white": "#e8e8e8", "black": "#222222",
              "yellow": "#e0b400", "orange": "#e8730c", "purple": "#7c3aed"}
    meta = {
        "format": "matchspace-track",
        "version": 1,
        "fps": FPS,
        "frames": total,
        "pitch": {"length": length, "width": width, "markings": "standard"},
        "teams": {
            "own": {"name": "Wir", "color": colors.get(match.get("ownColor"), "#d7263d")},
            "opponent": {"name": "Gegner", "color": colors.get(match.get("opponentColor"), "#1b65d6")},
            "referee": {"name": "Schiedsrichter", "color": "#f2c200"},
        },
        "periods": meta_periods,
        "entities": entities,
        "tracks": {"file": "tracks.bin", "dtype": "int16le", "layout": "frame, entity, [x, y, z]",
                   "scale": SCALE, "missing": MISSING},
        "source": {
            "name": f"Veo, {match.get('ageGroup', '')} {str(match.get('date', ''))[:10]}".strip(),
            "notes": "Veo-Positionsdaten (ca. 2,5 Hz), auf 25 Hz interpoliert. Keine Ballhöhe. "
                     "Rückennummern laut Veo-Erkennung, '?' = Spur ohne erkannte Nummer. "
                     + ("Positionen auf den selbst ausgemessenen Platz umgerechnet." if measured
                        else "Platzmaße laut Veo (Länge pauschal 105 m), nicht nachgemessen."),
        },
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    named = sum(1 for e in entities if e["kind"] == "player" and "label" not in e)
    print(f"{total} Frames, {E} Objekte ({named} mit Rückennummer, {E - 1 - named} ohne/Schiedsrichter) -> {out_dir}")


if __name__ == "__main__":
    if len(sys.argv) not in (3, 5):
        sys.exit(__doc__)
    main(*sys.argv[1:])
