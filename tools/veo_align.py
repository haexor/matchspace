#!/usr/bin/env python3
"""Bestimmt, wie Veos Positionsangaben auf dem echten Platz liegen.

Veo gibt Positionen als Anteil (0..1) eines Vierecks aus vier angeklickten Ecken an. Hier
wird die Abbildung dieser Anteile auf den echten Boden bestimmt (Homographie), dazu der
Zeitversatz zwischen Positionsdaten und Video. Grundlage sind Paare aus Veo-Position und
erkannter Person: Der Fußpunkt der Box wird über das Kameramodell (tools/veo_camera.py)
auf den Boden gerechnet. Zugeordnet wird getrennt nach Trikotfarbe, schrittweise enger.

Start: Veos vier Ecken aus camera_alignment.json, über unser Kameramodell auf den Boden gerechnet.

Aufruf:
    .venv/bin/python tools/veo_align.py VEO_ORDNER KAMERA.json AUSGABE.json START_S:DETEKTIONEN.json [...]
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import least_squares

sys.path.insert(0, str(Path(__file__).parent))
import veo_camera  # noqa: E402
import veo_tracks  # noqa: E402

LENSES = ("left", "right")
IDENTITY = np.eye(3)


def veo_corners(veo_dir, cam):
    """Veos angeklickte Ecken auf dem echten Boden: Anteil (x, y) -> Meter."""
    stacked = json.loads((Path(veo_dir) / "camera_alignment.json").read_text())["selected_corners"]["corners_stacked"]
    size = cam["lensSize"]
    out = {}
    for name, frac in (("cl", (0, 0)), ("cr", (1, 0)), ("fl", (0, 1)), ("fr", (1, 1))):
        for li, lens in enumerate(LENSES):
            c = stacked[name][lens]
            if c["valid"]:
                pixel = [c["stacked"][0] * size[0], c["stacked"][1] * 2 * size[1] - li * size[1]]
                out[frac] = veo_camera.to_ground(cam, lens, [pixel])[0][0]
    return out


def collect(clips, tracks, H, cam, gate, offset=0.0):
    """Paare (Veo-Anteil, Bodenpunkt der Box) über alle Bilder; dazu die Zahl sichtbarer Veo-Positionen."""
    L, W = cam["pitch"]["length"], cam["pitch"]["width"]
    frac, ground, total = [], [], 0
    for start, det in clips:
        for fr in det["frames"]:
            people = [(tid, p) for tid, p in veo_tracks.positions_at(tracks, start + fr["t"] + offset) if tracks[tid]["cls"] >= 0]
            metres = [(tid, veo_tracks.to_metres(H, p)[0]) for tid, p in people]
            where = dict(people)
            total += len(people)
            best = {}
            for lens in LENSES:
                b = np.array(fr[lens], float).reshape(-1, 6)
                if not len(b):
                    continue
                g, _ = veo_camera.to_ground(cam, lens, np.column_stack([(b[:, 0] + b[:, 2]) / 2, b[:, 3]]))
                g[(np.abs(g[:, 0]) > L / 2 + 5) | (np.abs(g[:, 1]) > W / 2 + 5)] = np.nan
                for tid, j, dist in veo_tracks.assign_ground(metres, tracks, g, b[:, 5], gate):
                    if tid not in best or dist < best[tid][0]:
                        best[tid] = (dist, g[j])
            for tid, (_, point) in best.items():
                frac.append(where[tid])
                ground.append(point)
    return np.array(frac).reshape(-1, 2), np.array(ground).reshape(-1, 2), total


def main(veo_dir, camera_path, out_path, *clip_args):
    cam = veo_camera.load(camera_path)
    export = veo_tracks.load_export(veo_dir)
    tracks = veo_tracks.build_tracks(export, IDENTITY)  # Positionen bleiben hier Veo-Anteile
    clips = []
    for arg in clip_args:
        start, path = arg.split(":", 1)
        clips.append((float(start), json.loads(Path(path).read_text())))

    corners = veo_corners(veo_dir, cam)
    L, W = cam["pitch"]["length"], cam["pitch"]["width"]
    print("Veos angeklickte Ecken liegen auf dem echten Platz bei (echte Ecke, Abstand):")
    for (fx, fy), point in corners.items():
        real = np.array([(fx - 0.5) * L, (fy - 0.5) * W])
        print(f"  {'nah' if fy == 0 else 'fern'} {'links' if fx == 0 else 'rechts'}: {point[0]:+.1f} / {point[1]:+.1f} m  "
              f"(echt {real[0]:+.1f} / {real[1]:+.1f}, {np.linalg.norm(point - real):.1f} m daneben)")
    H = cv2.getPerspectiveTransform(np.array(list(corners), np.float32), np.array(list(corners.values()), np.float32)).astype(float)

    def fit(H, frac, ground):
        res = least_squares(lambda h: (veo_tracks.to_metres(np.append(h, 1).reshape(3, 3), frac) - ground).ravel(),
                            (H / H[2, 2]).ravel()[:8], loss="soft_l1", f_scale=0.5, x_scale="jac")
        return np.append(res.x, 1).reshape(3, 3)

    for gate in (3.0, 2.0, 1.5, 1.5):
        frac, ground, _ = collect(clips, tracks, H, cam, gate)
        H = fit(H, frac, ground)

    # Zeitversatz: der Versatz, bei dem die meisten Positionen eine Erkennung in 1 m Umkreis haben
    rates = {}
    for offset in np.arange(-1.2, 1.21, 0.2):
        frac, _, total = collect(clips, tracks, H, cam, 1.0, offset)
        rates[round(float(offset), 1)] = len(frac) / max(1, total)
    offset = max(rates, key=rates.get)
    print("Anteil zugeordneter Positionen je Zeitversatz (s):", {k: round(v, 3) for k, v in rates.items()})
    for gate in (1.5, 1.5):
        frac, ground, _ = collect(clips, tracks, H, cam, gate, offset)
        H = fit(H, frac, ground)

    frac, ground, total = collect(clips, tracks, H, cam, 3.0, offset)
    err = np.linalg.norm(veo_tracks.to_metres(H, frac) - ground, axis=1)
    frame = veo_tracks.to_metres(H, [[0, 0], [1, 0], [0, 1], [1, 1], [0.5, 0.5]])
    result = {"H": H.tolist(), "timeOffsetS": offset, "pairs": len(err), "positions": total,
              "medianErrorM": float(np.median(err)), "p90ErrorM": float(np.percentile(err, 90)),
              "veoFrame": {"corners": frame[:4].tolist(), "centre": frame[4].tolist()},
              "note": "H bildet Veo-Anteile (x, y) auf Meter ab; Zeit im Video = Veo-Zeit - timeOffsetS"}
    Path(out_path).write_text(json.dumps(result, indent=1))
    print(f"{len(err)} von {total} Veo-Positionen haben eine Erkennung im Umkreis von 3 m ({len(err) / total:.0%}); "
          f"Abstand Median {np.median(err):.2f} m, 90 % unter {np.percentile(err, 90):.2f} m; Zeitversatz {offset:+.1f} s")
    print(f"Veos Feld auf dem echten Platz: {np.linalg.norm(frame[1] - frame[0]):.1f} m (nah) und {np.linalg.norm(frame[3] - frame[2]):.1f} m (fern) lang, "
          f"{np.linalg.norm(frame[2] - frame[0]):.1f} m (links) und {np.linalg.norm(frame[3] - frame[1]):.1f} m (rechts) breit; Veo rechnet mit 105 × 65,4 m")
    print(f"-> {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 5:
        sys.exit(__doc__)
    main(*sys.argv[1:])
