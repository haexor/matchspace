"""Boxen zu Spielern: verketten, Rückennummern oder eigene Spuren zuordnen, Ausreißer entfernen, glätten (Stufen 1 und 2
von tools/veo_scene.py).

Ergebnis ist je Spieler ein Feld (Bilder × 9) mit Linse, Box, Fußpunkt am Boden, Körpergröße und Boxnummer sowie die
geglätteten Reihen, aus denen die späteren Stufen Haltung und Position ableiten.
"""
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

sys.path.insert(0, str(Path(__file__).parent))
import veo_camera  # noqa: E402
import veo_tracks  # noqa: E402
from own_scene import OWN_GAP, drop_same_place, own_identities, with_numbers  # noqa: E402
from scene_util import running_median  # noqa: E402

LENSES = ("left", "right")
GATE = 1.5            # Meter: Einzelzuordnung Veo-Position zu Fußpunkt
WIDE_GATE = 4.0       # Meter: so weit darf eine verkettete Box von der Veo-Position liegen
LINK = 0.35           # Verkettung: höchster Abstand zum Vorgänger, in Boxhöhen
MAX_MISS = 10         # Bilder, die eine Folge ohne Erkennung überlebt
VOTE_WINDOW = 45      # Bilder vor und zurück, deren Einzelzuordnungen über die Nummer abstimmen
MIN_VOTES = 3
MIN_SEGMENT = 24      # Spieler mit weniger zugeordneten Bildern werden nicht aus dem Video gelesen
BOX_TO_BODY = 0.93    # Boxen umfassen etwas mehr als den Körper (Unschärfe, Haare, Sohle); Abzug geschätzt, nicht gemessen
DOWN_HEIGHT = 0.4     # Box niedriger als dieser Anteil der Körpergröße: Spieler liegt
DOWN_WIDE = (1.1, 0.6)   # oder Box breiter als hoch (Verhältnis) und zugleich niedriger als dieser Anteil
LOW_HEIGHT = 0.8      # darunter gilt der Spieler als geduckt, kniend oder sitzend


@dataclass
class Observed:
    """Zuordnung der Boxen zu Spielern. obs: (Mannschaft, Nummer) -> Feld (Bilder, 9): Linse, x1, y1, x2, y2, Boden x, Boden y,
    Größe, Boxnummer (NaN ohne Box); where: je Bild Spieler -> Lage am Boden (Veo oder eigene Spur); kit: Farbklasse des Trikots
    je Spieler; keepers: Torhüter (nur ohne Veo)."""
    obs: dict
    where: list
    kit: dict
    keepers: set
    total_boxes: int


def link_tracklets(frames, lens):
    """Verkettet die Boxen einer Linse von Bild zu Bild. Rückgabe: je Bild die Folgennummer je Box."""
    active, next_id, out = {}, 0, []  # nummer -> [bild, x, fußpunkt y, höhe, vx, vy, farbe]
    for fi, fr in enumerate(frames):
        b = np.array(fr[lens], float).reshape(-1, 6)
        cur = np.full(len(b), -1, int)
        c = np.column_stack([(b[:, 0] + b[:, 2]) / 2, b[:, 3]])
        h = b[:, 3] - b[:, 1]
        live = [(k, a) for k, a in active.items() if fi - a[0] <= MAX_MISS]
        active = dict(live)
        if len(b) and live:
            a = np.array([v for _, v in live])
            dt = fi - a[:, 0]
            pred = a[:, 1:3] + a[:, 4:6] * dt[:, None]
            cost = np.linalg.norm(pred[:, None] - c[None], axis=2) / a[:, 3:4]
            cost += 0.15 * (a[:, 6:7] != b[:, 5][None])
            cost[np.abs(np.log(h[None] / a[:, 3:4])) > 0.4] = 9
            r, cc = linear_sum_assignment(np.minimum(cost, 2 * LINK))
            for i, j in zip(r, cc):
                if cost[i, j] < LINK:
                    cur[j] = live[i][0]
        for j in range(len(b)):
            v = np.zeros(2)
            if cur[j] < 0:
                cur[j], next_id = next_id, next_id + 1
            else:
                old = active[cur[j]]
                v = 0.5 * old[4:6] + 0.5 * (c[j] - old[1:3]) / (fi - old[0])
            active[cur[j]] = np.array([fi, c[j, 0], c[j, 1], h[j], v[0], v[1], b[j, 5]])
        out.append(cur)
    return out


