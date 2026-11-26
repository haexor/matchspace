"""Spielstand der Szene und Positionen der Spieler (Basisspiel und Stufe „Eigene Position“ von tools/veo_scene.py).

Mit Veo liefert das Basisspiel Veo-Positionen (25 Hz), die hier durch die eigene Messung ersetzt werden. Ohne Veo genügt ein
eigener Spielordner (tools/own_match.py): nur Spielabschnitte, Uhr, Platz, Mannschaften; Bewegungsdaten werden nicht gelesen.
Eigene Position ist der Fußpunkt am Boden. Veo füllt die Lücken, verschoben um den zuletzt gemessenen Unterschied, damit
nichts springt.
"""
import json
import sys
from array import array
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.signal import savgol_filter

sys.path.insert(0, str(Path(__file__).parent))
import ball_motion  # noqa: E402
import track_limits  # noqa: E402
import veo_camera  # noqa: E402
from own_match import period_at  # noqa: E402
from own_scene import BALL_GAP, own_ball, player_entity  # noqa: E402
from scene_boxes import LENSES  # noqa: E402
from scene_util import resample, running_median, segments  # noqa: E402

OUT_FPS = 25
DEFAULT_HEIGHT = 1.70
DEPTH_CALM = 36000.0  # Gewicht der Ruhe in Blickrichtung: Schwankungen des Abstands schneller als rund 0,3 Hz gelten als Rauschen


@dataclass
class Game:
    """Spielstand der Szene im Takt der Ausgabe. xy: Lage je Ausgabebild und Figur (total, Figuren, 2); data: Rohwerte des
    Basisspiels (Bahnen int16); slots: Figuren, die Spieler sind; entity_of: Kennung -> Figur; ball: Figur des Balls oder None."""
    base: dict
    base_dir: Path
    out_dir: Path
    period: dict
    clock_start: float
    total: int
    ratio: float
    tscale: float
    data: array
    xy: np.ndarray
    slots: list
    entity_of: dict
    ball: int | None
    ball_source: str
    ball_track: object = None   # tools/ball_motion.OutputTrack: Ball mit Höhe und Kontakten, wenn `.ball3d.npz` vorliegt


def feet_on_ground(cam, eye, kp, lens, height):
    """Bodenpunkt unter dem Becken aus Gelenkpunkten (n, 17, 3); NaN, wo Hüften oder Knöchel nicht sicher erkannt sind.

    Ein Fuß in der Luft erscheint weiter weg, als er ist. Der Abstand zur Kamera kommt deshalb vom näheren
    der beiden Knöchel (der steht), der andere zählt höchstens 0,2 m mit."""
    out = np.full((len(kp), 2), np.nan)
    ankle_height, hip_height = 0.07 * height / 1.70, 0.51 * height
    for li, name in enumerate(LENSES):
        m = (lens == li) & (np.nan_to_num(kp[:, [11, 12, 15, 16], 2]) >= 0.5).all(axis=1)
        if not m.any():
            continue
        reach = np.stack([np.linalg.norm(veo_camera.to_ground(cam, name, kp[m, a, :2], ankle_height)[0] - eye[:2], axis=1) for a in (15, 16)])
        near, far = np.nanmin(reach, axis=0), np.nanmax(reach, axis=0)
        distance = near + np.minimum((far - near) / 2, 0.2)
        hips = veo_camera.to_ground(cam, name, (kp[m, 11, :2] + kp[m, 12, :2]) / 2, hip_height)[0] - eye[:2]
        out[m] = eye[:2] + hips / np.maximum(np.linalg.norm(hips, axis=1, keepdims=True), 1e-9) * distance[:, None]
    return out


