#!/usr/bin/env python3
"""Spielwerte und Spielbewertung je Spieler aus den gemessenen Bahnen einer Szene (oder eines ganzen Spiels).

Aus den Bahnen (tracks.bin, nur Positionen) und den Ballkontakten (meta.json `ballContacts`) werden je Spieler gemessen: Laufstrecke, Höchsttempo, Sprints, Ballkontakte.
Daraus entstehen zwei Dinge, beide nur aus Messwerten, nichts wird geschätzt oder eingetragen:
- Werte für das Spielerprofil (web/profile.js), soweit sie sich messen lassen: Tempo (aus dem Höchsttempo), Beschleunigung (aus der größten Beschleunigung), Ausdauer
  (aus der Laufstrecke je Minute im Vergleich zu den anderen). Alles andere (Dribbling, Zweikampf, Schuss, Passspiel) bleibt bei der Voreinstellung, bis es sich messen lässt.
- Eine Spielbewertung von 1 bis 10: wie viel ein Spieler in diesem Spiel im Vergleich zu den anderen geleistet hat (Mittel aus den Abständen zum Durchschnitt aller
  Spieler in jeder gemessenen Größe, 6 = Durchschnitt). Sie braucht genug Spieler (MIN_PEERS) und genug gesehene Zeit (MIN_SECONDS); sonst bleibt sie leer.

Eine kurze Szene (Sekunden) sagt über Ausdauer und Bewertung kaum etwas: Die Werte sind für ganze Spiele gedacht und werden bei zu wenig Zeit nicht ausgegeben.

Aufruf:
    .venv/bin/python tools/player_rating.py SZENENORDNER [--schreiben]
--schreiben legt `profile` (ratings, match) je Spieler in meta.json ab; der Viewer (web/spielen.html) liest die Werte von dort.
"""
import argparse
import json
from pathlib import Path

import numpy as np

SMOOTH_S = 0.5            # s: Fenster, über das die Geschwindigkeit geglättet wird (Spurrauschen)
SPRINT_MS = 5.5           # m/s: ab hier zählt ein Lauf als Sprint ...
SPRINT_MIN_S = 1.0        # ... wenn er mindestens so lange dauert
ACCEL_WINDOW_S = 1.0      # s: Fenster, über das die Beschleunigung gemessen wird
MIN_SECONDS = 30.0        # s gesehene Zeit, ab der Ausdauer und Bewertung etwas aussagen
MIN_PEERS = 4             # Spieler mit genug Daten, ab denen ein Vergleich möglich ist
PACE_RANGE = (4.6, 8.8)   # m/s: Höchsttempo, das Wert 0 und 99 entspricht (gleich wie physicsOf in web/profile.js)
ACCEL_RANGE = (2.0, 5.5)  # m/s²: größte Beschleunigung, die Wert 0 und 99 entspricht
STAMINA_AROUND = 70       # Ausdauerwert für die mittlere Laufstrecke je Minute; jede Standardabweichung mehr: +15
WEIGHTS = {"distancePerMin": 1.0, "topSpeed": 1.0, "sprintsPerMin": 0.7, "touchesPerMin": 0.8}   # Gewichte der Größen in der Bewertung


def smooth(v, n):
    """Gleitendes Mittel über n Bilder (NaN-fest: nur gültige Werte)."""
    if n <= 1:
        return v
    ok = ~np.isnan(v)
    k = np.ones(n)
    # numpy's "same" returns max(len(v), n) values. Crop the full
    # convolution explicitly so short tracks still produce one value per frame.
    start = (n - 1) // 2
    stop = start + len(v)
    num = np.convolve(np.where(ok, v, 0.0), k, "full")[start:stop]
    den = np.convolve(ok.astype(float), k, "full")[start:stop]
    with np.errstate(invalid="ignore", divide="ignore"):
        out = num / den
    out[den == 0] = np.nan
    return out


def speeds(xy, fps):
    """Geschwindigkeit (m/s) je Bild aus einer Spur (frames, 2); NaN, wo die Spur fehlt."""
    step = np.linalg.norm(np.diff(xy, axis=0), axis=1) * fps
    return smooth(np.concatenate([step, [np.nan]]), max(1, round(SMOOTH_S * fps)))


def sprint_count(v, fps):
    """Zahl der Sprints: zusammenhängende Läufe über SPRINT_MS von mindestens SPRINT_MIN_S."""
    fast = np.nan_to_num(v, nan=0.0) > SPRINT_MS
    count, run = 0, 0
    for f in list(fast) + [False]:
        if f:
            run += 1
        else:
            if run >= SPRINT_MIN_S * fps:
                count += 1
            run = 0
    return count


def stats_of(xy, fps, touches=0):
    """Messwerte eines Spielers aus seiner Spur (frames, 2). seconds = gesehene Zeit; Größen je Minute nur mit genug Zeit, sonst None."""
    seen = ~np.isnan(xy[:, 0])
    seconds = float(seen.sum()) / fps
    v = speeds(xy, fps)
    if seconds < 1.0 or np.isnan(v).all():
        return {"seconds": seconds, "distance": 0.0, "topSpeed": None, "maxAccel": None, "sprints": 0, "touches": touches}
    both = seen[:-1] & seen[1:]
    distance = float(np.nansum(np.where(both, np.linalg.norm(np.diff(xy, axis=0), axis=1), 0.0)))
    # Höchsttempo: 98. Perzentil der geglätteten Geschwindigkeit (ein einzelner Sprung der Spur zählt nicht)
    top = float(np.nanpercentile(v, 98))
    window = max(2, round(ACCEL_WINDOW_S * fps))
    accel = (v[window:] - v[:-window]) * fps / window if len(v) > window else np.array([np.nan])
    max_accel = float(np.nanpercentile(accel, 98)) if not np.isnan(accel).all() else None
    return {"seconds": seconds, "distance": distance, "topSpeed": top, "maxAccel": max_accel, "sprints": sprint_count(v, fps), "touches": touches}


