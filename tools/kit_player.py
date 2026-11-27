#!/usr/bin/env python3
"""Was ein Spieler zusätzlich zum Mannschaftstrikot trägt, aus seiner Textur gelesen: Unterhemd mit langen Ärmeln, Handschuhe, Schuhfarbe.

Trikot, Hose und Stutzen sind je Mannschaft gleich (tools/kit_sheet.py, ein Blatt je Mannschaft). Was sich je Spieler unterscheidet, steht in der Kachel seiner Textur
(looks.png, tools/looks_from_photo.py): Der Unterarm zeigt Haut oder Stoff (langes Unterhemd), das Handende Haut oder Stoff (Handschuh), der Fuß die Schuhfarbe.
Nichts davon wird eingetragen oder geraten: Was die Textur nicht zeigt, bleibt leer (null).

Die Kachel der Bild-KI-Ansichten (tools/photo_ai.py) zeigt, was das Modell aus der Mannschaftsangabe ableitet (alle Spieler dieselben Ärmel, Schuhe frei erfunden). Deshalb liest
dieses Werkzeug die Kacheln der VIDEO-Textur (Szene vor dem Übertragen der Fotos, QUELLE): Dort stehen Unterarm, Hand und Fuß mit den Farben, die das Video zeigt; nur die Hautfarbe
(Nase, Wange) kommt aus der Szene mit den Fotos.

Aufruf:
    .venv/bin/python tools/kit_player.py SZENENORDNER [--quelle VIDEOSZENE]
Schreibt looks.kit.players.SPIELER = { baseLayer, gloves, boots } (Farben als "#rrggbb" oder null) in SZENENORDNER/meta.json.
"""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

SKIN_CHROMA = 16.0       # Farbart (a, b in Lab) bis zu diesem Abstand von der Hautfarbe zählt als Haut
SLEEVE_ROWS = (0.1, 0.6)  # Unterarm: Anteil der Kachelhöhe, in dem der Ärmel (Unterhemd) liegt
HAND_ROWS = (0.8, 0.97)   # Handende des Unterarms (t ≥ 1,16 von 0 bis 1,45)
GLOVE_DIFF = 40.0         # Lab-Abstand zum Ärmel, ab dem das Handende ein anderer Stoff ist (Handschuh trotz Unterhemd)
DARK_SLEEVE = 75.0        # Helligkeit (Lab L, 0 bis 255) unter der ein nicht hautfarbener Unterarm als dunkles Unterhemd gilt (Farbe wird neutral dunkel: das Videobild mischt Gras und Haut in die Kachel)
LIGHT = (205.0, 16.0)     # Helligkeit und Farbart, ab der ein Texel als weißer Rand der Schuhkachel gilt (nicht Schuh)


def lab_of(rgb):
    return cv2.cvtColor(np.uint8([[np.clip(rgb, 0, 255)]]), cv2.COLOR_RGB2LAB)[0, 0].astype(np.float32)


def is_skin(rgb, skin_rgb):
    a, b = lab_of(rgb), lab_of(skin_rgb)
    return float(np.linalg.norm(a[1:] - b[1:])) < SKIN_CHROMA and abs(float(a[0] - b[0])) < 70.0


def median_rgb(tile_bgr, rows=(0.0, 1.0)):
    h = tile_bgr.shape[0]
    part = tile_bgr[int(rows[0] * h):max(int(rows[1] * h), int(rows[0] * h) + 1)].reshape(-1, 3)
    return np.median(part[:, ::-1], axis=0)


def hex_of(rgb):
    return "#%02x%02x%02x" % tuple(int(round(float(v))) for v in np.clip(rgb, 0, 255))


def boot_colour(tile_bgr):
    """Hauptfarbe des Fußes: Median der Texel ohne den hellen, farblosen Rand (Hintergrund der Schuhkachel)."""
    px = tile_bgr.reshape(-1, 3)[:, ::-1].astype(np.uint8)
    lab = cv2.cvtColor(px.reshape(-1, 1, 3), cv2.COLOR_RGB2LAB).reshape(-1, 3).astype(np.float32)
    keep = ~((lab[:, 0] > LIGHT[0]) & (np.linalg.norm(lab[:, 1:] - 128.0, axis=1) < LIGHT[1]))
    use = px[keep] if keep.sum() > 20 else px
    return np.median(use.astype(np.float32), axis=0)


