#!/usr/bin/env python3
"""Mannschaftsdaten für tools/photo_ai.py selbst erkennen (teams.json), nichts von Hand eintragen.

  - Farben von Trikot, Hose, Stutzen und langen Unterziehärmeln aus der Videotextur der Spieler (Mittelwert über die Mannschaft, benannt nach der
    nächsten Standardfarbe).
  - Rückenschrift: aus entzerrten, übereinandergelegten Rückenbildern der Mannschaft (tools/team_text.py) liest ein Bildmodell nur, was wirklich zu sehen
    ist; Buchstaben, die es nicht erkennt, bleiben `?`. Übernommen wird der Text nur bei Sicherheit >= MIN_CONFIDENCE und ohne `?`. Sonst bleibt die
    Schrift leer: lieber kein Text als ein erfundener. (`backTextRead` hält fest, was gelesen wurde.)
  - Vorderseite: schlicht (nichts erfinden).

Aufruf:
    .venv/bin/python tools/team_detect.py SZENENORDNER AUSGABE_TEAMS.json [--ruecken ORDNER_von_team_text.py] [--kandidaten ORDNER_von_photo_candidates.py] [--ohne-lesen]
"""
import argparse
import base64
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import photo_ai_bench as bench  # noqa: E402
import veo_looks as vl  # noqa: E402

MIN_CONFIDENCE = 0.7
HUES = [(15, "red"), (35, "orange"), (50, "yellow"), (95, "green"), (140, "light blue"), (165, "blue"), (200, "purple"), (235, "pink"), (255, "red")]   # Farbton 0..255 (OpenCV-Halbgrad * 255/180)


def colour_name(bgr):
    """Farbname nach Sättigung und Farbton: Video verschiebt Helligkeit und Weiß (bläulich, dunkel), der Farbton bleibt. Wenig Sättigung: weiß/grau/schwarz nach Helligkeit."""
    h, sat, v = cv2.cvtColor(np.uint8([[np.clip(bgr, 0, 255)]]), cv2.COLOR_BGR2HSV_FULL)[0, 0].astype(float)
    if v < 55:
        return "black"
    if sat < 100:
        return "white" if v > 115 else "grey"
    hue = h
    return next(n for lim, n in HUES if hue <= lim)


def segment_pixels(atlas, tx, ty, f, name, rows=(0.0, 1.0)):
    seg = next(s for s in vl.SEGMENTS if s[0] == name)
    x, y, w, h = (v * f for v in seg[1])
    px = atlas[ty + y + int(h * rows[0]):ty + y + int(h * rows[1]), tx + x:tx + x + w].reshape(-1, 3)
    return px[px.sum(axis=1) > 45]          # unbelegte (schwarze) Texel weglassen


