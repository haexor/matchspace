#!/usr/bin/env python3
"""Ballspur mit Höhe: bindet die Physik (tools/ball_physics.py) an Kamera und Kontakte (tools/ball_events.py).

Zwischen zwei Kontakten wird je ein Stück Spur an die Sehstrahlen durch die Ballpixel angepasst: Flug mit Höhe oder Rollen am Boden.
Lücken innerhalb eines Stücks (Ball nicht zu sehen) füllt die angepasste Bahn und sind als erschlossen gekennzeichnet; vor und nach
einem Stück reicht die Bahn bis zum Kontakt. Wo zu wenig Spur für eine Anpassung da ist, bleibt die Lage am Boden (wie bisher) oder
leer, mit Kennung „unbekannt“.

Aufruf:  .venv/bin/python tools/ball_motion.py KAMERA.json DETEKTIONEN.json   (liest DETEKTIONEN.json.ball.npz, schreibt .ball3d.npz)
"""
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import ball_events  # noqa: E402
import ball_physics  # noqa: E402
import veo_camera  # noqa: E402

LENSES = ("left", "right")
GROUND, FLIGHT = 1, 2      # kind je Bild; 0 = unbekannt
MARGIN = 1                 # Bilder rund um einen Kontakt, die nicht in die Anpassung eingehen (der Fuß verdeckt den Ball)


@dataclass
class Motion:
    xyz: np.ndarray        # (n, 3) Lage in Metern, Höhe = Mittelpunkt des Balls über dem Rasen
    kind: np.ndarray       # (n,) 0 unbekannt, 1 Boden, 2 Flug
    inferred: np.ndarray   # (n,) True, wo der Ball nicht gesehen und aus der Bahn erschlossen wurde
    z_sigma: np.ndarray    # (n,) Unsicherheit der Höhe in m (0 am Boden)
    segments: list


def observations(cam, pix: np.ndarray) -> tuple:
    """Je Bild mit Fund: Ursprung, Richtung und Entfernung des Sehstrahls (NaN ohne Fund)."""
    n = len(pix)
    origin, direction, rng = np.full((n, 3), np.nan), np.full((n, 3), np.nan), np.full(n, np.nan)
    for li in (0, 1):
        idx = np.flatnonzero(pix[:, 0] == li)
        if not len(idx):
            continue
        d = veo_camera.rays(cam, LENSES[li], pix[idx, 1:3])
        _, dist = veo_camera.to_ground(cam, LENSES[li], pix[idx, 1:3], ball_physics.RADIUS)
        origin[idx], direction[idx], rng[idx] = cam["lenses"][LENSES[li]]["centre"], d, dist
    return origin, direction, rng


def build(cam, pix: np.ndarray, contacts: list, fps: float) -> Motion:
    n = len(pix)
    origin, direction, rng = observations(cam, pix)
    found = ~np.isnan(pix[:, 0]) & ~np.isnan(rng)
    xyz = np.full((n, 3), np.nan)
    kind = np.zeros(n, np.uint8)
    inferred = np.zeros(n, bool)
    z_sigma = np.zeros(n)
    # Lage am Boden für alle Funde als Rückfall (Ball auf Rasenhöhe angenommen, wie bisher)
    for li in (0, 1):
        idx = np.flatnonzero(found & (pix[:, 0] == li))
        if len(idx):
            g, _ = veo_camera.to_ground(cam, LENSES[li], pix[idx, 1:3], ball_physics.RADIUS)
            xyz[idx] = np.column_stack([g, np.full(len(idx), ball_physics.RADIUS)])
    cuts = [0] + sorted(c.frame for c in contacts) + [n]
    segments = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        lo, hi = (a + MARGIN if a else 0), (b - MARGIN if b < n else n)
        idx = np.flatnonzero(found[lo:hi]) + lo
        if len(idx) < ball_physics.MIN_OBS:
            continue
        t = idx / fps
        for seg in ball_physics.segment_track(origin[idx], direction[idx], t, rng[idx], idx):
            if seg.fit is None:
                continue
            first = a if seg.start == idx[0] else seg.start
            last = b if seg.stop == idx[-1] + 1 else seg.stop
            frames = np.arange(first, min(last, n))
            xyz[frames] = seg.fit.at(frames / fps)
            kind[frames] = FLIGHT if seg.kind == "flight" else GROUND
            z_sigma[frames] = seg.fit.z_sigma if seg.kind == "flight" else 0.0
            inferred[frames] = ~found[frames]
            segments.append((first, int(frames[-1]) + 1, seg.kind, round(seg.rms, 3), round(seg.z_sigma, 2),
                             round(float(seg.fit.at(frames / fps)[:, 2].max()), 2)))
    return Motion(xyz, kind, inferred, z_sigma, segments)


