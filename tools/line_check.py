#!/usr/bin/env python3
"""Lage am Boden ohne Veo prüfen: Steht ein Fuß auf einer Platzlinie, ist seine wahre Lage bekannt.

Linienstelle (specs/003-eigene-referenz/research.md R5): Das stehende Fußgelenk (das untere, über 3 Bilder ruhig)
liegt im Bild höchstens NEAR_PX neben einer Linie des Normplatzes, und die Linie ist dort im Hintergrundbild
wirklich hell. Die wahre Lage ist der Punkt der Linie unter dem Fuß. Je Quelle wird der Abstand dazu in der Tiefe
(Blickrichtung der Kamera, positiv = weiter weg) und quer dazu gemessen:
  - scene: Lage der fertigen Szene (tracks.bin);
  - box: Mitte der Boxunterkante am Boden (wie das Tracking);
  - feet: Bodenpunkt aus den Gelenkpunkten (scene_positions.feet_on_ground, wie die fertige Szene ihn misst);
  - veo: nächster Veo-Spieler, nur mit --veo (zweite Meinung).
Körpermitte und stehender Fuß liegen bis rund 0,3 m auseinander; das mittelt sich über viele Stellen aus, ein fester
Versatz bleibt sichtbar.

Aufruf:
    .venv/bin/python tools/line_check.py SZENENVIDEO DETEKTIONEN.json KAMERA.json SZENE_ORDNER [--veo VEO_ORDNER VEO_ALIGN.json START_S] [--bericht B.json]
"""
import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).parent))
import veo_camera  # noqa: E402

NEAR_PX = 1.5        # px: so nah muss das Fußgelenk an der Linie liegen
STILL_PX = 2.0       # px: so wenig darf es sich zum Bild davor und danach bewegen
MIN_CONF = 0.5       # Mindestsicherheit der Gelenkpunkte
ANKLE_HEIGHT = 0.07  # m: Höhe des Fußgelenks über dem Boden (wie scene_positions.feet_on_ground)
PER_SECOND = 3       # höchstens so viele Stellen je Spieler und Sekunde
BRIGHT = 12.0        # Linie muss im Hintergrundbild so viel heller sein als ihre Umgebung
SOURCES = ("scene", "box", "feet", "veo")


@dataclass
class LineSpot:
    frame: int
    lens: int
    box: int
    player: str
    line: str
    truth: np.ndarray


def line_index(cam, length: float, width: float) -> dict:
    """Je Linse: Suchbaum der Linienpunkte im Bild (in Knöchelhöhe projiziert), Liniennamen, Bodenpunkte."""
    out = {}
    lines = veo_camera.model_lines(length, width, step=0.02)
    for li, lens in enumerate(veo_camera.LENSES):
        uv, names, world = [], [], []
        for name, pts in lines.items():
            if name.startswith("bar"):
                continue
            p = veo_camera.project(cam, lens, np.column_stack([pts[:, :2], np.full(len(pts), ANKLE_HEIGHT)]))
            ok = ~np.isnan(p).any(axis=1)
            uv.append(p[ok])
            names += [name] * int(ok.sum())
            world.append(pts[ok, :2])
        out[li] = (cKDTree(np.concatenate(uv)), np.array(names), np.concatenate(world))
    return out


def on_line(index: Mapping, lens: int, uv) -> tuple[str, np.ndarray, float]:
    """Nächste Linie zu einem Bildpunkt: Name, Bodenpunkt, Abstand im Bild (px)."""
    tree, names, world = index[lens]
    d, i = tree.query(np.asarray(uv, float))
    return str(names[i]), world[i], float(d)


def still(before, now, after) -> bool:
    """Steht der Fuß? Bewegung zum Bild davor und danach höchstens STILL_PX."""
    if before is None or after is None:
        return False
    now = np.asarray(now, float)
    return bool(np.linalg.norm(now - before) <= STILL_PX and np.linalg.norm(now - after) <= STILL_PX)


def visible(bright: np.ndarray, uv) -> bool:
    """Ist die Linie an dieser Stelle im Hintergrundbild zu sehen (heller als die Umgebung)?"""
    u, v = int(round(uv[0])), int(round(uv[1]))
    if not (2 <= v < bright.shape[0] - 2 and 2 <= u < bright.shape[1] - 2):
        return False
    around = np.median(bright[max(0, v - 8):v + 9, max(0, u - 8):u + 9])
    return bool(bright[v - 1:v + 2, u - 1:u + 2].max() - around >= BRIGHT)


