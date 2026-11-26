#!/usr/bin/env python3
"""Spielanalyse auf den Bahnen einer fertigen Szene: Abseits (Ziel 1) und freie Schussbahn (Ziel 3).

Arbeitet nur auf dem, was jede Szene (web/data/<szene>/) enthält: Bahnen (tracks.bin), Mannschaften und die Ballkontakte mit Spieler (meta.json:
`ballContacts`, aus tools/ball_outlook.py). Es ist also unabhängig von Kamera und Video und gilt für jede Perspektive, aus der Bahnen kommen.

Angriffsrichtung: je Mannschaft +1 (Tor bei +Länge/2) oder -1. Sie steht in meta.json unter periods[].attack, wird aber nicht geraten:
ohne sie keine Aussage. (In ganzen Spielen folgt sie aus dem Torwart, siehe tools/own_scene.py; in kurzen Szenen ist der Torwart oft nicht im Bild.)

Abseits (Regel 11, vereinfacht): Beim Kontakt eines Spielers (Pass oder Schuss) steht ein Mitspieler im Abseits, wenn er in der gegnerischen Hälfte näher
an der Torlinie ist als der Ball und der vorletzte Gegner. Gemessen wird mit der Hüfte (Spur), nicht mit dem vordersten Körperteil: Spielraum
ABS_TOL m; knappere Fälle sind als `close` gekennzeichnet, nicht entschieden. Ein Abseitsverdacht gilt als Regelverstoß erst, wenn der Mitspieler danach
innerhalb von INVOLVE_S den Ball berührt. Sieht man weniger als zwei Gegner, gibt es kein Urteil (ihr vorletzter ist unbekannt).

Freie Schussbahn: Vom Ball aus wird der Winkelbereich des Tors (Breite 7,32 m) bestimmt, den kein Gegner verdeckt (Körperbreite BLOCK_M als Scheibe).
Rückgabe ist der freie Anteil und die Mitte der größten Lücke. Ein Gegner, der nicht zwischen Ball und Torlinie steht, verdeckt nichts.

Aufruf:  .venv/bin/python tools/game_analysis.py SZENE_ORDNER [--angriff own=+1,opponent=-1]   (schreibt analysis.json in den Ordner)
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

GOAL_WIDTH = 7.32
BLOCK_M = 0.4          # m: Halbbreite, die ein Gegner (Körper plus Ball) der Schussbahn nimmt
ABS_TOL = 0.5          # m: Abstände zur Abseitslinie darunter gelten als knapp
INVOLVE_S = 4.0        # s: so bald danach muss der Mitspieler am Ball sein, damit der Abseitsverdacht zählt
LANE_RANGE_M = 30.0    # m: weiter vom Tor weg wird keine Schussbahn bewertet
SHOT_KINDS = ("pass", "shot")
KEEPER_ZONE = (8.0, 6.0)   # m: Tiefe und halbe Breite vor dem Tor, in der ein Gegner als Torwart gilt
THROW_FRAMES = 2           # Bilder: so nah an einem Einwurf ist der Kontakt der Einwurf selbst (Anstoß ohne Abseits, kein Schuss)


class Scene:
    def __init__(self, meta: dict, xy: np.ndarray):
        self.meta, self.xy = meta, xy
        self.ids = [e["id"] for e in meta["entities"]]
        self.team = [e.get("team") for e in meta["entities"]]
        self.kind = [e["kind"] for e in meta["entities"]]
        self.fps = float(meta["fps"])
        self.half_length = meta["pitch"]["length"] / 2


def load(scene_dir) -> Scene:
    d = Path(scene_dir)
    meta = json.loads((d / "meta.json").read_text())
    t = meta["tracks"]
    raw = np.fromfile(d / t["file"], dtype="<i2").reshape(meta["frames"], len(meta["entities"]), 3)
    xy = raw[:, :, :2].astype(float) * t["scale"]
    xy[raw[:, :, 0] == t["missing"]] = np.nan
    return Scene(meta, xy)


def players_of(scene: Scene, team: str | None = None, other: bool = False) -> list:
    """Indizes der Spieler; mit team nur diese Mannschaft, mit other=True nur die anderen Mannschaften (Spieler, nicht Schiedsrichter)."""
    return [i for i, k in enumerate(scene.kind) if k == "player" and (team is None or ((scene.team[i] == team) != other))]


def offside_positions(scene: Scene, frame: int, passer: int, attack: int) -> dict | None:
    """Mitspieler des Passgebers `passer` im Abseits zur Zeit des Kontakts. Rückgabe: {line (Linie in Richtung des Angriffs), defenders (gesehen), players: [...]}
    oder None, wenn weniger als zwei Gegner zu sehen sind oder der Ball fehlt."""
    ball = scene.kind.index("ball")
    b = scene.xy[frame, ball]
    if np.isnan(b).any():
        return None
    team = scene.team[passer]
    foes = [i for i in players_of(scene, team, other=True) if not np.isnan(scene.xy[frame, i]).any()]
    if len(foes) < 2:
        return None
    toward = lambda x: attack * x          # noqa: E731   Position in Richtung des gegnerischen Tors
    second_last = sorted(toward(scene.xy[frame, i, 0]) for i in foes)[-2]
    line = max(second_last, toward(b[0]))
    out = []
    for i in players_of(scene, team):
        if i == passer or np.isnan(scene.xy[frame, i]).any():
            continue
        u = toward(scene.xy[frame, i, 0])
        margin = u - line
        out.append({"id": scene.ids[i], "margin": round(float(margin), 2), "offside": bool(u > 0 and margin > 0), "close": bool(abs(margin) < ABS_TOL)})
    return {"line": round(float(line), 2), "defenders": len(foes), "players": out}


def free_lane(scene: Scene, frame: int, shooter: int, attack: int) -> dict | None:
    """Freier Anteil des Tors vom Ball aus gesehen. Rückgabe: {distance, free (0..1), gapCentre (m quer am Tor), gapWidth (m)} oder None (Ball fehlt, zu weit)."""
    ball = scene.kind.index("ball")
    b = scene.xy[frame, ball]
    if np.isnan(b).any():
        return None
    goal_x = attack * scene.half_length
    dist = abs(goal_x - b[0])
    if dist > LANE_RANGE_M or dist < 0.5:
        return None
    half = GOAL_WIDTH / 2
    lo, hi = np.arctan2(-half - b[1], dist), np.arctan2(half - b[1], dist)       # Winkel zur Torlinie, Mitte der Lücke in Winkeln
    blocked = []
    for i in players_of(scene, scene.team[shooter], other=True):
        p = scene.xy[frame, i]
        if np.isnan(p).any():
            continue
        along = (p[0] - b[0]) * attack
        if along <= 0 or along > dist:      # nicht zwischen Ball und Torlinie
            continue
        d = float(np.hypot(along, p[1] - b[1]))
        centre = np.arctan2(p[1] - b[1], along)
        spread = np.arcsin(min(1.0, BLOCK_M / d))
        blocked.append((centre - spread, centre + spread))
    keeper = any(not np.isnan(scene.xy[frame, i]).any() and abs(scene.xy[frame, i, 0] - goal_x) <= KEEPER_ZONE[0] and abs(scene.xy[frame, i, 1]) <= KEEPER_ZONE[1]
                 for i in players_of(scene, scene.team[shooter], other=True))
    free, best = _gaps(lo, hi, blocked)
    total = hi - lo
    gap_lo, gap_hi = best
    return {"distance": round(float(dist), 1), "keeperSeen": keeper, "free": round(float(free / total), 2),
            "gapCentre": round(float(b[1] + np.tan((gap_lo + gap_hi) / 2) * dist), 2) if gap_hi > gap_lo else None,
            "gapWidth": round(float((np.tan(gap_hi) - np.tan(gap_lo)) * dist), 2) if gap_hi > gap_lo else 0.0}


def _gaps(lo: float, hi: float, blocked: list) -> tuple:
    """Freie Länge in [lo, hi] nach Abzug der Sperrintervalle, und die größte freie Lücke (von, bis)."""
    gaps, cur = [], lo
    for a, b in sorted(blocked):
        if a > cur:
            gaps.append((cur, min(a, hi)))
        cur = max(cur, b)
        if cur >= hi:
            break
    if cur < hi:
        gaps.append((cur, hi))
    gaps = [(a, b) for a, b in gaps if b > a]
    return sum(b - a for a, b in gaps), (max(gaps, key=lambda g: g[1] - g[0]) if gaps else (0.0, 0.0))


def analyse(scene: Scene, attack: dict) -> dict:
    """Je Pass oder Schuss mit bekanntem Spieler: Abseitsstellung der Mitspieler und freie Schussbahn. attack: Mannschaft -> +1 oder -1."""
    contacts = scene.meta.get("ballContacts", [])
    throws = [e["frame"] for e in scene.meta.get("events", []) if e["kind"] == "throw-in"]
    rows = []
    for n, c in enumerate(contacts):
        if c["kind"] not in SHOT_KINDS or c["player"] is None or any(abs(c["frame"] - f) <= THROW_FRAMES for f in throws):
            continue
        i = scene.ids.index(c["player"])
        a = attack.get(scene.team[i])
        if a is None:
            continue
        row = {"frame": c["frame"], "time": round(c["frame"] / scene.fps, 2), "kind": c["kind"], "player": c["player"], "offside": None, "shotLane": None}
        o = offside_positions(scene, c["frame"], i, a)
        if o is not None:
            later = [x for x in contacts[n + 1:] if x["player"] is not None and (x["frame"] - c["frame"]) / scene.fps <= INVOLVE_S]
            involved = next(iter(x["player"] for x in later if scene.team[scene.ids.index(x["player"])] == scene.team[i]), None)
            for p in o["players"]:
                p["involved"] = p["id"] == involved
            o["verdict"] = ("offside" if any(p["offside"] and p["involved"] and not p["close"] for p in o["players"])
                            else "close" if any(p["offside"] and p["involved"] for p in o["players"]) else "onside")
            row["offside"] = o
        lane = free_lane(scene, c["frame"], i, a)
        if lane is not None:
            lane["unused"] = bool(c["kind"] != "shot" and lane["free"] >= 0.5 and lane["keeperSeen"])   # ohne gesehenen Torwart keine Aussage
            row["shotLane"] = lane
        rows.append(row)
    return {"attack": attack, "rows": rows, "note": "Hüftposition statt vorderstem Körperteil; Urteile mit `close` sind knapp und nicht entschieden."}


def parse_attack(text: str) -> dict:
    return {k: int(v) for k, v in (p.split("=") for p in text.split(","))}


def main(argv) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("scene")
    ap.add_argument("--angriff", help="z. B. own=+1,opponent=-1 (sonst aus meta.json periods[].attack)")
    args = ap.parse_args(argv)
    scene = load(args.scene)
    attack = parse_attack(args.angriff) if args.angriff else (scene.meta["periods"][0].get("attack") or {})
    if not attack:
        sys.exit("Angriffsrichtung unbekannt: --angriff own=+1,opponent=-1 angeben (+1 = Tor bei +x). Ohne sie keine Aussage.")
    result = analyse(scene, attack)
    (Path(args.scene) / "analysis.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))
    for r in result["rows"]:
        o, lane = r["offside"], r["shotLane"]
        print(f"{r['time']:.1f} s {r['kind']} von {r['player']}: "
              + (f"Abseits {o['verdict']} (Linie {o['line']} m, {o['defenders']} Gegner gesehen)" if o else "Abseits: kein Urteil")
              + (f"; Schussbahn frei {lane['free']:.0%}, Lücke {lane['gapWidth']} m bei y={lane['gapCentre']}" + (" (nicht genutzt)" if lane["unused"] else "")
                 + ("" if lane["keeperSeen"] else " [Torwart nicht gesehen: unsicher]") if lane else ""))
    print(f"{len(result['rows'])} Pässe/Schüsse bewertet -> {args.scene}/analysis.json")


if __name__ == "__main__":
    main(sys.argv[1:])
