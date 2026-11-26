#!/usr/bin/env python3
"""Ballspur mit Höhe: bindet die Physik (tools/ball_physics.py) an Kamera und Kontakte (tools/ball_events.py).

Zwischen zwei Kontakten wird je ein Stück Spur an die Sehstrahlen durch die Ballpixel angepasst: Flug mit Höhe oder Rollen am Boden.
Lücken innerhalb eines Stücks (Ball nicht zu sehen) füllt die angepasste Bahn und sind als erschlossen gekennzeichnet; vor und nach
einem Stück reicht die Bahn bis zum Kontakt. Wo zu wenig Spur für eine Anpassung da ist oder weder Rollen noch Flug plausibel sind, bleibt die Lage leer (Kennung „unbekannt“):
Die Lage am Boden wäre bei einem Ball in der Luft stark verzerrt.

Aufruf:  .venv/bin/python tools/ball_motion.py KAMERA.json DETEKTIONEN.json   (liest DETEKTIONEN.json.ball.npz, schreibt .ball3d.npz)
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import ball_events  # noqa: E402
import ball_physics  # noqa: E402
import veo_camera  # noqa: E402

LENSES = ("left", "right")
GROUND, FLIGHT = 1, 2      # kind je Bild; 0 = unbekannt
EXTEND = 6                 # Bilder, die eine angepasste Bahn über die letzte Beobachtung hinaus weitergeführt wird (Ausholen bis zum Kontakt)
JUMP_M = 1.5              # m: größte Lücke zwischen zwei Stücken am Kontakt
MARGIN = 1                 # Bilder rund um einen Kontakt, die nicht in die Anpassung eingehen (der Fuß verdeckt den Ball)
REACH_TOL = 0.10           # m: so nah am Sehstrahl darf ein Beobachtung liegen, damit der Flug sie noch mit abdeckt (Abwurf, Landung)
MERGE_RMS = 0.02           # m: erklärt ein einziger Flug die Spur beidseits eines „Kontakts“ so genau, war es keiner


@dataclass
class Motion:
    xyz: np.ndarray        # (n, 3) Lage in Metern, Höhe = Mittelpunkt des Balls über dem Rasen
    kind: np.ndarray       # (n,) 0 unbekannt, 1 Boden, 2 Flug
    inferred: np.ndarray   # (n,) True, wo der Ball nicht gesehen und aus der Bahn erschlossen wurde
    z_sigma: np.ndarray    # (n,) Unsicherheit der Höhe in m (0 am Boden)
    segments: list
    contacts: list = field(default_factory=list)   # Kontakte, die übrig blieben


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


def angular_track(cam, pix: np.ndarray) -> np.ndarray:
    """Ballspur in Winkeln um die Kamera, mal Entfernung (am Boden angenommen) in Meter umgerechnet: (n, 2), NaN ohne Fund.
    Anders als die Lage am Boden bleibt ein Flug darin glatt (die Verzerrung durch die Höhe ändert sich nur langsam), und
    die Naht der beiden Linsenbilder macht keinen Sprung. Darin werden Kontakte gesucht."""
    _, direction, rng = observations(cam, pix)
    az = np.arctan2(direction[:, 0], direction[:, 1])
    el = np.arcsin(np.clip(direction[:, 2], -1, 1))
    return np.column_stack([az * rng, el * rng])


def drop_discontinuous(pieces: list, fps: float, jump: float = JUMP_M) -> int:
    """Benachbarte Stücke (ein Kontakt dazwischen) müssen am Übergang zusammenpassen: Der Ball ist beim Kontakt an einem Ort. Passen
    sie um mehr als `jump` Meter nicht zusammen, fliegt das unsicherere Stück raus (Rollen vor Flug, sonst der größere Restfehler).
    Rückgabe: Zahl entfernter Stücke."""
    removed = 0
    i = 0
    while i < len(pieces) - 1:
        a, b = pieces[i], pieces[i + 1]
        if b["frames"][0] - a["frames"][-1] <= 2 * MARGIN + 2:
            gap = np.linalg.norm(a["seg"].fit.at(a["frames"][-1] / fps) - b["seg"].fit.at(b["frames"][0] / fps))
            if gap > jump:
                if a["seg"].kind == b["seg"].kind:
                    worse = a if a["seg"].rms >= b["seg"].rms else b
                else:
                    worse = a if a["seg"].kind == "ground" else b   # ein Flug erklärt sich selbst, Rollen am Boden weicht
                pieces.remove(worse)
                removed += 1
                i = max(0, i - 1)
                continue
        i += 1
    return removed


def prune_flight_contacts(origin, direction, rng, found: np.ndarray, contacts: list, fps: float) -> list:
    """Entfernt Kontakte, die keine sind: Die Suche nach Kontakten (tools/ball_events.py) arbeitet auf der Spur im Bild, und ein
    Flug ändert dort seine scheinbare Geschwindigkeit (Höhe, Entfernung), ohne dass ihn jemand berührt. Ein echter Kontakt
    knickt die Bahn: Eine einzige Wurfparabel über die Spur davor und danach passt dann nicht. Passt sie dagegen auf MERGE_RMS genau
    (und ist sie als Flug plausibel), fliegt der Ball durch und der Kontakt fällt weg. Der Reihe nach, die sicheren zuletzt."""
    n = len(found)
    kept = sorted(contacts, key=lambda c: c.frame)
    for c in sorted(contacts, key=lambda c: c.confidence):
        i = kept.index(c)
        a = kept[i - 1].frame if i else -1
        b = kept[i + 1].frame if i + 1 < len(kept) else n
        idx = np.flatnonzero(found[a + 1:b]) + a + 1
        if len(idx) < ball_physics.MIN_OBS:
            continue
        kind, fit = ball_physics.choose(origin[idx], direction[idx], idx / fps, rng[idx])
        if kind == "flight" and fit.rms <= MERGE_RMS:
            kept.remove(c)
    return kept


def reach(fit, origin, direction, found: np.ndarray, frm: int, limit: int, fps: float, tol: float = REACH_TOL) -> int:
    """Wie weit ein angepasster Flug von Bild `frm` aus in Richtung `limit` (ausschließlich) noch zur Spur passt: das letzte Bild,
    dessen Fund höchstens `tol` Meter vom Flug entfernt am Sehstrahl liegt, ohne dass ein schlechterer Fund dazwischen liegt.
    Dort beginnt der Wurf, wo der Ball die Hand verlässt (davor liegt der Ball in der Hand und folgt keiner Parabel)."""
    step = 1 if limit > frm else -1
    last = frm
    for f in range(frm + step, limit, step):
        if not found[f]:
            continue
        miss = float(np.linalg.norm(np.cross(fit.at(f / fps) - origin[f], direction[f])))
        if miss > tol:
            break
        last = f
    return last


def fill_raw(xyz, kind, inferred, z_sigma, origin, direction, rng, found: np.ndarray, fps: float) -> int:
    """Erkennungen, die in keinem angepassten Stück liegen (zu wenige Beobachtungen am Stück, Gedränge), als Lage am Boden übernehmen, wenn sie
    zum letzten bekannten Ort passen (höchstens RAW_MAX_SPEED und RAW_MAX_S entfernt). Sonst blieb der Ball dort unbekannt und die Ausgabe überbrückte
    geradeaus bis zum nächsten bekannten Ort, auch wo der Ball im Video gar nicht weiterzog. Schreibt in xyz/kind/inferred; Rückgabe: Zahl übernommener Bilder."""
    taken, last, last_f = 0, None, None
    for f in range(len(found)):
        if kind[f] != 0:
            last, last_f = xyz[f].copy(), f
            continue
        if not found[f]:
            continue
        point = origin[f] + direction[f] * rng[f]
        point[2] = ball_physics.RADIUS
        if last is not None and (f - last_f) / fps <= RAW_MAX_S and np.linalg.norm(point[:2] - last[:2]) / max((f - last_f) / fps, 1e-3) <= RAW_MAX_SPEED:
            xyz[f], kind[f], inferred[f], z_sigma[f] = point, GROUND, False, 0.0
            last, last_f = point, f
            taken += 1
    return taken


def build(cam, pix: np.ndarray, contacts: list, fps: float) -> Motion:
    n = len(pix)
    origin, direction, rng = observations(cam, pix)
    found = ~np.isnan(pix[:, 0]) & ~np.isnan(rng)
    xyz = np.full((n, 3), np.nan)
    kind = np.zeros(n, np.uint8)
    inferred = np.zeros(n, bool)
    z_sigma = np.zeros(n)
    contacts = prune_flight_contacts(origin, direction, rng, found, contacts, fps)
    cuts = [0] + sorted(c.frame for c in contacts) + [n]
    pieces = []
    for i, (a, b) in enumerate(zip(cuts[:-1], cuts[1:])):
        before = cuts[i - 1] if i > 1 else -1      # Kontakt vor dem davor: so weit darf ein Flug zurückreichen
        lo, hi = (a + MARGIN if a else 0), (b - MARGIN if b < n else n)
        idx = np.flatnonzero(found[lo:hi]) + lo
        if len(idx) < ball_physics.MIN_OBS:
            continue
        t = idx / fps
        for seg in ball_physics.segment_track(origin[idx], direction[idx], t, rng[idx], idx):
            if seg.fit is None or seg.kind == "unknown":
                continue
            first = max(a if seg.start == idx[0] else seg.start, seg.start - EXTEND)   # bis zum Kontakt, aber nicht weit ins Leere
            last = min(b if seg.stop == idx[-1] + 1 else seg.stop, seg.stop + EXTEND)
            if seg.kind == "flight":
                first = min(first, reach(seg.fit, origin, direction, found, seg.start, before, fps))
                last = max(last, reach(seg.fit, origin, direction, found, seg.stop - 1, b, fps) + 1)
                if first < lo and a:     # der Kontakt davor war der Abwurf, der Flug beginnt früher: den Kontakt dorthin legen
                    moved = [c for c in contacts if c.frame == a]
                    for c in moved:
                        c.frame, c.time = int(first), first / fps
            pieces.append({"seg": seg, "frames": np.arange(first, min(last, n))})
    drop_discontinuous(pieces, fps)
    segments = []
    pieces_end = len(pieces)
    for pc in pieces:
        seg, frames = pc["seg"], pc["frames"]
        at = seg.fit.at(frames / fps)
        xyz[frames] = at
        kind[frames] = FLIGHT if seg.kind == "flight" else GROUND
        z_sigma[frames] = seg.fit.z_sigma if seg.kind == "flight" else 0.0
        inferred[frames] = ~found[frames]
        segments.append((int(frames[0]), int(frames[-1]) + 1, seg.kind, round(seg.rms, 3), round(seg.z_sigma, 2), round(float(at[:, 2].max()), 2)))
    fill_raw(xyz, kind, inferred, z_sigma, origin, direction, rng, found, fps)
    return Motion(xyz, kind, inferred, z_sigma, segments, contacts)


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


RAW_MAX_SPEED = 15.0       # m/s: so schnell darf sich eine nicht angepasste Erkennung vom letzten bekannten Ort entfernt haben, um als Ort am Boden zu gelten
RAW_MAX_S = 0.6            # s: so lange darf der letzte bekannte Ort zurückliegen
GAP_MAX_SPEED = 22.0       # m/s: schneller kann der Ball eine ungesehene Lücke nicht durchquert haben (Pass eines U15-Spielers)
GAP_MAX_S = 0.8            # s: so lange Lücken werden überbrückt, längere nicht: Wo der Ball länger nicht zu sehen war, weiß man nicht, wohin er flog (ein Hochschlag über das Feld, ein Abpraller), und ein gerader Weg wäre erfunden
HOLD_S = 1.0               # s: am Anfang und Ende der Szene hält der Ball so lange die nächste bekannte Lage, danach ist er unbekannt
ARC_MAX_S = 1.2            # s: bis zu dieser Dauer wird eine schnelle Lücke zwischen Bodenlagen als Flug mit Bogen überbrückt (Scheitel g·T²/8)
ARC_MIN_SPEED = 7.0        # m/s: langsamer rollt der Ball
AIR_MAX_S = 3.5            # s: so lange darf ein Flug durch eine Lücke gerechnet werden (Scheitel 15 m: obere Grenze für einen Schlag im Jugendfußball)
AIR_MIN_Z = 0.25           # m: Höhe, ab der ein Bild als Flug gilt
AIR_FIT_FRAMES = 8         # Bilder vor und hinter der Lücke, aus denen die Parabel stammt
AIR_MIN_FIT = 4            # so viele Flugbilder braucht eine Seite mindestens
AIR_RMS = 0.30            # m: Restfehler, bis zu dem eine Parabel beide Seiten einer Lücke erklärt
AIR_LAND_ERR = 2.5         # m: so weit darf die Rechnung vom gesehenen Ort am anderen Ende der Lücke abweichen
AIR_ROLL_SPEED = 5.0       # m/s: Rollen nach der Landung bis zur nächsten Lage (Zuschlag zur erlaubten Abweichung)


def _air_side(xy: np.ndarray, z: np.ndarray, start: int, step: int) -> list:
    """Bilder im Flug (Höhe ≥ AIR_MIN_Z) lückenlos ab `start` in Richtung `step`, höchstens AIR_FIT_FRAMES; zeitlich geordnet."""
    out, f = [], start
    while 0 <= f < len(xy) and len(out) < AIR_FIT_FRAMES and not np.isnan(xy[f, 0]) and z[f] >= AIR_MIN_Z:
        out.append(f)
        f += step
    return sorted(out)


def _air_fit(frames: list, xy: np.ndarray, z: np.ndarray, fps: float) -> tuple:
    """Wurfparabel (feste Schwerkraft) durch die Lagen: p0 (3,) bei Zeit des ersten Bildes, v (3,), Restfehler. Höhe = Mittelpunkt des Balls."""
    t = (np.array(frames) - frames[0]) / fps
    pts = np.column_stack([xy[frames], z[frames] + ball_physics.RADIUS])
    y = pts + 0.5 * ball_physics.G * (t ** 2)[:, None] * np.array([0.0, 0.0, 1.0])
    A = np.column_stack([np.ones_like(t), t])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    return coef[0], coef[1], float(np.sqrt(((y - A @ coef) ** 2).sum(axis=1).mean()))


def _air_at(p0, v, t) -> np.ndarray:
    return p0 + v * t - 0.5 * ball_physics.G * t * t * np.array([0.0, 0.0, 1.0])


def air_bridge(xy: np.ndarray, z: np.ndarray, A: int, B: int, fps: float) -> bool:
    """Flug durch die Lücke (A, B) rechnen, wenn ihn das Gesehene davor und/oder danach bestimmt, und die Lücke damit füllen (Rückgabe True).
    Beide Seiten im Flug: eine Parabel muss beide erklären (Restfehler AIR_RMS). Nur eine Seite im Flug (Schuss, dessen Beginn man sah, oder dessen Landung):
    die Parabel muss am Boden dort ankommen oder dort herkommen, wo die andere Seite liegt (AIR_LAND_ERR). Sonst bleibt die Lücke leer: Ohne Beleg
    gibt es keine Bahn."""
    T = (B - A) / fps
    if T > AIR_MAX_S:
        return False
    before, after = _air_side(xy, z, A, -1), _air_side(xy, z, B, +1)
    R = ball_physics.RADIUS
    g = ball_physics.G
    n = np.arange(A + 1, B)
    if len(before) >= AIR_MIN_FIT and len(after) >= AIR_MIN_FIT:
        frames = before + after
        p0, v, rms = _air_fit(frames, xy, z, fps)
        if rms > AIR_RMS:
            return False
        pts = _air_at(p0, v, ((n - frames[0]) / fps)[:, None])
        xy[A + 1:B], z[A + 1:B] = pts[:, :2], np.maximum(pts[:, 2] - R, 0.0)
        return True
    if len(before) >= AIR_MIN_FIT or len(after) >= AIR_MIN_FIT:
        forward = len(before) >= AIR_MIN_FIT
        frames = before if forward else after
        p0, v, rms = _air_fit(frames, xy, z, fps)
        if rms > AIR_RMS:
            return False
        # Zeit (ab frames[0]), zu der der Mittelpunkt wieder auf Bodenhöhe ist: z0 + vz t - g t²/2 = R
        disc = v[2] ** 2 + 2 * g * (p0[2] - R)
        if disc < 0:
            return False
        roots = ((v[2] - np.sqrt(disc)) / g, (v[2] + np.sqrt(disc)) / g)      # früher, später
        other = B if forward else A
        t_other = (other - frames[0]) / fps
        if forward:
            t_ground = roots[1]
            if not ((A - frames[0]) / fps < t_ground <= t_other):
                return False
            rest = t_other - t_ground
            ground_xy = p0[:2] + v[:2] * t_ground
            if z[other] >= AIR_MIN_Z or np.isnan(xy[other, 0]):
                ok = np.linalg.norm(_air_at(p0, v, t_other)[:2] - xy[other]) <= AIR_LAND_ERR and abs(_air_at(p0, v, t_other)[2] - R - z[other]) <= 0.8
                rest = 0.0
            else:
                ok = np.linalg.norm(ground_xy - xy[other]) <= AIR_LAND_ERR + AIR_ROLL_SPEED * rest
        else:
            t_ground = roots[0]
            if not (t_other <= t_ground < (B - frames[0]) / fps):
                return False
            rest = t_ground - t_other
            ground_xy = p0[:2] + v[:2] * t_ground
            if z[other] >= AIR_MIN_Z or np.isnan(xy[other, 0]):
                ok = np.linalg.norm(_air_at(p0, v, t_other)[:2] - xy[other]) <= AIR_LAND_ERR and abs(_air_at(p0, v, t_other)[2] - R - z[other]) <= 0.8
                rest = 0.0
            else:
                ok = np.linalg.norm(ground_xy - xy[other]) <= AIR_LAND_ERR + AIR_ROLL_SPEED * rest
        if not ok:
            return False
        t = (n - frames[0]) / fps
        pts = _air_at(p0, v, t[:, None])
        out_xy, out_z = pts[:, :2], np.maximum(pts[:, 2] - R, 0.0)
        rolled = (t > t_ground) if forward else (t < t_ground)    # nach der Landung (oder vor dem Abschlag) bis zur anderen Seite am Boden entlang
        if rolled.any():
            if rest > GAP_MAX_S:     # zwischen Landung und nächster Lage zu lange ungesehen: der Flug zählt, das Rollen danach nicht
                out_xy[rolled], out_z[rolled] = np.nan, np.nan
            else:
                span = max(abs(t_other - t_ground), 1e-9)
                w = (np.abs(t - t_ground) / span)[rolled]
                out_xy[rolled] = ground_xy + (xy[other] - ground_xy) * w[:, None]
                out_z[rolled] = 0.0
        xy[A + 1:B], z[A + 1:B] = out_xy, out_z
        return True
    return False


def bridge(xy: np.ndarray, z: np.ndarray, fps: float) -> tuple:
    """Lücken der Ballspur (NaN) im Takt der Ausgabe schließen, ohne den Ball durch die Gegend zu schießen. Zwischen zwei bekannten Lagen
    legt der Ball eine gerade Strecke zurück, solange das Tempo glaubwürdig ist (höchstens GAP_MAX_SPEED und GAP_MAX_S); ein schneller kurzer Weg
    zwischen Bodenlagen ist ein Flug mit Bogen. Ist das Tempo unmöglich, war der Ball nicht zu verfolgen: Die Lücke bleibt leer (der Ball ist
    dann unbekannt, nicht an einem erfundenen Ort). Anfang und Ende halten die nächste Lage nur kurz (HOLD_S).
    Rückgabe: Lage (n, 2) und Höhe (n,) über dem Boden, NaN in offenen Lücken."""
    xy, z = xy.copy(), z.copy()
    known = ~np.isnan(xy[:, 0])
    n = len(xy)
    idx = np.flatnonzero(known)
    if not len(idx):
        return xy, z
    hold = int(HOLD_S * fps)
    runs, start = [], None
    for f in range(n + 1):
        gap = f < n and not known[f]
        if gap and start is None:
            start = f
        if not gap and start is not None:
            runs.append((start, f))
            start = None
    for a, b in runs:
        if a == 0 or b == n:                        # Anfang oder Ende: die nächste Lage nur kurz halten, sonst unbekannt
            src = b if a == 0 else a - 1
            held = slice(max(a, b - hold), b) if a == 0 else slice(a, min(b, a + hold))
            xy[a:b], z[a:b] = np.nan, np.nan
            xy[held], z[held] = xy[src], z[src]
            continue
        A, B = a - 1, b
        T = (B - A) / fps
        v = float(np.linalg.norm(xy[B] - xy[A])) / T
        if T > GAP_MAX_S and air_bridge(xy, z, A, B, fps):    # lange Lücke: nur ein gerechneter Flug, den das Gesehene bestimmt
            continue
        if v > GAP_MAX_SPEED or T > GAP_MAX_S:
            xy[a:b], z[a:b] = np.nan, np.nan
            continue
        s = (np.arange(a, b) - A) / (B - A)
        xy[a:b] = xy[A] + (xy[B] - xy[A]) * s[:, None]
        z[a:b] = z[A] + (z[B] - z[A]) * s
        if T <= ARC_MAX_S and v >= ARC_MIN_SPEED and max(z[A], z[B]) < 0.3:
            z[a:b] += 4 * (ball_physics.G * T * T / 8) * s * (1 - s)
    return xy, z


def main(camera_path, det_path) -> None:
    cam = veo_camera.load(camera_path)
    z = np.load(f"{det_path}.ball.npz")
    pix, fps = z["pixel"], float(z["fps"])
    contacts = ball_events.find_contacts(angular_track(cam, pix), fps)
    m = build(cam, pix, contacts, fps)
    np.savez_compressed(f"{det_path}.ball3d.npz", xyz=m.xyz, kind=m.kind, inferred=m.inferred, z_sigma=m.z_sigma, fps=fps,
                        contacts=np.array([[c.frame, c.speed_in, c.speed_out, c.jump, c.confidence] for c in m.contacts]))
    print(f"{len(m.contacts)} Kontakte (von {len(contacts)} Kandidaten); Stücke (von, bis, Art, Restfehler m, Höhenunsicherheit m, größte Höhe m):")
    for s in m.segments:
        if s[2] == "flight":
            print("  ", s)
    print(f"Flug in {(m.kind == FLIGHT).sum()} Bildern, Boden in {(m.kind == GROUND).sum()}, erschlossen {m.inferred.sum()}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
