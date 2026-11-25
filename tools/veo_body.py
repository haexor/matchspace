#!/usr/bin/env python3
"""Liest den ganzen Körper jedes Spielers im Video: 3D-Gelenke, Hände, Füße, Kopfrichtung (SAM 3D Body, MHR-Körper).

Die Schablone aus tools/pose_fit.py (Laufzyklus plus 17 Bildpunkte) gibt keine mögliche Körperhaltung her, wenn sich Spieler überdecken oder drehen:
Füße im Boden, vertauschte Arme, falsche Kopfrichtung. Ein Körpermodell, das aus einem Bildausschnitt eine ganze, anatomisch mögliche Haltung
schätzt, liefert genau diese Teile. Es läuft je Person auf einem Ausschnitt; die Box kommt aus der Bahn des Spielers (nicht aus der Erkennung),
damit sich auch zwei Spieler im Zweikampf trennen, bei denen der Detektor nur eine Box liefert.

Läuft nicht im Projekt-venv, sondern in einer eigenen Umgebung (siehe docs/body-model.md): Das Modell braucht eigene Abhängigkeiten, und die Gewichte
(facebook/sam-3d-body-dinov3, SAM License) sind bei Hugging Face freizuschalten. Alles läuft lokal; es gehen keine Bilder hinaus.

Aufruf (im venv des Körpermodells):
    python tools/veo_body.py SZENE_ORDNER KAMERA.json VIDEO DETEKTIONEN.json.body.npz [--code models/sam-3d-body] [--von N --bis M] [--min-hoehe 50]
SZENE_ORDNER ist die fertige Szene (Bahnen der Spieler); VIDEO der Szenenabschnitt, in dem Bild n der Szene bei n * 29,97 / 25 liegt.

Ausgabe (npz), eine Zeile je Person und Bild:
    ids (E,)     Kennungen der Figuren (meta.entities)  player (n,)  Index darin      frame (n,)  Szenenbild      lens (n,)  0 links, 1 rechts
    box (n, 4)   Pixel der Linse                     kp3d (n, 70, 3)  MHR70 in Metern, Kamerakoordinaten des Ausschnitts
    kp2d (n, 70, 2)  Pixel der Linse                 cam_t (n, 3)  Verschiebung des Modells in den Ausschnitt   focal (n,)  Brennweite in Pixeln
"""
import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import veo_camera  # noqa: E402
from scene_overlay import LENSES, VIDEO_FPS, load_scene  # noqa: E402

REPO = "facebook/sam-3d-body-dinov3"
HEAD = 1.6               # m: Höhe für die Box über dem Fußpunkt
BOX_H, BOX_W = 1.05, 1.1  # Faktor auf die Bildhöhe des Spielers: Höhe und Breite der Box (breit genug für Ausfallschritte)
MIN_HEIGHT = 50          # Pixel: kleiner ist der Spieler für das Modell zu grob
LENS_W, LENS_H = 2048, 1024


def player_boxes(cam, tracks, f, players):
    """Je Spieler mit Position im Bild f: (Index, Linse, Box in Pixeln der Linse). Die Box kommt aus der Bahn."""
    out = []
    for e in players:
        p = tracks[f, e]
        if np.isnan(p[0]):
            continue
        for li, name in enumerate(LENSES):
            foot, head = veo_camera.project(cam, name, [[p[0], p[1], 0.0], [p[0], p[1], HEAD]])
            if np.isnan(foot).any() or np.isnan(head).any() or not (0 <= foot[0] < LENS_W and 0 <= foot[1] < LENS_H):
                continue
            h = abs(foot[1] - head[1]) * BOX_H
            cx, cy = foot[0], (foot[1] + head[1]) / 2
            out.append((e, li, [cx - BOX_W * h / 2, cy - h / 2, cx + BOX_W * h / 2, cy + h / 2], h))
            break
    return out


def main(scene, camera, video, out_path, code, first, last, min_height):
    sys.path.insert(0, str(code))
    from sam_3d_body import SAM3DBodyEstimator, load_sam_3d_body_hf
    meta, tracks = load_scene(scene)
    cam = veo_camera.load(camera)
    players = [i for i, e in enumerate(meta["entities"]) if e["kind"] == "player"]
    model, cfg = load_sam_3d_body_hf(REPO)
    est = SAM3DBodyEstimator(model, cfg)
    cap = cv2.VideoCapture(str(video))
    ratio = VIDEO_FPS / 25
    last = meta["frames"] if last is None else min(last, meta["frames"])
    rows = {k: [] for k in ("player", "frame", "lens", "box", "kp3d", "kp2d", "cam_t", "focal")}
    began = time.time()
    for f in range(first, last):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(f * ratio)))
        ok, image = cap.read()
        if not ok:
            break
        half = image.shape[0] // 2
        todo = [b for b in player_boxes(cam, tracks, f, players) if b[3] >= min_height]
        for li in (0, 1):
            mine = [b for b in todo if b[1] == li]
            if not mine:
                continue
            lens = cv2.cvtColor(image[li * half:(li + 1) * half], cv2.COLOR_BGR2RGB)
            res = est.process_one_image(lens, bboxes=np.array([b[2] for b in mine], np.float32))
            for (e, _, box, _), r in zip(mine, res):
                for key, value in (("player", e), ("frame", f), ("lens", li), ("box", box), ("kp3d", r["pred_keypoints_3d"]),
                                   ("kp2d", r["pred_keypoints_2d"]), ("cam_t", r["pred_cam_t"]), ("focal", float(r["focal_length"]))):
                    rows[key].append(value)
        if (f + 1) % 10 == 0 or f == last - 1:
            print(f"{f + 1}/{last} Bilder, {len(rows['player'])} Personen, {time.time() - began:.0f} s", flush=True)
            np.savez_compressed(out_path, ids=np.array([e["id"] for e in meta["entities"]]), **{k: np.array(v) for k, v in rows.items()})
    print(f"-> {out_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scene")
    ap.add_argument("camera")
    ap.add_argument("video")
    ap.add_argument("out")
    ap.add_argument("--code", default="models/sam-3d-body")
    ap.add_argument("--von", type=int, default=0)
    ap.add_argument("--bis", type=int, default=None)
    ap.add_argument("--min-hoehe", type=int, default=MIN_HEIGHT)
    a = ap.parse_args()
    main(a.scene, a.camera, a.video, a.out, a.code, a.von, a.bis, a.min_hoehe)