def box_metres(cam, lens, boxes):
    """Fußpunkt am Boden (x, y) und Höhe in Metern je Box (Strahl durch die Oberkante, geschnitten über dem Fußpunkt)."""
    b = np.asarray(boxes, float).reshape(-1, 4)
    centre = (b[:, 0] + b[:, 2]) / 2
    out = np.full((len(b), 3), np.nan)
    out[:, :2] = veo_camera.to_ground(cam, lens, np.column_stack([centre, b[:, 3]]))[0]
    ray = veo_camera.rays(cam, lens, np.column_stack([centre, b[:, 1]]))
    reach = np.linalg.norm(out[:, :2] - cam["position"][:2], axis=1)
    out[:, 2] = cam["position"][2] + ray[:, 2] * reach / np.maximum(np.linalg.norm(ray[:, :2], axis=1), 1e-9)
    return out


def posture(height_m, width_px, height_px, body_height):
    """Aus Boxmaßen: liegt der Spieler, und ist er zumindest tief (geduckt, kniend, sitzend)?"""
    share = height_m * BOX_TO_BODY / body_height
    with np.errstate(invalid="ignore", divide="ignore"):
        down = (share < DOWN_HEIGHT) | ((width_px / height_px > DOWN_WIDE[0]) & (share < DOWN_WIDE[1]))
        low = share < LOW_HEIGHT
    return down, low | down


def ground_points(run) -> list:
    """Je Bild und Linse: Fußpunkt am Boden (x, y) und Körpergröße über dem Fußpunkt (m) je Box, Form (Boxen, 3);
    NaN weit außerhalb des Platzes. Körpergröße: Strahl durch die Boxoberkante, geschnitten über dem Fußpunkt."""
    cam, cam_pos = run.cam, run.cam_pos
    L, W = run.length, run.width
    ground = []
    for fr in run.frames:
        per_lens = []
        for lens in LENSES:
            b = np.array(fr[lens], float).reshape(-1, 6)
            g = np.full((len(b), 3), np.nan)
            if len(b):
                centre = (b[:, 0] + b[:, 2]) / 2
                g[:, :2], dist = veo_camera.to_ground(cam, lens, np.column_stack([centre, b[:, 3]]))
                g[(np.abs(g[:, 0]) > L / 2 + 5) | (np.abs(g[:, 1]) > W / 2 + 5)] = np.nan
                ray = veo_camera.rays(cam, lens, np.column_stack([centre, b[:, 1]]))
                reach = np.linalg.norm(g[:, :2] - cam_pos[:2], axis=1)
                g[:, 2] = cam_pos[2] + ray[:, 2] * reach / np.maximum(np.linalg.norm(ray[:, :2], axis=1), 1e-9)
            per_lens.append(g)
        ground.append(per_lens)
    return ground


