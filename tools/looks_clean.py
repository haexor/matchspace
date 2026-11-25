#!/usr/bin/env python3
"""Videotextur der Spieler aufbereiten: Aufdruckfleck entfernen, Schuhe säubern, Atlas vergrößern.

Die Videotextur (tools/veo_looks.py) hat je Spieler nur 64 × 64 Texel für den ganzen Rumpf; der Aufdruck auf dem Rücken ist im Video rund 20 Pixel
breit und wird dort zu einem verwischten Fleck samt Schmierstreifen. Der Viewer druckt die Rückennummer selbst scharf auf das Trikot (web/avatar.js,
wo die Nummer bekannt ist). Dahinter stört der verwischte Fleck. Hier:
 1. Der Fleck der Rückennummer (und was unter ihm an Aufdruck verschmiert ist) wird mit der Trikotfarbe ringsum überdeckt, aber nur bei Spielern mit
    bekannter Nummer: Bei unbekannter Nummer zeigt der Fleck wenigstens, dass dort etwas gedruckt ist. Kleine Schrift (Verein, Sponsor) lässt sich aus
    so wenigen Pixeln nicht lesen und wird nicht erfunden; ihr Schmierstreifen verschwindet mit.
 2. Die Fußkachel wird in der Schuhfarbe neu gemalt (tools/boot_look.py): kein Mosaik aus Schuh, Socke und Rasen.
 3. Der Atlas wird vergrößert, Körperteil für Körperteil und waagrecht umlaufend (keine Kante an der Naht): Weniger Treppen, nicht mehr Information.

Aufruf (nach tools/veo_looks.py):
    .venv/bin/python tools/looks_clean.py SZENENORDNER [--faktor 4]
Schreibt looks.png in größerer Auflösung neu und passt meta.looks an (tile, Rechtecke; Eintrag "cleaned"). Bricht ab, wenn es schon gelaufen ist.
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import boot_look  # noqa: E402

TORSO = "torso"
ROWS = (0.2, 0.9)             # Anteil der Kachelhöhe, in dem Aufdruck gesucht wird
COLS = (0.30, 0.70)           # Anteil der Kachelbreite um den Rücken (Naht liegt nach dem Rollen in der Mitte)
MIN_DELTA = 35.0              # Helligkeitsunterschied zum Trikot, ab dem ein Texel zum Aufdruck zählt
SMEAR = 0.6                   # Schmierstreifen und Hof: schon ab diesem Anteil von MIN_DELTA
MIN_PIXELS = 12               # kleinster Fleck, der als Nummer gilt


def luminance(img):
    return img[..., 0] * 0.114 + img[..., 1] * 0.587 + img[..., 2] * 0.299   # BGR


def print_mask(torso):
    """Aufdruck auf dem Rücken in der Rumpfkachel (h, w, 3 BGR): Maske (h, w) in Texeln der gerollten Kachel (Naht in der Mitte) oder None, wenn kein
    Fleck von mindestens MIN_PIXELS Texeln zu sehen ist. Heller Aufdruck auf dunklem Trikot oder umgekehrt."""
    h, w = torso.shape[:2]
    lum = luminance(np.roll(torso.astype(float), w // 2, axis=1))
    r0, r1, c0, c1 = int(ROWS[0] * h), int(ROWS[1] * h), int(COLS[0] * w), int(COLS[1] * w)
    shirt = float(np.median(lum[r0:r1]))
    diff = lum[r0:r1, c0:c1] - shirt
    sign = 1.0 if diff.max() >= -diff.min() else -1.0
    strong = (sign * diff) >= max(MIN_DELTA, 0.45 * float((sign * diff).max()))
    if int(strong.sum()) < MIN_PIXELS:
        return None
    mask = np.zeros((h, w), bool)
    mask[r0:r1, c0:c1] = (sign * diff) >= SMEAR * MIN_DELTA
    return mask


def erase(torso_hi, mask, factor, grow=2):
    """Maske (Texel der kleinen gerollten Kachel) samt Hof in der vergrößerten, gerollten Kachel (h, w, 3 float) mit der Trikotfarbe ringsum überdecken."""
    big = cv2.resize(mask.astype(np.uint8), (torso_hi.shape[1], torso_hi.shape[0]), interpolation=cv2.INTER_NEAREST)
    area = cv2.dilate(big, np.ones((2 * grow * factor + 1,) * 2, np.uint8)) > 0
    ring = (cv2.dilate(big, np.ones((4 * grow * factor + 1,) * 2, np.uint8)) > 0) & ~area
    if not ring.any():
        return torso_hi
    shirt = np.median(torso_hi[ring], axis=0)
    soft = cv2.GaussianBlur(area.astype(np.float32), (0, 0), factor)[..., None]
    return torso_hi * (1 - soft) + shirt * soft


def clean_back(torso_hi, torso_lo, factor):
    """Rückenaufdruck aus der vergrößerten Rumpfkachel entfernen. Rückgabe (Kachel, True) oder (unverändert, False), wenn kein Fleck zu sehen war."""
    mask = print_mask(torso_lo)
    if mask is None:
        return torso_hi, False
    w = torso_hi.shape[1]
    out = erase(np.roll(torso_hi.astype(float), w // 2, axis=1), mask, factor)
    return np.clip(np.roll(out, -(w // 2), axis=1), 0, 255).astype(np.uint8), True


def upscale_atlas(atlas, tile, columns, segments, factor):
    """Atlas (H, W, 3) mit Kacheln tile × tile: jedes Körperteil für sich vergrößern, waagrecht umlaufend (die Teile sind Zylinder: Naht ohne Kante)."""
    rows = atlas.shape[0] // tile
    out = np.zeros((rows * tile * factor, columns * tile * factor, 3), atlas.dtype)
    pad = 2
    for k in range(rows * columns):
        ty, tx = divmod(k, columns)
        for s in segments:
            x, y, w, h = s["rect"]
            part = atlas[ty * tile + y: ty * tile + y + h, tx * tile + x: tx * tile + x + w]
            wrapped = np.concatenate([part[:, -pad:], part, part[:, :pad]], axis=1)
            big = cv2.resize(wrapped, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)[:, pad * factor:(pad + w) * factor]
            out[(ty * tile + y) * factor:(ty * tile + y + h) * factor, (tx * tile + x) * factor:(tx * tile + x + w) * factor] = big
    return out


def clean_boots(atlas, tile, columns, segments, count):
    """Fußkacheln aller Spieler und Mannschaften in sauberer Schuhfarbe neu malen (tools/boot_look.py); Rückgabe: Zahl der geänderten Kacheln."""
    rect = {s["name"]: s["rect"] for s in segments}
    changed = 0
    for k in range(count):
        r, c = divmod(k, columns)

        def part(name):
            x, y, w, h = rect[name]
            return (slice(r * tile + y, r * tile + y + h), slice(c * tile + x, c * tile + x + w))
        sock = np.median(atlas[part("calf_l")].reshape(-1, 3), axis=0)
        colour = boot_look.shared_colour(atlas[part("foot_l")], atlas[part("foot_r")], sock)
        for name in ("foot_l", "foot_r"):
            area = atlas[part(name)]
            new = boot_look.clean_foot(area, sock, colour)
            if not np.array_equal(new, area):
                atlas[part(name)] = new
                changed += 1
    return changed


def main(scene_dir, factor):
    scene_dir = Path(scene_dir)
    meta = json.loads((scene_dir / "meta.json").read_text())
    looks = meta.get("looks")
    if not looks:
        raise SystemExit("keine Videotextur in der Szene (tools/veo_looks.py zuerst)")
    if looks.get("cleaned"):
        raise SystemExit("schon aufbereitet; die Szene neu bauen (tools/veo_scene.py), dann dieses Werkzeug")
    tile, columns, segments = looks["tile"], looks["columns"], looks["segments"]
    atlas = cv2.imread(str(scene_dir / looks["file"]))
    count = max([*looks["players"].values(), *looks.get("teams", {}).values()], default=-1) + 1
    boots = clean_boots(atlas, tile, columns, segments, count)
    big = upscale_atlas(atlas, tile, columns, segments, factor)
    tx, ty, tw, th = next(s for s in segments if s["name"] == TORSO)["rect"]
    entities = {e["id"]: e for e in meta["entities"]}
    erased = []
    for pid, k in looks["players"].items():
        if entities.get(pid, {}).get("number") is None:
            continue
        r, c = divmod(k, columns)
        lo = atlas[r * tile + ty: r * tile + ty + th, c * tile + tx: c * tile + tx + tw]
        y0, x0 = (r * tile + ty) * factor, (c * tile + tx) * factor
        new, found = clean_back(big[y0: y0 + th * factor, x0: x0 + tw * factor], lo, factor)
        if found:
            big[y0: y0 + th * factor, x0: x0 + tw * factor] = new
            erased.append(pid)
    cv2.imwrite(str(scene_dir / looks["file"]), big)
    looks["tile"] = tile * factor
    for s in segments:
        s["rect"] = [v * factor for v in s["rect"]]
    looks["cleaned"] = {"factor": factor, "numberBlobErased": erased, "boots": boots}
    (scene_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    print(f"Atlas {atlas.shape[1]}x{atlas.shape[0]} -> {big.shape[1]}x{big.shape[0]}; Schuhkacheln neu gemalt: {boots}; Nummernfleck entfernt: {', '.join(erased) or 'keiner'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scene")
    ap.add_argument("--faktor", type=int, default=4)
    a = ap.parse_args()
    main(a.scene, a.faktor)