def thin(spots: Sequence[LineSpot], fps: float) -> list[LineSpot]:
    """Höchstens PER_SECOND Stellen je Spieler und Sekunde, damit wenige Spieler das Ergebnis nicht beherrschen."""
    count: dict = {}
    out = []
    for s in sorted(spots, key=lambda s: s.frame):
        key = (s.player, int(s.frame // fps))
        if count.get(key, 0) < PER_SECOND:
            count[key] = count.get(key, 0) + 1
            out.append(s)
    return out


def depth_across(point, truth, eye) -> tuple[float, float]:
    """Abstand point - truth in Blickrichtung der Kamera (positiv = weiter weg) und quer dazu (m)."""
    ray = np.asarray(truth, float) - eye
    ray /= np.linalg.norm(ray)
    d = np.asarray(point, float) - truth
    return float(d @ ray), float(d[0] * ray[1] - d[1] * ray[0])


def summary(errors: Sequence[Mapping[str, tuple[float, float]]]) -> dict:
    """Median und Streuung (25.–75. Perzentil) des Tiefenfehlers, Median des Querfehlers, je Quelle."""
    out = {}
    for src in SOURCES:
        vals = np.array([e[src] for e in errors if src in e and np.isfinite(e[src]).all()], float).reshape(-1, 2)
        if len(vals):
            q1, q3 = np.percentile(vals[:, 0], [25, 75])
            out[src] = {"spots": int(len(vals)), "depthMedian": round(float(np.median(vals[:, 0])), 3),
                        "depthIqr": round(float(q3 - q1), 3), "acrossMedian": round(float(np.median(np.abs(vals[:, 1]))), 3)}
    return out


def find(identity: Mapping, kp: np.ndarray, kp_index: np.ndarray, index: Mapping, bright: Sequence[np.ndarray] | np.ndarray,
         fps: float) -> list[LineSpot]:
    """Linienstellen aller Spieler: unteres Fußgelenk ruhig, auf einer Linie, Linie sichtbar."""
    spots = []
    for name, p in identity["players"].items():
        dets = [tuple(d) for d in p["detections"]]
        ankles = {}
        for f, lens, box in dets:
            row = kp[kp_index[f, lens, 0] + box]
            ok = row[[15, 16], 2] >= MIN_CONF
            if ok.any():
                k = 15 + int(np.argmax(np.where(ok, row[[15, 16], 1], -np.inf)))   # das untere steht
                ankles[f] = (lens, box, row[k, :2])
        for f, (lens, box, uv) in ankles.items():
            prev, nxt = ankles.get(f - 1), ankles.get(f + 1)
            if not still(prev[2] if prev and prev[0] == lens else None, uv, nxt[2] if nxt and nxt[0] == lens else None):
                continue
            line, truth, dist = on_line(index, lens, uv)
            image = bright[lens] if isinstance(bright, (list, tuple)) else bright
            if dist <= NEAR_PX and visible(image, uv):
                spots.append(LineSpot(f, lens, box, name, line, truth))
    return thin(spots, fps)


def main(argv: list[str] | None = None) -> None:
    import jersey_eval
    import jersey_reader
    import scene_positions
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    for name in ("video", "det", "camera", "scene"):
        ap.add_argument(name)
    ap.add_argument("--veo", nargs=3, metavar=("VEO_ORDNER", "VEO_ALIGN", "START_S"))
    ap.add_argument("--bericht")
    args = ap.parse_args(argv)
    report_path = jersey_reader.check_private_dir(args.bericht) if args.bericht else None
    cam = veo_camera.load(args.camera)
    det = json.loads(Path(args.det).read_text())
    identity = json.loads(Path(f"{args.det}.identity.json").read_text())
    with np.load(f"{args.det}.keypoints.npz") as k:
        kp, kp_index = k["kp"], k["index"]
    fps = det["fps"]
    background = veo_camera.background(args.video)
    half = background.shape[0] // 2
    bright = [veo_camera.brightness(background[li * half:(li + 1) * half]) for li in range(2)]
    index = line_index(cam, cam["pitch"]["length"], cam["pitch"]["width"])
    spots = find(identity, kp, kp_index, index, bright, fps)
    eye = np.asarray(cam["position"][:2], float)
    meta, xy = jersey_eval.load_scene(Path(args.scene))
    column = {e["id"]: i for i, e in enumerate(meta["entities"])}
    veo_at = jersey_eval.reference(*args.veo[:2]) if args.veo else None
    errors = []
    for s in spots:
        e = {}
        b = det["frames"][s.frame][veo_camera.LENSES[s.lens]][s.box]
        lens = veo_camera.LENSES[s.lens]
        g, _ = veo_camera.to_ground(cam, lens, [[(b[0] + b[2]) / 2, b[3]]])
        e["box"] = depth_across(g[0], s.truth, eye)
        row = kp[kp_index[s.frame, s.lens, 0] + s.box][None]
        feet = scene_positions.feet_on_ground(cam, cam["position"], row, np.array([s.lens]), scene_positions.DEFAULT_HEIGHT)
        if np.isfinite(feet).all():
            e["feet"] = depth_across(feet[0], s.truth, eye)
        t = det["frames"][s.frame]["t"]
        i = int(round(t * meta["fps"]))
        if s.player in column and i < len(xy) and np.isfinite(xy[i, column[s.player]]).all():
            e["scene"] = depth_across(xy[i, column[s.player]], s.truth, eye)
        if veo_at is not None:
            near = min(veo_at(float(args.veo[2]) + t).values(), key=lambda q: np.linalg.norm(q - g[0]), default=None)
            if near is not None and np.linalg.norm(near - g[0]) < 2.0:
                e["veo"] = depth_across(near, s.truth, eye)
        errors.append(e)
    result = {"spots": len(spots), "lines": dict(sorted(((l, sum(1 for s in spots if s.line == l)) for l in {s.line for s in spots}),
                                                          key=lambda kv: -kv[1])), "sources": summary(errors)}
    print(f"{len(spots)} Linienstellen ({', '.join(f'{k} {v}' for k, v in result['lines'].items())})")
    for src, v in result["sources"].items():
        print(f"  {src:6s} {v['spots']:4d} Stellen: Tiefe Median {v['depthMedian']:+.2f} m (Streuung {v['depthIqr']:.2f} m), "
              f"quer Median {v['acrossMedian']:.2f} m")
    if report_path:
        old = json.loads(report_path.read_text()) if report_path.exists() else {}
        old["lines"] = result
        report_path.write_text(json.dumps(old, indent=2, ensure_ascii=False) + "\n")
        print(f"-> {report_path}")


if __name__ == "__main__":
    main()