def neutral_dark(rgb):
    """Neutrales Dunkel mit der Helligkeit von `rgb`: Im Videobild mischt sich Rasengrün oder Hautton in das Schwarz des Unterhemds (Kachel aus wenigen Pixeln)."""
    lightness = float(lab_of(rgb)[0])
    return hex_of(cv2.cvtColor(np.uint8([[[lightness, 128, 128]]]), cv2.COLOR_LAB2RGB)[0, 0])


def variant_of(arm_tiles, foot_tiles, skin_rgb, detect_gloves=False):
    """{baseLayer, gloves, boots} aus den Unterarm- und Fußkacheln (BGR, links und rechts) und der Hautfarbe (RGB); Farben als "#rrggbb" oder None.
    baseLayer: Der Unterarm ist nicht hautfarben und dunkel (langes dunkles Unterhemd). boots: Hauptfarbe des Fußes.
    gloves nur mit detect_gloves: Das Handende ist nicht hautfarben (ohne Unterhemd) oder ein anderer Stoff als der Ärmel (mit Unterhemd). Die Hand ist in der Videokachel wenige
    Pixel groß und vermischt sich mit Rasen und Ärmel: Handschuhe sind darin nicht verlässlich zu erkennen, deshalb standardmäßig aus (null).
    Ohne Hautfarbe lässt sich nichts davon entscheiden: dann null (außer boots)."""
    arm = np.mean([median_rgb(t, SLEEVE_ROWS) for t in arm_tiles], axis=0)
    hand = np.mean([median_rgb(t, HAND_ROWS) for t in arm_tiles], axis=0)
    boots = np.mean([boot_colour(t) for t in foot_tiles], axis=0)
    out = {"baseLayer": None, "gloves": None, "boots": hex_of(boots)}
    if skin_rgb is None:
        return out
    sleeve = not is_skin(arm, skin_rgb) and float(lab_of(arm)[0]) < DARK_SLEEVE
    if sleeve:
        out["baseLayer"] = neutral_dark(arm)
    if detect_gloves:
        if sleeve and float(np.linalg.norm(lab_of(hand) - lab_of(arm))) > GLOVE_DIFF and not is_skin(hand, skin_rgb):
            out["gloves"] = hex_of(hand)
        elif not sleeve and not is_skin(hand, skin_rgb):
            out["gloves"] = hex_of(hand)
    return out


def main(scene_dir, source_dir=None):
    scene_dir = Path(scene_dir)
    source_dir = Path(source_dir) if source_dir else scene_dir
    meta_path = scene_dir / "meta.json"
    meta = json.loads(meta_path.read_text())
    looks = meta["looks"]
    src = json.loads((source_dir / "meta.json").read_text())["looks"]
    atlas = cv2.imread(str(source_dir / "looks.png"))
    tile, cols = src["tile"], src["columns"]
    seg = {s["name"]: s["rect"] for s in src["segments"]}
    skins = looks.get("skin", {})
    players = looks.setdefault("kit", {}).setdefault("players", {})
    for pid, k in src["players"].items():
        if pid not in looks["players"]:
            continue
        ty, tx = (k // cols) * tile, (k % cols) * tile

        def cut(name):
            x, y, w, h = seg[name]
            return atlas[ty + y:ty + y + h, tx + x:tx + x + w]
        skin = np.array(skins[pid], np.float32) if pid in skins else None
        players.setdefault(pid, {}).update(variant_of([cut("lowerarm_l"), cut("lowerarm_r")], [cut("foot_l"), cut("foot_r")], skin))
        print(f"{pid}: {({k_: v for k_, v in players[pid].items() if k_ in ('baseLayer', 'gloves', 'boots')})}")
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("szene")
    ap.add_argument("--quelle", help="Szene mit der Videotextur (Standard: SZENENORDNER selbst)")
    a = ap.parse_args()
    main(a.szene, a.quelle)
