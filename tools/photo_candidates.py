#!/usr/bin/env python3
"""Je Spieler die besten Videobilder für eine Rück-, Vorder- und Seitenansicht heraussuchen und zuschneiden (Eingabe für die Bild-KI, tools/photo_ai.py).

Gewählt wird aus den Daten der Szene (Haltung, Kamera), ohne die Bilder zu dekodieren; nur die Gewinner werden aus dem Video geholt:
  - Ansicht: Wie frontal zeigt der Rumpf in die gewünschte Richtung (Rücken, Brust, links, rechts) zur Kamera? (Mindestens `MIN_FACING`.)
  - Größe: Höhe des Spielers im Bild in Pixeln (mehr Pixel, mehr Information).
  - Freistand: Der Umriss des Spielers darf sich kaum mit dem anderer Figuren überlappen (sonst steckt eine fremde Farbe im Ausschnitt).
  - Vollständig: Kopf und Füße liegen im Bild.
Aus den besten Kandidaten gewinnt das schärfste Bild (Varianz des Laplace-Filters im Rumpfbereich).

Aufruf:
    .venv/bin/python tools/photo_candidates.py VIDEO DETEKTIONEN.json KAMERA.json HINTERGRUND.png SZENENORDNER AUSGABEORDNER [--spieler own-6 ...]
Schreibt AUSGABEORDNER/SPIELER/ANSICHT.png, AUSGABEORDNER/index.json und eine Übersicht AUSGABEORDNER/uebersicht.png.
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import veo_camera  # noqa: E402
import veo_looks as vl  # noqa: E402

VIEWS = ("hinten", "vorn", "links", "rechts")
MIN_FACING = 0.8          # cos des Winkels zwischen Blickrichtung zum Spieler und der gewünschten Seite des Rumpfs (≈ 37°)
MIN_HEIGHT = 60           # Pixel: kleinere Spieler liefern zu wenig
MAX_OVERLAP = 0.04        # Anteil des Spielerrahmens, den andere Figuren überdecken dürfen
PAD = 0.18                # Rand um den Spieler (Anteil der Höhe)
SHARP_TOP = 6             # so viele beste Bilder je Ansicht werden auf Schärfe verglichen


def box(cam, lens_name, world, n, W, H):
    """Rahmen (x0, y0, x1, y1) einer Figur im Bild und ihre Höhe; None, wenn Kopf oder Füße außerhalb liegen. world: (20, 3)."""
    names = ["head", "nose", "lAnkle", "rAnkle", "lShoulder", "rShoulder", "lHip", "rHip", "lWrist", "rWrist", "lKnee", "rKnee"]
    pts = np.array([world[n[k]] for k in names if k in n])
    uv = veo_camera.project(cam, lens_name, pts)
    if np.isnan(uv).any():
        return None
    x0, y0 = uv.min(axis=0)
    x1, y1 = uv.max(axis=0)
    top = veo_camera.project(cam, lens_name, (world[n["head"]] + np.array([0, 0, 0.12]))[None])[0]
    y0 = min(y0, top[1])
    return np.array([x0, y0, x1, y1]), y1 - y0


def candidates(sc, player):
    """Je Ansicht eine nach Güte sortierte Liste (Güte, Bild, Linse, Rahmen) für einen Spieler."""
    n, cam, W, H = sc["n"], sc["cam"], sc["W"], sc["H"]
    out = {v: [] for v in VIEWS}
    others = sc["players"] + sc["others"]
    for f in np.flatnonzero(player["usable"]):
        li = int(player["lens"][f])
        if li < 0:
            continue
        lens_name = vl.LENSES[li]
        world = player["world"][f]
        got = box(cam, lens_name, world, n, W, H)
        if got is None:
            continue
        rect, height = got
        if height < MIN_HEIGHT or rect[0] < 4 or rect[2] > W - 4 or rect[1] < 4 or rect[3] > H - 4:
            continue
        hip, sh = (world[n["lHip"]] + world[n["rHip"]]) / 2, (world[n["lShoulder"]] + world[n["rShoulder"]]) / 2
        up = vl.unit(sh - hip)
        left = vl.unit(world[n["lShoulder"]] - world[n["rShoulder"]])
        front = vl.unit(np.cross(left, up))
        centre = cam["lenses"][lens_name]["centre"]
        view = vl.unit(centre - (hip + sh) / 2)
        facing = {"vorn": float(front @ view), "hinten": float(-front @ view), "links": float(left @ view), "rechts": float(-left @ view)}
        # Überlappung mit anderen Figuren im selben Bild
        overlap = 0.0
        area = (rect[2] - rect[0]) * (rect[3] - rect[1])
        for o in others:
            if o is player or not (o["world"][f, 0, 0] == o["world"][f, 0, 0]):
                continue
            b = box(cam, lens_name, o["world"][f], n, W, H)
            if b is None:
                continue
            ix = max(0.0, min(rect[2], b[0][2]) - max(rect[0], b[0][0]))
            iy = max(0.0, min(rect[3], b[0][3]) - max(rect[1], b[0][1]))
            overlap = max(overlap, ix * iy / max(area, 1.0))
        if overlap > MAX_OVERLAP:
            continue
        for v in VIEWS:
            if facing[v] >= MIN_FACING:
                out[v].append((facing[v] ** 2 * height * (1 - overlap), int(f), li, rect.copy(), facing[v], float(height)))
    for v in VIEWS:
        out[v].sort(key=lambda c: -c[0])
    return out


def main(video, det_path, camera_path, background_path, scene_dir, out_dir, only):
    sc = vl.load_scene(video, det_path, camera_path, background_path, scene_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(sc["video"]))
    H = sc["H"]

    def crop_of(f, li, rect):
        want = min(int(round(f * sc["ratio"])), len(sc["det"]["frames"]) - 1)
        cap.set(cv2.CAP_PROP_POS_FRAMES, want)
        ok, image = cap.read()
        lens = image[li * H:(li + 1) * H]
        w, h = rect[2] - rect[0], rect[3] - rect[1]
        x0, y0 = int(max(rect[0] - PAD * h, 0)), int(max(rect[1] - PAD * h, 0))
        x1, y1 = int(min(rect[2] + PAD * h, sc["W"])), int(min(rect[3] + PAD * h, H))
        return lens[y0:y1, x0:x1].copy(), (x0, y0, x1, y1)

    index, sheet_rows = {}, []
    for player in sc["players"]:
        if only and player["id"] not in only:
            continue
        cands = candidates(sc, player)
        entry = {"team": player["team"], "views": {}}
        tiles = []
        for v in VIEWS:
            top = cands[v][:SHARP_TOP]
            best = None
            for c in top:
                img, box_ = crop_of(c[1], c[2], c[3])
                body = img[int(img.shape[0] * 0.2):int(img.shape[0] * 0.65)]
                sharp = float(cv2.Laplacian(cv2.cvtColor(body, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
                if best is None or sharp * c[0] > best[0]:
                    best = (sharp * c[0], c, img, box_, sharp)
            if best is None:
                tiles.append(np.zeros((200, 120, 3), np.uint8))
                continue
            _, c, img, box_, sharp = best
            folder = out_dir / player["id"]
            folder.mkdir(exist_ok=True)
            cv2.imwrite(str(folder / f"{v}.png"), img)
            entry["views"][v] = {"frame": c[1], "lens": c[2], "facing": round(c[4], 2), "height_px": round(c[5]), "sharpness": round(sharp, 1), "box": [int(x) for x in box_]}
            tile = cv2.resize(img, (int(img.shape[1] * 200 / img.shape[0]), 200), interpolation=cv2.INTER_CUBIC)
            cv2.putText(tile, f"{player['id']} {v} B{c[1]}", (3, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1, cv2.LINE_AA)
            tiles.append(tile)
        index[player["id"]] = entry
        have = ", ".join(f"{v} B{e['frame']} ({e['height_px']} px)" for v, e in entry["views"].items()) or "keine brauchbare Ansicht"
        print(f"{player['id']}: {have}", flush=True)
        width = sum(t.shape[1] for t in tiles)
        sheet_rows.append(np.hstack(tiles))
    (out_dir / "index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False))
    if sheet_rows:
        width = max(r.shape[1] for r in sheet_rows)
        sheet = np.vstack([np.pad(r, ((0, 0), (0, width - r.shape[1]), (0, 0))) for r in sheet_rows])
        cv2.imwrite(str(out_dir / "uebersicht.png"), sheet)
    print(f"-> {out_dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ("video", "detektionen", "kamera", "hintergrund", "szenenordner", "ausgabe"):
        ap.add_argument(name)
    ap.add_argument("--spieler", nargs="*")
    a = ap.parse_args()
    main(a.video, a.detektionen, a.kamera, a.hintergrund, a.szenenordner, a.ausgabe, set(a.spieler or []))