def veo_observations(run, ground) -> Observed:
    """Mit Veo: Boxen verketten, Einzelzuordnungen am Boden als Stimmen sammeln, je Folge und Zeitfenster die Mehrheit nehmen."""
    frames, tracks, align, n = run.frames, run.tracks, run.align, run.n
    chain = [link_tracklets(frames, lens) for lens in LENSES]
    votes, where, direct = [{}, {}], [], 0
    for fi, fr in enumerate(frames):
        people = veo_tracks.positions_at(tracks, run.start + fr["t"] + align["timeOffsetS"])
        where.append({(tracks[t]["team"], tracks[t]["jersey"]): p for t, p in people})
        for li, lens in enumerate(LENSES):
            b = np.array(fr[lens], float).reshape(-1, 6)
            if len(b):
                g = ground[fi][li]
                for tid, j, _ in veo_tracks.assign_ground(people, tracks, g[:, :2], b[:, 5], GATE):
                    votes[li].setdefault(int(chain[li][fi][j]), {})[fi] = (tracks[tid]["team"], tracks[tid]["jersey"])
    best = [{} for _ in range(n)]
    for li, lens in enumerate(LENSES):
        members = {}
        for fi, ids in enumerate(chain[li]):
            for j, t in enumerate(ids):
                members.setdefault(int(t), []).append((fi, j))
        for t, items in members.items():
            v = votes[li].get(t)
            if not v:
                continue
            vf = np.array(sorted(v))
            vk = [v[f] for f in vf]
            for fi, j in items:
                lo, hi = np.searchsorted(vf, [fi - VOTE_WINDOW, fi + VOTE_WINDOW + 1])
                if hi - lo < MIN_VOTES:
                    continue
                key, count = Counter(vk[lo:hi]).most_common(1)[0]
                g = ground[fi][li][j]
                if count < 0.6 * (hi - lo) or key[1] < 0 or key not in where[fi] or np.isnan(g[0]):
                    continue
                dist = float(np.linalg.norm(g[:2] - where[fi][key]))
                if dist > WIDE_GATE:
                    continue
                if key not in best[fi] or dist < best[fi][key][0]:
                    best[fi][key] = (dist, li, *frames[fi][lens][j][:4], *g, j, v.get(fi) == key)
    obs = {}
    for fi in range(n):
        for key, row in best[fi].items():
            obs.setdefault(key, np.full((n, 9), np.nan))[fi] = row[1:10]   # letzte Spalte: Nummer der Box im Bild
            direct += bool(row[10])
    total_boxes = sum(len(b) for b in best)
    veo_error = np.array([row[0] for b in best for row in b.values()])
    print(f"{total_boxes} Boxen mit Rückennummer, davon {total_boxes - direct} nur über die Verkettung; "
          f"Abstand Veo-Position zu unserem Fußpunkt: Median {np.median(veo_error):.2f} m, 90 % unter {np.percentile(veo_error, 90):.2f} m", flush=True)
    kit = {(tr["team"], tr["jersey"]): tr["cls"] for tr in run.tracks.values()}   # Farbklasse des Trikots je Spieler
    return Observed(obs, where, kit, set(), total_boxes)


def own_observations(run, ground) -> Observed:
    """Ohne Veo: Zuordnung Box -> Spieler direkt aus dem eigenen Tracking; „where“ ist die eigene Spur, über Lücken gerade
    verbunden (dort wird in vergrößerten Ausschnitten nach Liegenden gesucht)."""
    n, frames, cam, fps = run.n, run.frames, run.cam, run.fps
    identities = own_identities(run.det, cam, n, run.video)
    run.clock("Eigene Spuren")
    identities = with_numbers(identities, run.det, run.video, run.det_path, run.squad, cam=cam)
    run.clock("Rückennummern gelesen")
    obs, own_kit, keepers = {}, {}, set()
    where = [{} for _ in range(n)]
    for key, (colour, keeper, items) in identities.items():
        rows = np.full((n, 9), np.nan)
        for fi, r in items.items():
            li, j = int(r[3]), int(r[8])
            g = ground[fi][li][j]
            if np.isnan(g[0]):
                continue
            rows[fi] = (li, *frames[fi][LENSES[li]][j][:4], *g, j)
        seen = np.flatnonzero(~np.isnan(rows[:, 0]))
        if len(seen) < 2:
            continue
        obs[key] = rows
        own_kit[key] = colour if not keeper else -1
        if keeper:
            keepers.add(key)
        # Lücken bis OWN_GAP gerade verbinden; über längere Lücken ist der Spieler nicht da (er steckt dann oft in einer anderen Spur)
        bridged = np.zeros(n, bool)
        bridged[seen] = True
        for a, b in zip(seen[:-1], seen[1:]):
            if b - a <= OWN_GAP * fps:
                bridged[a:b] = True
        for fi in np.flatnonzero(bridged):
            where[fi][key] = np.array([np.interp(fi, seen, rows[seen, 5]), np.interp(fi, seen, rows[seen, 6])])
    removed = drop_same_place(obs, where)   # zwei Spuren an derselben Stelle sind eine Person
    total_boxes = int(sum((~np.isnan(b[:, 0])).sum() for b in obs.values()))
    print(f"Doppelte Spuren an derselben Stelle: {removed} Spieler-Bilder entfernt", flush=True)
    print(f"Eigenes Tracking: {len(obs)} Spuren auf dem Platz ({dict(Counter(k[0] for k in obs))}, davon {len(keepers)} Torwart), "
          f"{total_boxes} Boxen zugeordnet", flush=True)
    return Observed(obs, where, own_kit, keepers, total_boxes)


def observe(run) -> Observed:
    """Stufe 1: Boxen verketten und Spielern zuordnen, mit Veo über die Rückennummer, sonst über das eigene Tracking."""
    ground = ground_points(run)
    return own_observations(run, ground) if run.no_veo else veo_observations(run, ground)