def smooth_track(pos, eye, sideways=True):
    """Glättet eine Bahn (n, 2), in Blickrichtung der Kamera viel stärker als quer dazu.

    Ein Pixel im Bild sind quer zur Blickrichtung wenige Zentimeter, in die Tiefe aber rund 0,3 m: Der Abstand
    zur Kamera ist viel ungenauer gemessen als die seitliche Lage. In Blickrichtung gilt deshalb die ruhigste
    Bahn, die zu den Messungen passt (gleichmäßiges Tempo bleibt erhalten, Beschleunigungen werden über gut
    eine Sekunde verteilt); sonst käme aus dem Messrauschen ein Hin und Her, in das sich die Figur legen müsste."""
    if len(pos) < 9:
        return pos
    rel = pos - eye[:2]
    reach, angle = np.linalg.norm(rel, axis=1), np.unwrap(np.arctan2(rel[:, 1], rel[:, 0]))
    reach = track_limits._solve(reach, np.full(len(pos) - 2, DEPTH_CALM), np.zeros(len(pos) - 1))
    if sideways:
        angle = savgol_filter(angle, min(15, len(pos) // 2 * 2 - 1), 2)
    return eye[:2] + reach[:, None] * np.column_stack([np.cos(angle), np.sin(angle)])


def load_game(run, observed, base_dir, out_dir) -> Game:
    """Spielstand der Szene aus dem Basisspiel. Mit Veo: Veo-Positionen. Ohne Veo: Spieler sind die eigenen Spuren, ihre Lage
    die eigene Spur (Lücken gerade verbunden); dazu der Ball. Vom Basisspiel bleiben dann nur Platz, Kulisse, Mannschaftsnamen
    und Uhr."""
    n, fps, det_path = run.n, run.fps, run.det_path
    where, obs, keepers = observed.where, observed.obs, observed.keepers
    base_dir, out_dir = Path(base_dir), Path(out_dir)
    base = json.loads((base_dir / "meta.json").read_text())
    E = len(base["entities"])
    period, clock_start = period_at(base["periods"], run.start)
    total = int(n / fps * OUT_FPS)
    ratio = fps / OUT_FPS
    tscale = base["tracks"]["scale"]
    if not run.no_veo:
        first = period["startFrame"] + round((run.start - period["videoStartS"]) * base["fps"])
        data = array("h")
        with open(base_dir / base["tracks"]["file"], "rb") as f:
            f.seek(first * E * 3 * 2)
            data.fromfile(f, total * E * 3)
        xy = np.array(data, float).reshape(total, E, 3)
        xy = np.where(xy == base["tracks"]["missing"], np.nan, xy * tscale)[:, :, :2]
    if run.no_veo:
        entities = []
        names = Counter()
        for key in sorted(obs, key=lambda k: (k[0], k[1])):
            names[key[0]] += 1
            entities.append(player_entity(key, key in keepers, names[key[0]]))
        entities.append({"id": "ball", "kind": "ball"})
        base["entities"] = entities
        E = len(entities)
        data = array("h", [base["tracks"]["missing"]]) * (total * E * 3)
        xy = np.full((total, E, 2), np.nan)
        for i, key in enumerate(sorted(obs, key=lambda k: (k[0], k[1]))):
            spot = np.full((n, 2), np.nan)
            for fi, p in ((fi, where[fi][key]) for fi in range(n) if key in where[fi]):
                spot[fi] = p
            xy[:, i] = resample(spot, total, ratio)
    slots = [i for i, e in enumerate(base["entities"]) if e["kind"] == "player"]
    entity_of = {e["id"]: i for i, e in enumerate(base["entities"])}
    ball = next((i for i, e in enumerate(base["entities"]) if e["kind"] == "ball"), None)
    ball_source = "Veo"
    if ball is not None and Path(f"{det_path}.ball.npz").exists():   # eigener Ball aus dem Video (tools/veo_ball.py) statt Veos
        xy[:, ball] = own_ball(resample(np.load(f"{det_path}.ball.npz")["pos"], total, ratio), BALL_GAP * OUT_FPS)
        ball_source = "Video"
    track = None
    if ball is not None and Path(f"{det_path}.ball3d.npz").exists():   # Ball mit Höhe aus der Physik (tools/ball_motion.py)
        track = ball_motion.output_track(f"{det_path}.ball3d.npz", total, ratio)
        xy[:, ball], track.z = ball_motion.bridge(track.xy, track.z, OUT_FPS, xy[:, slots])   # nur die Bahn der Physik: die Bodenlage der Rohspur wäre im Flug verzerrt
    return Game(base, base_dir, out_dir, period, clock_start, total, ratio, tscale, data, xy, slots, entity_of, ball, ball_source, track)


def measure_positions(run, observed, joints, floor, game: Game) -> None:
    """Eigene Position: Fußpunkt am Boden, aus den Gelenkpunkten verfeinert, am Boden das Becken; Veo füllt die Lücken,
    verschoben um den zuletzt gemessenen Unterschied. Schreibt in game.xy."""
    cam_pos, cam, obs = run.cam_pos, run.cam, observed.obs
    kp2d, boxed, body = joints.kp2d, joints.boxed, joints.body
    xy, total, ratio, entity_of, slots = game.xy, game.total, game.ratio, game.entity_of, game.slots
    veo_speed, own_speed, measured_share, refined = [], [], {}, 0
    for key, b in obs.items():
        entity = entity_of.get(f"{key[0]}-{key[1]}")
        if entity is None or np.isnan(b[:, 5]).all():
            continue
        point = b[:, 5:7].copy()
        # Genauer als die Unterkante der Box (die oft einen Nachbarn mit umfasst) sind die Gelenkpunkte: seitliche Lage
        # aus der Hüftmitte, Abstand zur Kamera aus dem Fuß, der auf dem Rasen steht.
        if key in kp2d:
            feet = feet_on_ground(cam, cam_pos, kp2d[key], b[:, 0], body.get(key, DEFAULT_HEIGHT))
            better = boxed[key] & ~np.isnan(feet[:, 0]) & (np.linalg.norm(feet - point, axis=1) < 3.0)
            point[better] = feet[better]
            refined += int(better.sum())
        if key in floor:  # am Boden zählt das Becken, nicht die Unterkante der Box
            lying = ~np.isnan(floor[key][:, 0, 0])
            point[lying] = floor[key][lying, 0, :2]
        own = resample(point, total, ratio)
        veo = xy[:, entity].copy()
        offset = own - veo
        for a in range(2):
            m = running_median(offset[:, a], 9)
            offset[np.abs(offset[:, a] - m) > 1.5, :] = np.nan
        seen = ~np.isnan(offset[:, 0])
        if seen.sum() < 5:
            continue
        idx = np.arange(total)
        offset = np.column_stack([np.interp(idx, idx[seen], offset[seen, a]) for a in range(2)])
        pos = veo + offset
        there = ~np.isnan(pos[:, 0])
        for a, e in segments(there, 9):
            pos[a:e] = track_limits.physical(smooth_track(pos[a:e], cam_pos), OUT_FPS)
            if e - a > 15:
                step = int(OUT_FPS * 0.4)
                veo_speed.append(np.linalg.norm(veo[a + step:e] - veo[a:e - step], axis=1) / 0.4)
                own_speed.append(np.linalg.norm(pos[a + step:e] - pos[a:e - step], axis=1) / 0.4)
        xy[:, entity] = pos
        measured_share[key] = seen.mean()
    for i in slots:
        if not any(entity_of.get(f"{k[0]}-{k[1]}") == i for k in measured_share):
            xy[:, i] = track_limits.clean(xy[:, i], OUT_FPS)
    print(f"Position in {refined} Bildern aus den Gelenkpunkten statt aus der Box bestimmt", flush=True)
    if own_speed:
        v, o = np.concatenate(veo_speed), np.concatenate(own_speed)
        print(f"Tempo über 0,4 s gemittelt, {len(measured_share)} Spieler: höchstes laut Veo {np.nanmax(v) * 3.6:.1f} km/h, "
              f"aus eigenen Positionen {np.nanmax(o) * 3.6:.1f} km/h; 99. Perzentil {np.nanpercentile(v, 99) * 3.6:.1f} und {np.nanpercentile(o, 99) * 3.6:.1f} km/h", flush=True)
    game.out_dir.mkdir(parents=True, exist_ok=True)
    run.clock("Positionen")
