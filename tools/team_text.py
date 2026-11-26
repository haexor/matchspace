#!/usr/bin/env python3
"""Rückenschrift einer Mannschaft aus dem Video gewinnen: Alle Spieler eines Vereins tragen denselben Aufdruck über der Nummer.

Ein einzelnes Bild gibt davon nur einen unleserlichen Fleck (Schrift 3 px stark). Hier wird die Rückenpartie (Schulterlinie bis etwa Rückenmitte) aus vielen
Bildern vieler Spieler einer Mannschaft entzerrt (Schultern und Hüfte aus der Haltung), aufeinander ausgerichtet (ECC, nur Verschiebung) und gemittelt.
Ergebnis je Mannschaft: ORDNER/TEAM_ruecken.png (Mittel), TEAM_einzeln.png (Beitragsbilder) und TEAM.json (Anzahl Bilder, Güte).

Aufruf:
    .venv/bin/python tools/team_text.py AUSGABEORDNER --szene VIDEO DET.json KAMERA.json HINTERGRUND.png SZENENORDNER [--szene ...] [--bilder 60]
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import photo_candidates as pc  # noqa: E402
import veo_camera  # noqa: E402
import veo_looks as vl  # noqa: E402

CANVAS = (320, 240)          # Breite, Höhe der entzerrten Rückenpartie
S_RANGE = (-0.85, 0.85)      # in halben Schulterbreiten um die Rückenmitte
T_RANGE = (-0.12, 0.62)      # von der Schulterlinie nach unten, in Rumpflängen (Schulter–Hüfte)
MIN_FACING = 0.88
MIN_GAP = 12                 # Bilder Abstand zwischen zwei Beiträgen desselben Spielers


def patch(frame_lens, cam, lens_name, world, n):
    """Entzerrte Rückenpartie (CANVAS) für eine Figur in einem Bild; None, wenn Punkte fehlen."""
    pts = np.array([world[n[k]] for k in ("lShoulder", "rShoulder", "lHip", "rHip")])
    uv = veo_camera.project(cam, lens_name, pts)
    if np.isnan(uv).any():
        return None
    ls, rs, lh, rh = uv
    sm, hm = (ls + rs) / 2, (lh + rh) / 2
    side, down = (rs - ls) / 2, hm - sm     # Bildrichtung nach rechts: von hinten liegt Spieler-links im Bild links
    # Zielpunkt (x, y) der Leinwand -> Bildpunkt: sm + s·side + t·down
    W, H = CANVAS
    s0, s1 = S_RANGE
    t0, t1 = T_RANGE
    src = np.float32([sm + s0 * side + t0 * down, sm + s1 * side + t0 * down, sm + s0 * side + t1 * down])
    dst = np.float32([[0, 0], [W, 0], [0, H]])
    m = cv2.getAffineTransform(src, dst)
    return cv2.warpAffine(frame_lens, m, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def feature(img):
    """Für die Ausrichtung: Helligkeit ohne Grundfarbe des Trikots (Aufdruck gegen Stoff)."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return g - cv2.GaussianBlur(g, (0, 0), 12)


def align_stack(patches, rounds=3):
    """Alle Beiträge auf ein gemeinsames Mittel ausrichten (nur Verschiebung), ungeeignete verwerfen. -> (Mittelbild, Beiträge, Gewichte)."""
    feats = [feature(p) for p in patches]
    ref = np.median(feats, axis=0)
    aligned, weights = list(patches), np.ones(len(patches))
    for _ in range(rounds):
        out, wts = [], []
        for p, f in zip(patches, feats):
            warp = np.eye(2, 3, dtype=np.float32)
            try:
                cc, warp = cv2.findTransformECC(ref.astype(np.float32), f, warp, cv2.MOTION_TRANSLATION,
                                                (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-4), None, 5)
            except cv2.error:
                cc = 0.0
            out.append(cv2.warpAffine(p, warp, CANVAS, flags=cv2.INTER_CUBIC + cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE))
            wts.append(max(float(cc), 0.0))
        aligned, weights = out, np.array(wts)
        keep = weights >= np.percentile(weights, 25)
        ref = np.average([feature(a) for a, k in zip(aligned, keep) if k], axis=0, weights=weights[keep])
    keep = weights >= np.percentile(weights, 25)
    mean = np.average([a.astype(np.float32) for a, k in zip(aligned, keep) if k], axis=0, weights=weights[keep])
    return np.clip(mean, 0, 255).astype(np.uint8), aligned, weights


