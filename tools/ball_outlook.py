#!/usr/bin/env python3
"""Flugbahn des Balls über das Ende der Messung hinaus und Einwürfe als Ereignisse.

Aus der Ballspur (tools/ball_motion.py: Flugstücke mit Höhe) wird zu jedem Flug die Wurfparabel angepasst (Schwerkraft bekannt, kein Luftwiderstand)
und dort weitergeführt, wo ihn ein Kontakt (Fuß, Kopf, Pfosten) beendet hat. Daraus folgt, wohin der Ball ohne diesen Kontakt geflogen wäre:
wo er gelandet wäre und, wenn die Bahn die Torlinie kreuzt, ob zwischen den Pfosten und unter der Latte (Tor), darüber oder daneben.
Das ist die Grundlage für die Frage „wäre der Ball ohne die Ablenkung aufs Tor gegangen?“ (Ziel 2).

Die Fortsetzung ist eine Rechnung, keine Messung: Sie gilt nur so weit, wie die Parabel stimmt, und trägt die Unsicherheit der Höhe des Flugs mit.
Ein Flug, der am Boden endet (Landung), wird nicht verlängert.

Einwurf: Ein Flug, der an der Seitenlinie in Handhöhe beginnt, aus dem Stand vor der Hand (kein Rollen davor), zählt als Einwurf; Werfer ist der nächste Spieler.

Aufruf:  .venv/bin/python tools/ball_outlook.py DETEKTIONEN.json   (liest .ball3d.npz, schreibt .outlook.json)
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import ball_events  # noqa: E402
import ball_physics  # noqa: E402

PITCH = (90.0, 55.0)       # m: Länge, Breite, wenn die Szene nichts anderes sagt
GOAL_WIDTH = 7.32          # m (Tore im Jugendfußball sind oft kleiner; die Maße sind Parameter)
GOAL_HEIGHT = 2.44
LANDED_M = 0.5             # m: endet der Flug niedriger, ist der Ball gelandet und wird nicht verlängert
MAX_AHEAD_S = 4.0          # s: so weit wird höchstens fortgesetzt
STEP_S = 1 / 120
FIT_TAIL = 12              # Bilder am Ende des Flugs, aus denen die Parabel für die Fortsetzung stammt
THROW_LINE_M = 1.5         # m: so nah an der Seitenlinie beginnt ein Einwurf
THROW_MIN_Z = 1.3          # m: Mindesthöhe des Balls beim Abwurf
THROW_MAX_SPEED = 25.0     # m/s
MAX_SPEED = 35.0           # m/s: schneller fliegt ein Ball im Jugendfußball nicht; ein solcher „Flug“ ist ein Fehler der Höhenbestimmung
MARGIN_M = 3.0             # m: so weit außerhalb des Spielfelds darf ein Flug beginnen oder enden und noch glaubwürdig sein


def fit_parabola(t: np.ndarray, xyz: np.ndarray) -> tuple:
    """Lage p0 bei t[0] und Geschwindigkeit v einer Wurfparabel (feste Schwerkraft) durch die Lagen (n, 3). Rückgabe: p0, v, Restfehler in m."""
    x = t - t[0]
    y = xyz + 0.5 * ball_physics.G * (x ** 2)[:, None] * np.array([0.0, 0.0, 1.0])
    A = np.column_stack([np.ones_like(x), x])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    resid = y - A @ coef
    return coef[0], coef[1], float(np.sqrt((resid ** 2).sum(axis=1).mean()))


def position(p0: np.ndarray, v: np.ndarray, x: float) -> np.ndarray:
    return p0 + v * x - 0.5 * ball_physics.G * x * x * np.array([0.0, 0.0, 1.0])


def goal_verdict(y: float, z: float) -> str:
    """Wo die Bahn die Torlinie kreuzt: goal, high (darüber), wide (daneben)."""
    r = ball_physics.RADIUS
    if abs(y) > GOAL_WIDTH / 2 + r:
        return "wide"
    if z - r > GOAL_HEIGHT:
        return "high"
    return "goal"


def continue_flight(p0, v, t_end: float, half_length: float, half_width: float) -> dict:
    """Fortsetzung ab t_end (s nach p0-Zeit 0): Landung, Torlinie, Seitenlinie. p0 gehört zu Zeit 0."""
    out = {"landing": None, "goal_line": None, "touch_line": False}
    steps = int(MAX_AHEAD_S / STEP_S)
    prev = position(p0, v, t_end)
    for i in range(1, steps + 1):
        x = t_end + i * STEP_S
        cur = position(p0, v, x)
        if out["goal_line"] is None and abs(cur[0]) >= half_length > abs(prev[0]):
            frac = (half_length - abs(prev[0])) / max(abs(cur[0]) - abs(prev[0]), 1e-9)
            at = prev + frac * (cur - prev)
            out["goal_line"] = {"side": int(np.sign(cur[0])), "y": round(float(at[1]), 2), "z": round(float(at[2]), 2),
                                "time_ahead": round(x - t_end - (1 - frac) * STEP_S, 2), "verdict": goal_verdict(float(at[1]), float(at[2]))}
        if not out["touch_line"] and abs(cur[1]) >= half_width > abs(prev[1]):
            out["touch_line"] = True
        if cur[2] <= ball_physics.RADIUS:
            out["landing"] = {"x": round(float(cur[0]), 2), "y": round(float(cur[1]), 2), "time_ahead": round(x - t_end, 2)}
            break
        prev = cur
    return out


def flights(kind: np.ndarray) -> list:
    """(von, bis) der Flugstücke (bis ausschließlich)."""
    isf = np.append(kind == 2, False)
    out, start = [], None
    for f, v in enumerate(isf):
        if v and start is None:
            start = f
        if not v and start is not None:
            out.append((start, f))
            start = None
    return out


def outlook(xyz: np.ndarray, kind: np.ndarray, fps: float, pitch=PITCH) -> list:
    """Je Flug: Beginn, Ende, größte Höhe, Abwurfgeschwindigkeit; endet er im Flug (Kontakt), seine Fortsetzung bis zur Landung und zur Torlinie."""
    half_length, half_width = pitch[0] / 2, pitch[1] / 2
    result = []
    for a, b in flights(kind):
        t = np.arange(a, b) / fps
        pts = xyz[a:b]
        ok = ~np.isnan(pts[:, 0])
        if ok.sum() < 4:
            continue
        p0, v, err = fit_parabola(t[ok], pts[ok])
        last = pts[ok][-1]
        item = {"start": a, "end": b, "t_start": round(a / fps, 2), "t_end": round(b / fps, 2),
                "apex": round(float(pts[ok][:, 2].max()), 2), "start_pos": [round(float(c), 2) for c in pts[ok][0]],
                "end_pos": [round(float(c), 2) for c in last], "speed": round(float(np.linalg.norm(v)), 1), "fit_error": round(err, 3)}
        # Fortsetzung aus dem Ende des Flugs, nicht aus dem Anfang: dort sitzt die Parabel an den jüngsten Lagen
        tail = slice(max(0, ok.sum() - FIT_TAIL), None)
        tt, tp = t[ok][tail], pts[ok][tail]
        q0, qv, _ = fit_parabola(tt, tp)
        item["ended_in_air"] = bool(last[2] > LANDED_M)
        outside = any(abs(p[0]) > half_length + MARGIN_M or abs(p[1]) > half_width + MARGIN_M for p in (pts[ok][0], last))
        item["reliable"] = bool(item["speed"] <= MAX_SPEED and not outside)   # sonst keine Fortsetzung: sie würde den Fehler fortschreiben
        item["continuation"] = (continue_flight(q0, qv, float(tt[-1] - tt[0]), half_length, half_width)
                                if item["ended_in_air"] and item["reliable"] else None)
        result.append(item)
    return result


def speed_near(xyz: np.ndarray, frame: int, fps: float, after: bool, span: int = 6) -> float | None:
    """Tempo des Balls in m/s kurz vor oder nach einem Bild aus der räumlichen Spur (mit Höhe), nicht aus der Spur im Bild: Die Winkelspur
    überschätzt im Flug das Tempo stark (ein Wurf von 9 m/s erscheint dort mit über 20). None, wenn weniger als drei Lagen da sind."""
    idx = np.arange(frame + 1, frame + 1 + span) if after else np.arange(frame - span, frame)
    idx = idx[(idx >= 0) & (idx < len(xyz))]
    idx = idx[~np.isnan(xyz[idx, 0])]
    if len(idx) < 3:
        return None
    t = idx / fps
    A = np.column_stack([np.ones_like(t), t - t.mean()])
    coef, *_ = np.linalg.lstsq(A, xyz[idx], rcond=None)
    return float(np.linalg.norm(coef[1]))


def throw_ins(result: list, kind: np.ndarray, pitch=PITCH) -> list:
    """Flüge, die an der Seitenlinie in Handhöhe nach einem Stehen (kein Rollen davor) beginnen."""
    half_width = pitch[1] / 2
    out = []
    for item in result:
        x, y, z = item["start_pos"]
        before = kind[max(0, item["start"] - 3):item["start"]]
        rolled = bool((before == 1).any())
        if item["reliable"] and abs(y) >= half_width - THROW_LINE_M and z >= THROW_MIN_Z and item["speed"] <= THROW_MAX_SPEED and not rolled:
            out.append({"kind": "throw-in", "time": item["t_start"], "pos": [x, y], "height": z})
    return out


def main(det_path, pitch=PITCH) -> dict:
    z = np.load(f"{det_path}.ball3d.npz")
    xyz, kind, fps = z["xyz"], z["kind"], float(z["fps"])
    result = outlook(xyz, kind, fps, pitch)
    contacts = []
    for c in z["contacts"]:
        v_in, v_out = (speed_near(xyz, int(c[0]), fps, after) for after in (False, True))
        contacts.append({"time": round(float(c[0]) / fps, 2), "speed_in": None if v_in is None else round(v_in, 1),
                         "speed_out": None if v_out is None else round(v_out, 1),
                         "kind": "unknown" if v_out is None else ball_events.classify(v_out), "confidence": round(float(c[4]), 2)})
    data = {"fps": fps, "pitch": list(pitch), "goal": [GOAL_WIDTH, GOAL_HEIGHT], "flights": result, "events": throw_ins(result, kind, pitch),
            "contacts": contacts,
            "note": "Fortsetzung = Wurfparabel ohne Luftwiderstand aus den letzten Lagen des Flugs; keine Messung."}
    Path(f"{det_path}.outlook.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    for it in result:
        cont = it["continuation"]
        goal = cont["goal_line"] if cont else None
        print(f"Flug {it['t_start']:.1f}–{it['t_end']:.1f} s, Höhe bis {it['apex']} m, {it['speed']} m/s" + ("" if it["reliable"] else " (unglaubwürdig, keine Fortsetzung)")
              + (f"; ohne Kontakt gelandet bei ({cont['landing']['x']}, {cont['landing']['y']})" if cont and cont["landing"] else "")
              + (f"; Torlinie: {goal['verdict']} (y {goal['y']}, z {goal['z']})" if goal else ""))
    for e in data["events"]:
        print(f"Einwurf bei {e['time']:.1f} s, Lage {e['pos']}, Höhe {e['height']} m")
    return data


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
