#!/usr/bin/env python3
"""Erzeugt Körperhaltungen allein aus den Laufwegen eines Spiels, ohne Videoanalyse.

Jede Figur bekommt eine natürliche Bewegung passend zu Tempo und Laufrichtung: Stehen, Gehen,
Laufen aus aufgezeichneten Bewegungen eines Menschen (tools/motion_clips.py). Das ist ein
Platzhalter für Spiele, zu denen es nur Positionen gibt. Schüsse, Zweikämpfe, Sprünge oder
Paraden zeigt er nicht.

Aufruf:
    .venv/bin/python tools/synth_poses.py web/data/game1 [MINUTEN]
"""
import json
import math
import sys
from pathlib import Path

CHUNK_FRAMES = 1500
POSE_SCALE = 0.001  # 1 Einheit = 1 mm, relativ zur Spielerposition am Boden
MISSING = -32768

JOINTS = [
    # Name, Kugelradius in m, Körperteil (bestimmt die Farbe)
    ("pelvis", 0.10, "shorts"), ("neck", 0.06, "shirt"), ("head", 0.11, "skin"), ("nose", 0.025, "skin"),
    ("lShoulder", 0.06, "shirt"), ("rShoulder", 0.06, "shirt"),
    ("lElbow", 0.042, "skin"), ("rElbow", 0.042, "skin"),
    ("lWrist", 0.04, "skin"), ("rWrist", 0.04, "skin"),
    ("lHip", 0.085, "shorts"), ("rHip", 0.085, "shorts"),
    ("lKnee", 0.055, "skin"), ("rKnee", 0.055, "skin"),
    ("lAnkle", 0.045, "sock"), ("rAnkle", 0.045, "sock"),
    ("lHeel", 0.04, "boot"), ("rHeel", 0.04, "boot"),
    ("lToe", 0.035, "boot"), ("rToe", 0.035, "boot"),
]
NAMES = [j[0] for j in JOINTS]
BONES = [
    # von, nach, Radius in m, Körperteil
    ("pelvis", "neck", 0.13, "shirt"), ("lShoulder", "rShoulder", 0.06, "shirt"),
    ("lHip", "rHip", 0.085, "shorts"), ("neck", "head", 0.045, "skin"),
    ("lShoulder", "lElbow", 0.045, "shirt"), ("rShoulder", "rElbow", 0.045, "shirt"),
    ("lElbow", "lWrist", 0.036, "skin"), ("rElbow", "rWrist", 0.036, "skin"),
    ("lHip", "lKnee", 0.07, "shorts"), ("rHip", "rKnee", 0.07, "shorts"),
    ("lKnee", "lAnkle", 0.05, "sock"), ("rKnee", "rAnkle", 0.05, "sock"),
    ("lAnkle", "lHeel", 0.04, "boot"), ("rAnkle", "rHeel", 0.04, "boot"),
    ("lHeel", "lToe", 0.04, "boot"), ("rHeel", "rToe", 0.04, "boot"),
]


def main(match_dir, minutes=None):
    import numpy as np
    sys.path.insert(0, str(Path(__file__).parent))
    import foot_planting
    import pose_fit
    import pose_limits

    match_dir = Path(match_dir)
    meta_path = match_dir / "meta.json"
    meta = json.loads(meta_path.read_text())
    fps, n, entities = meta["fps"], meta["frames"], meta["entities"]
    scale, miss = meta["tracks"]["scale"], meta["tracks"]["missing"]
    data = np.fromfile(match_dir / meta["tracks"]["file"], "<i2").reshape(n, len(entities), 3)
    players = [i for i, e in enumerate(entities) if e["kind"] == "player"]
    ball = next(i for i, e in enumerate(entities) if e["kind"] == "ball")
    frames = n if minutes is None else min(n, int(float(minutes) * 60 * fps))

    def track(entity):
        xy = data[:frames, entity, :2].astype(float) * scale
        xy[data[:frames, entity, 0] == miss] = np.nan
        return xy

    ball_xy = track(ball)
    chunks = math.ceil(frames / CHUNK_FRAMES)
    J = len(JOINTS)
    out = np.full((chunks * CHUNK_FRAMES, len(players), J, 3), MISSING, np.int16)
    for slot, entity in enumerate(players):
        pos = track(entity)
        present = ~np.isnan(pos[:, 0])
        if not present.any():
            continue
        lengths = pose_limits.bone_lengths(1.62 + 0.17 * ((slot * 7919) % 11) / 10)
        d, _ = pose_fit.natural_motion(pos, ball_xy, fps, lengths, start_phase=slot * 1.7)
        d = pose_limits.limit_directions(pose_limits.limit_turn(d, fps))
        d, pos = pose_limits.balance_depth(d, lengths, pos, None, fps)   # in Beschleunigung und Kurve hineinlegen
        d = pose_limits.limit_directions(d)
        joints, *_ = foot_planting.plant_feet(pose_limits.build(d, lengths), pos, fps, lengths)
        joints = pose_limits.build(pose_limits.limit_directions(pose_limits.directions_of(joints)), lengths)   # Festhalten der Füße darf nichts überdehnen
        out[:frames, slot][present] = np.clip(np.round(joints[present] / POSE_SCALE), -32767, 32767).astype(np.int16)
        print(f"\r{slot + 1}/{len(players)} Figuren", end="", flush=True)
    print()
    out_dir = match_dir / "poses"
    out_dir.mkdir(exist_ok=True)
    for old in out_dir.glob("*.bin"):
        old.unlink()
    for c in range(chunks):
        out[c * CHUNK_FRAMES:(c + 1) * CHUNK_FRAMES].astype("<i2").tofile(out_dir / f"{c:03d}.bin")

    meta["version"] = 1
    meta["poses"] = {
        "synthetic": True,
        "source": "Natürliche Bewegung aus den Laufwegen (tools/synth_poses.py, Vorlagen aus tools/motion_clips.py)",
        "path": "poses/{chunk}.bin",
        "chunkFrames": CHUNK_FRAMES,
        "chunks": chunks,
        "dtype": "int16le",
        "layout": "frame, player, joint, [x, y, z]",
        "relativeTo": "track",
        "scale": POSE_SCALE,
        "missing": MISSING,
        "skeleton": {
            "joints": [{"name": n_, "radius": r, "part": part} for n_, r, part in JOINTS],
            "bones": [{"from": NAMES.index(a), "to": NAMES.index(b), "radius": r, "part": part}
                      for a, b, r, part in BONES],
        },
    }
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    print(f"{chunks} Pose-Dateien -> {out_dir}")


if __name__ == "__main__":
    if len(sys.argv) not in (3, 2):
        sys.exit(__doc__)
    main(*sys.argv[1:])
