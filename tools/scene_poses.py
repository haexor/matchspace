"""Haltung je Spieler (Stufen 4 und 5 von tools/veo_scene.py).

Je Spieler wird die Bewegung gesucht, die im Kamerabild auf den Gelenkpunkten liegt und in allem, was das Bild offen lässt
(Tiefe, verdeckte Gelenke, Lücken), einer natürlichen Bewegung im Takt der sichtbaren Schritte folgt (tools/pose_fit.py).
Danach Grenzen des Körpers (tools/pose_limits.py), Glättung, Boden: Jede Figur hat in jedem Bild ein vollständiges,
mögliches Skelett. Stehende Füße bleiben an ihrer Stelle.
"""
import math
import os
import sys
from array import array
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import body_build  # noqa: E402
import body_pose  # noqa: E402
import foot_fit  # noqa: E402
import foot_planting  # noqa: E402
import overlap  # noqa: E402
import ground_motion  # noqa: E402
import pose_fit  # noqa: E402
import pose_limits  # noqa: E402
import track_limits  # noqa: E402
import veo_camera  # noqa: E402
from own_scene import MIN_APPEARANCE  # noqa: E402
from scene_positions import DEFAULT_HEIGHT, OUT_FPS, smooth_track  # noqa: E402
from scene_util import resample_keypoints, segments  # noqa: E402
from synth_poses import JOINTS, NAMES  # noqa: E402

SEEN_SHARE = 0.6      # Anteil erkannter Gelenke, ab dem ein Bild als "aus dem Video gelesen" zählt
POSE_SCALE, MISSING, CHUNK_FRAMES = 0.001, -32768, 1500


@dataclass
class PoseResult:
    """Ergebnis der Haltungsrechnung. buf: Gelenke aller Figuren, int16 in Stücken zu CHUNK_FRAMES Bildern; toes: Fußspitzen
    für den Ball; views: 2D-Gelenkpunkte je Spieler im Takt der Ausgabe; die übrigen Felder sind Zähler für den Bericht."""
    buf: array
    toes: list
    views: dict
    estimated: int = 0
    present_total: int = 0
    summary: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    backward_frames: int = 0
    stats: Counter = field(default_factory=Counter)
    grounded: int = 0
    slip_before: float = 0.0
    slip_after: float = 0.0
    slip_frames: int = 0
    feet_from_video: int = 0   # Fuß-Bilder, deren Stellung aus dem Bild gesetzt wurde
    body_frames: int = 0       # Spieler-Bilder, deren Haltung vom Körpermodell stammt (tools/veo_body.py)
    position_shift: float = 0.0   # Summe der mittleren Verschiebung der Bahn durch die Hüfte des Körpermodells (m), über Spieler
    position_players: int = 0


def load_body(run):
    """Ergebnis des Körpermodells (DETEKTIONEN.json.body.npz von tools/veo_body.py) oder None."""
    path = Path(str(run.det_path) + ".body.npz")
    if not path.exists():
        return None
    data = dict(np.load(path))
    if "ids" not in data or not len(data["player"]):
        return None
    kept = body_pose.drop_misplaced(data)
    print(f"Körpermodell: {len(data['player']) - len(kept['player'])} von {len(data['player'])} Personen aussortiert (falsche Person gelesen)", flush=True)
    return kept