def per_minute(s):
    """Größen je Minute oder None, wenn zu wenig Zeit gesehen wurde."""
    if s["seconds"] < MIN_SECONDS:
        return None
    m = s["seconds"] / 60.0
    return {"distancePerMin": s["distance"] / m, "topSpeed": s["topSpeed"], "sprintsPerMin": s["sprints"] / m, "touchesPerMin": s["touches"] / m}


def scale(x, lo, hi):
    return int(round(99 * min(1.0, max(0.0, (x - lo) / (hi - lo)))))


def ratings_of(stats, peers):
    """Profilwerte (0 bis 99) aus den Messwerten eines Spielers; nur, was sich messen lässt. peers: Liste der Größen je Minute der Vergleichsspieler (None-frei)."""
    out = {}
    if stats["topSpeed"] is not None and stats["seconds"] >= MIN_SECONDS:
        out["pace"] = scale(stats["topSpeed"], *PACE_RANGE)
    if stats["maxAccel"] is not None and stats["seconds"] >= MIN_SECONDS:
        out["acceleration"] = scale(stats["maxAccel"], *ACCEL_RANGE)
    pm = per_minute(stats)
    if pm and len(peers) >= MIN_PEERS:
        dist = np.array([p["distancePerMin"] for p in peers])
        sd = float(dist.std())
        if sd > 1e-6:
            out["stamina"] = int(round(min(99, max(1, STAMINA_AROUND + 15 * (pm["distancePerMin"] - dist.mean()) / sd))))
    return out


def match_rating(stats, peers):
    """Spielbewertung 1 bis 10 gegenüber den anderen: gewichtetes Mittel der Abstände zum Durchschnitt (in Standardabweichungen), 6 = Durchschnitt. None ohne genug Daten."""
    pm = per_minute(stats)
    if pm is None or len(peers) < MIN_PEERS:
        return None
    total, weight = 0.0, 0.0
    for key, w in WEIGHTS.items():
        values = np.array([p[key] for p in peers if p.get(key) is not None], float)
        if len(values) < MIN_PEERS or pm[key] is None:
            continue
        sd = float(values.std())
        if sd < 1e-9:
            continue
        total += w * (pm[key] - values.mean()) / sd
        weight += w
    if weight == 0:
        return None
    return round(float(min(10.0, max(1.0, 6.0 + 1.2 * total / weight))), 1)


def analyse(scene_dir):
    """Messwerte, Profilwerte und Bewertung für jeden Spieler der Szene: {id: {stats, ratings, match}}."""
    d = Path(scene_dir)
    meta = json.loads((d / "meta.json").read_text())
    t = meta["tracks"]
    raw = np.fromfile(d / t["file"], dtype="<i2").reshape(meta["frames"], len(meta["entities"]), 3)
    xy = raw[:, :, :2].astype(float) * t["scale"]
    xy[raw[:, :, 0] == t["missing"]] = np.nan
    touches = {}
    for c in meta.get("ballContacts", []):
        if c.get("player"):
            touches[c["player"]] = touches.get(c["player"], 0) + 1
    ids = [(i, e["id"]) for i, e in enumerate(meta["entities"]) if e["kind"] == "player"]
    stats = {pid: stats_of(xy[:, i], meta["fps"], touches.get(pid, 0)) for i, pid in ids}
    minute = {pid: per_minute(s) for pid, s in stats.items()}
    peers = [m for m in minute.values() if m]
    result = {}
    for pid, s in stats.items():
        others = [m for q, m in minute.items() if m and q != pid]
        result[pid] = {"stats": s, "ratings": ratings_of(s, others), "match": match_rating(s, others)}
    return meta, result


def main(a):
    meta, result = analyse(a.szene)
    for pid, r in result.items():
        s = r["stats"]
        top = f"{s['topSpeed'] * 3.6:.1f} km/h" if s["topSpeed"] else "–"
        print(f"{pid:16s} {s['seconds']:6.1f} s  {s['distance']:7.1f} m  Höchsttempo {top:>10s}  Sprints {s['sprints']:2d}  Kontakte {s['touches']:2d}  Werte {r['ratings']}  Bewertung {r['match']}")
    if a.schreiben:
        for e in meta["entities"]:
            if e["id"] in result:
                r = result[e["id"]]
                e["profile"] = {"ratings": r["ratings"], "match": {"rating": r["match"], "seconds": round(r["stats"]["seconds"], 1), "distance": round(r["stats"]["distance"], 1),
                                                                  "topSpeed": None if r["stats"]["topSpeed"] is None else round(r["stats"]["topSpeed"], 2),
                                                                  "sprints": r["stats"]["sprints"], "touches": r["stats"]["touches"]}}
        (Path(a.szene) / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
        print("-> meta.json (profile je Spieler)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("szene")
    ap.add_argument("--schreiben", action="store_true")
    main(ap.parse_args())