def colours(scene_dir):
    meta = json.loads((Path(scene_dir) / "meta.json").read_text())["looks"]
    atlas = cv2.imread(str(Path(scene_dir) / "looks.png"))
    cols, tile = meta["columns"], meta["tile"]
    f = tile // vl.TILE
    teams = {}
    for player, k in meta["players"].items():
        team = player.split("-")[0]
        if team in ("referee",):
            continue
        ty, tx = (k // cols) * tile, (k % cols) * tile
        part = lambda name, rows=(0.0, 1.0): segment_pixels(atlas, tx, ty, f, name, rows)   # noqa: E731
        info = {"shirt": part("torso", (0.35, 0.75)), "shorts": np.vstack([part("thigh_l", (0.4, 0.8)), part("thigh_r", (0.4, 0.8))]),
                "socks": np.vstack([part("calf_l", (0.2, 0.9)), part("calf_r", (0.2, 0.9))]),
                }
        for key, px in info.items():
            if len(px) > 30:
                teams.setdefault(team, {}).setdefault(key, []).append(np.median(px, axis=0))
    out = {}
    for team, parts in teams.items():
        med = {k: np.median(v, axis=0) for k, v in parts.items()}
        entry = {k: colour_name(med[k]) for k in ("shirt", "shorts", "socks") if k in med}
        out[team] = entry
    return out


def black_sleeves(cand_dir, team):
    """Lange schwarze Ärmel: Anteil fast schwarzer Pixel an den Seiten des Rumpfbands in den echten Ausschnitten (Median über die Spieler); True/False/None (zu wenige)."""
    index = json.loads((Path(cand_dir) / "index.json").read_text())
    shares = []
    for p, v in index.items():
        if v["team"] != team:
            continue
        for view in ("hinten", "vorn"):
            if view not in v["views"]:
                continue
            im = cv2.imread(str(Path(cand_dir) / p / f"{view}.png"))
            mask = vl_mask(im)
            if mask is None:
                continue
            h = im.shape[0]
            r0, r1 = int(h * 0.22), int(h * 0.50)
            xs = np.nonzero(mask[r0:r1].any(axis=0))[0]
            if len(xs) < 10:
                continue
            x0, x1 = xs.min(), xs.max()
            side = np.zeros_like(mask[r0:r1])
            w = x1 - x0
            side[:, x0:x0 + int(0.28 * w)] = True
            side[:, x1 - int(0.28 * w):x1 + 1] = True
            region = mask[r0:r1] & side
            if region.sum() < 40:
                continue
            dark = cv2.cvtColor(im[r0:r1], cv2.COLOR_BGR2HSV)[..., 2] < 60
            shares.append(float((dark & region).sum() / region.sum()))
    return (float(np.median(shares)) > 0.3) if len(shares) >= 2 else None


def vl_mask(im):
    r = vl.segmenter().predict(im, imgsz=320, classes=[0], conf=0.3, retina_masks=True, verbose=False)[0]
    if r.masks is None:
        return None
    return (r.masks.data.cpu().numpy() > 0.5).any(axis=0)


def read_text(image_paths):
    """Ein Bildmodell liest die Rückenschrift aus unscharfen Ausschnitten; nur Gesehenes, `?` für Unleserliches. -> (line1, line2, Sicherheit, Notiz)."""
    prompt = ("These are enlarged crops from the back of football shirts of ONE youth team (same print on every shirt): a club name in white letters above the player number, "
              "possibly a smaller second line. The images are very blurry (low-resolution video).\n"
              "Read ONLY what you can actually see. Do not guess or complete a name from your knowledge. Mark each letter you cannot read with '?'.\n"
              "Answer as JSON only: {\"line1\": \"...\", \"line2\": \"...\", \"confidence\": 0..1, \"notes\": \"...\"} (line2 = \"\" if no second line is visible).")
    urls = []
    for p in image_paths:
        ok, buf = cv2.imencode(".png", cv2.imread(str(p)))
        urls.append("data:image/png;base64," + base64.b64encode(buf).decode())
    r = bench.request("/chat/completions", {"model": bench.JUDGE, "usage": {"include": True}, "temperature": 0.2,
                                            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}] + [{"type": "image_url", "image_url": {"url": u}} for u in urls]}]})
    text = r["choices"][0]["message"]["content"]
    data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
    return data.get("line1", ""), data.get("line2", ""), float(data.get("confidence", 0)), data.get("notes", "")


def main(scene_dir, out_path, back_dir, cand_dir, read, infer=True):
    teams = colours(scene_dir)
    for team, entry in teams.items():
        entry.update({"backText": [], "front": None})
        entry.pop("front")
        if infer and cand_dir and black_sleeves(cand_dir, team):
            entry["extra"] = "black long undershirt sleeves"
        if not read:
            continue
        paths = []
        if cand_dir:   # echte Rückenausschnitte der Mannschaft, Schriftband 6-fach vergrößert
            index = json.loads((Path(cand_dir) / "index.json").read_text())
            for p, v in index.items():
                if v["team"] == team and "hinten" in v["views"]:
                    im = cv2.imread(str(Path(cand_dir) / p / "hinten.png"))
                    h = im.shape[0]
                    out = Path(out_path).parent / "team-text" / f"{p}_band.png"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    cv2.imwrite(str(out), cv2.resize(im[int(h * 0.18):int(h * 0.50)], None, fx=6, fy=6, interpolation=cv2.INTER_CUBIC))
                    paths.append(out)
        if back_dir and (Path(back_dir) / f"{team}_ruecken.png").exists():
            paths.append(Path(back_dir) / f"{team}_ruecken.png")
        if not paths:
            continue
        l1, l2, conf, notes = read_text(paths[:6])
        entry["backTextRead"] = {"line1": l1, "line2": l2, "confidence": conf}
        lines = [t for t in (l1, l2) if t]
        if conf >= MIN_CONFIDENCE and lines and not any("?" in t for t in lines):
            entry["backText"] = lines
        print(f"{team}: Schrift gelesen {lines or '-'} (Sicherheit {conf:.2f}) -> {'übernommen' if entry['backText'] else 'NICHT übernommen (unleserlich), keine Rückenschrift'}")
    Path(out_path).write_text(json.dumps(teams, indent=1, ensure_ascii=False))
    print(f"-> {out_path}: " + "; ".join(f"{t}: {e.get('shirt')}/{e.get('shorts')}/{e.get('socks')}" + (f" + {e['extra']}" if e.get('extra') else "") for t, e in teams.items()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("szenenordner")
    ap.add_argument("ausgabe")
    ap.add_argument("--ruecken")
    ap.add_argument("--kandidaten")
    ap.add_argument("--ohne-lesen", action="store_true")
    a = ap.parse_args()
    main(a.szenenordner, a.ausgabe, a.ruecken, a.kandidaten, not a.ohne_lesen)