def smooth_boxes(run, observed: Observed):
    """Stufe 2: Ausreißer entfernen (Box springt zu einem Nachbarn), Mitte und Höhe glätten. Entfernt Ausreißer in
    observed.obs. Rückgabe (smooth, heights): geglättete Reihen und Körpergröße je Spieler."""
    n, cam, size, where = run.n, run.cam, run.size, observed.where
    smooth, heights = {}, {}
    for key, b in observed.obs.items():
        cx, cy, h = (b[:, 1] + b[:, 3]) / 2, (b[:, 2] + b[:, 4]) / 2, b[:, 4] - b[:, 2]
        for li in (0, 1):  # Linsenwechsel verschiebt die Pixelkoordinaten: je Linse getrennt beurteilen
            m = b[:, 0] == li
            if m.sum() < 5:
                b[m] = np.nan
                continue
            mx = running_median(np.where(m, cx, np.nan), 21)
            my = running_median(np.where(m, cy, np.nan), 21)
            mh = running_median(np.where(m, h, np.nan), 31)
            # Die Boxhöhe selbst ist kein Ausreißermerkmal: Wer fällt, wird in wenigen Bildern niedrig.
            bad = m & (np.hypot(cx - mx, cy - my) > 0.6 * mh)
            b[bad] = np.nan
        have = ~np.isnan(b[:, 0])
        if have.sum() < MIN_SEGMENT:
            b[:] = np.nan
            continue
        cx, cy, h, w = (b[:, 1] + b[:, 3]) / 2, (b[:, 2] + b[:, 4]) / 2, b[:, 4] - b[:, 2], b[:, 3] - b[:, 1]
        heights[key] = float(np.clip(np.nanpercentile(b[:, 7], 60) * BOX_TO_BODY, 1.45, 1.95))
        # Höhe in Pixeln, die der Spieler an dieser Stelle stehend hätte
        stand = np.full(n, np.nan)
        for li, lens in enumerate(LENSES):
            m = b[:, 0] == li
            if m.any():
                foot = np.column_stack([b[m, 5:7], np.zeros(m.sum())])
                top = foot + [0, 0, heights[key] / BOX_TO_BODY]
                stand[m] = np.abs(veo_camera.project(cam, lens, top)[:, 1] - veo_camera.project(cam, lens, foot)[:, 1])
        # am Boden: Box sehr niedrig oder breiter als hoch; über ein paar Bilder beruhigt
        down, low = posture(b[:, 7], w, h, heights[key])
        share = running_median(np.where(have, b[:, 7] * BOX_TO_BODY / heights[key], np.nan), 5)   # Höhe des Körpers als Anteil der Körpergröße
        down = running_median(np.where(have, down.astype(float), np.nan), 7) > 0.5
        low = running_median(np.where(have, low.astype(float), np.nan), 7) > 0.5
        if key[0] != "referee":
            # Bilder ohne Box, in denen Veo die Position weiterführt: Linse, erwarteter Fußpunkt (u, v), Stehhöhe in Pixeln
            virtual = np.full((n, 4), np.nan)
            for fi in np.flatnonzero(~have):
                spot = where[fi].get(key)
                if spot is None:
                    continue
                margin = 5.0
                for li, lens in enumerate(LENSES):
                    uv = veo_camera.project(cam, lens, [[spot[0], spot[1], 0], [spot[0], spot[1], heights[key] / BOX_TO_BODY]])
                    inside = min(uv[0, 0], size[0] - uv[0, 0], uv[0, 1], size[1] - uv[0, 1])
                    if not np.isnan(uv).any() and inside > margin:
                        virtual[fi], margin = (li, uv[0, 0], uv[0, 1], abs(uv[1, 1] - uv[0, 1])), inside
            smooth[key] = {"lens": b[:, 0].copy(), "cx": cx, "cy": cy, "h": running_median(h, 31), "w": running_median(w, 5),
                           "stand": stand, "have": have, "down": down & have, "low": (low | down) & have, "virtual": virtual, "share": share}
    print(f"{len(smooth)} Spieler mit Boxfolge; im Mittel in {np.mean([s['have'].mean() for s in smooth.values()]):.0%} der Bilder zugeordnet", flush=True)
    print("Körpergröße aus der Boxhöhe (m):", {f"{k[0]}-{k[1]}": round(v, 2) for k, v in sorted(heights.items())}, flush=True)
    return smooth, heights