@dataclass
class OutputTrack:
    xy: np.ndarray         # (total, 2) Lage; NaN, wo die Bahn nichts sagt
    z: np.ndarray          # (total,) Höhe der Ballunterseite über dem Rasen in Metern (0 am Boden)
    inferred: np.ndarray   # (total,) erschlossen statt gesehen
    flight: np.ndarray     # (total,) Flug
    contacts: np.ndarray   # Ausgabebilder der Kontakte


def sample(values: np.ndarray, total: int, ratio: float) -> np.ndarray:
    """Werte (n, ...) auf total Bilder im Takt der Ausgabe: gemittelt, wo beide Nachbarn gültig sind, sonst das nächste; NaN, wo das nächste Quellbild leer ist."""
    src = np.arange(total) * ratio
    a = np.minimum(src.astype(int), len(values) - 1)
    b = np.minimum(a + 1, len(values) - 1)
    shape = (-1,) + (1,) * (values.ndim - 1)
    w = (src - a).reshape(shape)
    ok = ~np.isnan(values).reshape(len(values), -1).any(axis=1)
    va, vb = ok[a].reshape(shape), ok[b].reshape(shape)
    near = np.where(src - a < 0.5, a, b)   # ist das nächste Quellbild leer, bleibt das Ausgabebild leer: keine Lage erfinden
    return np.where(ok[near].reshape(shape), np.where(va & vb, values[a] + (values[b] - values[a]) * w, values[near]), np.nan)


def output_track(path, total: int, ratio: float) -> OutputTrack:
    """Liest `.ball3d.npz` (tools/ball_motion.py) im Takt der Ausgabe."""
    z = np.load(path)
    xyz = sample(z["xyz"], total, ratio)
    near = np.minimum(np.round(np.arange(total) * ratio).astype(int), len(z["kind"]) - 1)
    contacts = np.unique(np.round(z["contacts"][:, 0] / ratio).astype(int)) if len(z["contacts"]) else np.zeros(0, int)
    return OutputTrack(xyz[:, :2], np.maximum(np.nan_to_num(xyz[:, 2], nan=ball_physics.RADIUS) - ball_physics.RADIUS, 0.0), z["inferred"][near].astype(bool),
                       z["kind"][near] == FLIGHT, contacts[(contacts >= 0) & (contacts < total)])


def main(camera_path, det_path) -> None:
    cam = veo_camera.load(camera_path)
    z = np.load(f"{det_path}.ball.npz")
    pix, fps = z["pixel"], float(z["fps"])
    contacts = ball_events.find_contacts(z["pos"], fps)
    m = build(cam, pix, contacts, fps)
    np.savez_compressed(f"{det_path}.ball3d.npz", xyz=m.xyz, kind=m.kind, inferred=m.inferred, z_sigma=m.z_sigma, fps=fps,
                        contacts=np.array([[c.frame, c.speed_in, c.speed_out, c.jump, c.confidence] for c in contacts]))
    print(f"{len(contacts)} Kontakte; Stücke (von, bis, Art, Restfehler m, Höhenunsicherheit m, größte Höhe m):")
    for s in m.segments:
        if s[2] == "flight":
            print("  ", s)
    print(f"Flug in {(m.kind == FLIGHT).sum()} Bildern, Boden in {(m.kind == GROUND).sum()}, erschlossen {m.inferred.sum()}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