def collect(video, det_path, camera_path, background_path, scene_dir, count):
    """Entzerrte Rückenpartien aus einer Szene: {Mannschaft: [(Beitrag, Spieler, Bild)]}, die besten `count` je Mannschaft, nicht zu viele von einem Spieler."""
    sc = vl.load_scene(video, det_path, camera_path, background_path, scene_dir)
    cap = cv2.VideoCapture(str(sc["video"]))
    H, n = sc["H"], sc["n"]
    teams = {}
    for player in sc["players"]:
        cands = pc.candidates(sc, player)["hinten"]
        teams.setdefault(player["team"], []).extend((c[0], player, c) for c in cands if c[4] >= MIN_FACING)
    out = {}
    for team, items in teams.items():
        items.sort(key=lambda it: -it[0])
        got, used, per_player = [], [], {}
        for score, player, c in items:
            if len(got) >= count:
                break
            if per_player.get(player["id"], 0) >= max(3, count // 6):   # nicht ein Spieler allein
                continue
            if any(pid == player["id"] and abs(fr - c[1]) < MIN_GAP for pid, fr in used):   # Nachbarbilder bringen nichts Neues
                continue
            f, li = c[1], c[2]
            cap.set(cv2.CAP_PROP_POS_FRAMES, min(int(round(f * sc["ratio"])), len(sc["det"]["frames"]) - 1))
            ok, image = cap.read()
            if not ok:
                continue
            p = patch(image[li * H:(li + 1) * H], sc["cam"], vl.LENSES[li], player["world"][f], n)
            if p is None:
                continue
            got.append((p, f"{Path(str(scene_dir)).name}:{player['id']}", int(f), float(c[5])))
            used.append((player["id"], int(f)))
            per_player[player["id"]] = per_player.get(player["id"], 0) + 1
        out[team] = got
    return out


def main(scenes, out_dir, count):
    """scenes: Liste (video, det, kamera, hintergrund, szenenordner). Beiträge aller Szenen werden je Mannschaft gemeinsam ausgerichtet und gemittelt."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pooled = {}
    for spec in scenes:
        got = collect(*spec, count)
        for team, items in got.items():
            print(f"  {Path(str(spec[4])).name}: {team}: {len(items)} Beiträge (Höhe im Bild {', '.join(str(round(i[3])) for i in items[:3])} ... px)", flush=True)
            pooled.setdefault(team, []).extend(items)
    for team, items in pooled.items():
        if len(items) < 5:
            print(f"{team}: nur {len(items)} brauchbare Bilder, übersprungen")
            continue
        patches = [i[0] for i in items]
        mean, aligned, weights = align_stack(patches)
        cv2.imwrite(str(out_dir / f"{team}_ruecken.png"), cv2.resize(mean, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC))
        order = np.argsort(-weights)[:4]
        cv2.imwrite(str(out_dir / f"{team}_einzeln.png"), np.hstack([patches[i] for i in order] + [mean]))
        players = sorted({i[1] for i in items})
        (out_dir / f"{team}.json").write_text(json.dumps({"images": len(patches), "sources": players, "weights": [round(float(w), 3) for w in weights]}, indent=1))
        print(f"{team}: {len(patches)} Bilder aus {len(players)} Quellen -> {out_dir / (team + '_ruecken.png')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ausgabe")
    ap.add_argument("--szene", nargs=5, action="append", metavar=("VIDEO", "DET", "KAMERA", "HINTERGRUND", "SZENENORDNER"), required=True, help="mehrfach: alle Szenen zusammen")
    ap.add_argument("--bilder", type=int, default=60, help="Beiträge je Mannschaft und Szene")
    a = ap.parse_args()
    main(a.szene, a.ausgabe, a.bilder)