def fit_poses(run, observed, smooth, joints, floor, game) -> PoseResult:
    """Haltung je Figur: natürliche Bewegung entlang ihrer Bahn, im Kamerabild an die Gelenkpunkte angepasst; danach Grenzen
    des Körpers, Glättung, Boden. Korrigiert game.xy (die Anpassung verschiebt die Bahn leicht)."""
    n, cam, cam_pos, no_veo = run.n, run.cam, run.cam_pos, run.no_veo
    kp2d, boxed, body = joints.kp2d, joints.boxed, joints.body
    obs, base, xy, slots, ball, total, ratio = observed.obs, game.base, game.xy, game.slots, game.ball, game.total, game.ratio
    J = len(JOINTS)
    buf = array("h", [MISSING]) * (math.ceil(total / CHUNK_FRAMES) * CHUNK_FRAMES * len(slots) * J * 3)
    result = PoseResult(buf, [], {})
    ball_xy = xy[:, ball] if ball is not None else None
    median_height = float(np.median(list(body.values()))) if body else DEFAULT_HEIGHT
    body_data = load_body(run)
    builds = body_build.measure(body_data) if body_data is not None else {}
    nearest = np.minimum(np.round(np.arange(total) * ratio).astype(int), n - 1)
    for slot, entity in enumerate(slots):
        pos = xy[:, entity].copy()
        for a, b in segments(~np.isnan(pos[:, 0]), 1):   # Auftritte unter einer halben Sekunde: keine Figur (zu kurz für eine Haltung)
            if b - a < MIN_APPEARANCE * OUT_FPS:
                pos[a:b] = np.nan
        xy[:, entity] = pos
        present = ~np.isnan(pos[:, 0])
        if not present.any():
            continue
        e = base["entities"][entity]
        key = (e["team"], int(e["id"].rsplit("-", 1)[1])) if no_veo else (e["team"], e["number"]) if "label" not in e else None
        lengths = pose_limits.bone_lengths(body.get(key, median_height))
        if e["id"] in builds:   # Schulter, Hüfte, Beinlängen, Rumpf und Arme des Spielers statt der Schablone
            e["build"] = {p: round(builds[e["id"]][p], 3) for p in body_build.PARTS}
            lengths = body_build.apply(lengths, builds[e["id"]])
        down, low, seen, h36 = np.zeros(total, bool), np.zeros(total, bool), np.zeros(total), None
        foot_out = lens_feet = None   # Fußpunkte aus dem Bild im Takt der Ausgabe (tools/veo_feet.py), wenn vorhanden
        if key in smooth:
            low, down = smooth[key]["low"][nearest], smooth[key]["floor"][nearest]
            points = np.where(boxed[key][:, None, None], kp2d[key], np.nan)
            kp_out, lens_out = resample_keypoints(points, obs[key][:, 0], total, ratio)
            if joints.foot2d is not None and key in joints.foot2d and (~np.isnan(joints.foot2d[key][:, 0, 0])).any():
                foot_out, lens_feet = resample_keypoints(np.where(boxed[key][:, None, None], joints.foot2d[key], np.nan), obs[key][:, 0], total, ratio)
            target, weight = pose_fit.targets(kp_out)
            weight = weight * overlap.weight_factor(obs, key)[nearest][:, None]   # überdeckt (Zweikampf): Gelenkpunkte unsicher
            ref, A = pose_fit.linearize(cam, lens_out, pos)
            weight[down | ~present | np.isnan(ref[:, 0])] = 0
            result.views[e["id"]] = {"kp": kp_out.astype(np.float32), "lens": lens_out.astype(np.float32), "down": down,
                                     "lying": smooth[key]["down"][nearest], "share": smooth[key]["share"][nearest].astype(np.float32)}
            if os.environ.get("MATCHSPACE_DEBUG"):  # Eingaben der Anpassung zum Nachstellen
                np.savez(f"{os.environ['MATCHSPACE_DEBUG']}.{e['id']}.npz", kp=kp_out, lens=lens_out, pos=pos, ball=ball_xy, down=down, low=low,
                         height=body.get(key, median_height), present=present)
            motion, backwards = pose_fit.natural_motion(pos, ball_xy, OUT_FPS, lengths, target, weight, A)
            lean = np.where(down, math.pi, np.where(low, math.radians(70), pose_limits.MAX_LEAN))
            fitted = pose_fit.fit(target, weight, ref, A, pos, cam_pos, lengths, motion, lean)
            pos = pos + fitted["shift"]
            for a, b in segments(present, 9):   # die Korrektur der Anpassung darf die Bahn nicht unruhig oder unmöglich machen
                pos[a:b] = track_limits.physical(smooth_track(pos[a:b], cam_pos, sideways=False), OUT_FPS)
            xy[:, entity] = pos
            h36, seen = fitted["h36m"], fitted["observed"]
            result.errors.append(fitted["error"])
            result.backward_frames += int((backwards & present).sum())
        else:
            motion, _ = pose_fit.natural_motion(pos, ball_xy, OUT_FPS, lengths, start_phase=slot * 1.7)
        d = motion.copy()
        if h36 is not None:
            for a, b in segments(present & ~np.isnan(h36[:, 0, 0]), 2):
                limited, changes = pose_limits.limit_joints(h36[a:b], lean[a:b, None])
                result.stats.update(changes)
                d[a:b] = pose_limits.directions_from_h36m(limited)
        if down.any():   # fallen, liegen, aufstehen: Ablauf aus möglichen Haltungen, gesteuert von der gemessenen Körperhöhe
            way = np.gradient(np.where(present[:, None], pos, np.nan), axis=0)
            lying_now = smooth[key]["down"][nearest] & down
            d = ground_motion.sequence(d, smooth[key]["share"][nearest], lying_now, down & present, way, OUT_FPS)
            result.grounded += int((down & present).sum())
        sam = np.zeros(total, bool)
        if body_data is not None:   # Haltung vom Körpermodell, wo es den Spieler gelesen hat (außer am Boden: dort die bewährte Abfolge)
            seen_by_model = pose_limits.directions_of(body_pose.world_joints(body_data, e["id"], total, cam, veo_camera.rays, NAMES))
            sam = ~np.isnan(seen_by_model[:, 1, 0]) & present & ~down
            d[sam] = seen_by_model[sam]
            result.body_frames += int(sam.sum())
        d = pose_limits.smooth_directions(pose_limits.limit_turn(d, OUT_FPS), OUT_FPS)
        allowed = lean if key in smooth else pose_limits.MAX_LEAN
        d = pose_limits.limit_directions(d, allowed)   # Glätten kann Grenzen wieder verletzen
        d, pos = pose_limits.balance_depth(d, lengths, pos, cam_pos, OUT_FPS, skip=down | sam)   # das Modell gibt die Neigung vor
        d = pose_limits.limit_directions(d, allowed)
        if sam.any():   # Position: im Zweikampf mischt die gemeinsame Box beide Spieler und hält sie auseinander; die Füße des Modells sind je Person gelesen
            seen_at = body_pose.position_from_feet(body_data, e["id"], total, cam, veo_camera.rays, pose_limits.build(d, lengths), NAMES)
            before = pos.copy()
            pos = body_pose.refine_position(pos, seen_at, sam)
            result.position_shift += float(np.nanmean(np.linalg.norm(pos - before, axis=1)[sam]))
            result.position_players += 1
        for a, b in segments(present, 6):
            pos[a:b] = track_limits.physical(pos[a:b], OUT_FPS)
        xy[:, entity] = pos
        joint_pos, before, after, count = foot_planting.plant_feet(pose_limits.build(d, lengths), pos, OUT_FPS, lengths, skip=down)
        # Das Festhalten der Füße kann die Hüfte überdehnen: Grenzen ein letztes Mal anwenden (der Fuß gibt dann nach)
        joint_pos = pose_limits.build(pose_limits.limit_directions(pose_limits.directions_of(joint_pos), allowed), lengths)
        if foot_out is not None and not sam.any():   # Ferse und Zehe aus dem Bild statt aus der Laufrichtung
            joint_pos, fed = foot_fit.apply(joint_pos, pos, foot_out, lens_feet, cam, NAMES, veo_camera.rays)
            result.feet_from_video += fed
        for side in "lr":
            result.toes.append(joint_pos[:, NAMES.index(side + "Toe"), :2] + pos)
        result.slip_before += before
        result.slip_after += after
        result.slip_frames += count
        values = np.where(np.isnan(joint_pos), MISSING, np.clip(np.round(np.nan_to_num(joint_pos) / POSE_SCALE), -32767, 32767)).astype(np.int64)
        for of in np.flatnonzero(present):
            o = (of * len(slots) + slot) * J * 3
            buf[o:o + J * 3] = array("h", values[of].ravel().tolist())
        from_video = (seen >= SEEN_SHARE) | down
        result.estimated += int((from_video & present).sum())
        result.present_total += int(present.sum())
        if key in smooth:
            result.summary[e["id"]] = round(float((from_video & present).sum() / present.sum()), 2)
    return result
