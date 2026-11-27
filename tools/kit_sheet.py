#!/usr/bin/env python3
"""Das Mannschaftskit (Trikot, Hose, Stutzen) als sauberes Einzelteile-Bild von der Bild-KI erzeugen lassen: ein Blatt je Mannschaft.

Warum: Auf den Ansichten der Spieler (tools/photo_ai.py) sind Trikot, Hose und Stutzen ein Körper in einer Textur, ihre Kanten verlaufen ineinander (Zacken am Saum, schwammige
Flächen). Das Kit ist je Mannschaft gleich; es unterscheidet sich nur nach Größe (Körpermaße, im Viewer), Rückennummer und Rückenschrift (im Viewer aufgedruckt) und was ein Spieler
zusätzlich trägt (Unterhemd, Handschuhe, Schuhe: tools/kit_player.py). Die Bild-KI bekommt die vier Ansichten EINES Spielers der Mannschaft als Referenz und zeichnet ein Blatt mit
den Stücken einzeln auf neutralem Grund: Trikot vorn und hinten (ohne Nummer), Hose vorn und hinten, Stutzen. Das Blatt ist die Textur der Kleidungshüllen (web/garments.js).

Aufruf (Schlüssel OPENROUTER_API_KEY aus der Umgebung oder .env im Projektordner):
    python tools/kit_sheet.py MANNSCHAFT KI_ORDNER TEAMS.json --referenz SPIELER --ausgabe ORDNER [--modell M] [--max-kosten 0.5] [--neu] [--trocken]
    python tools/kit_sheet.py MANNSCHAFT KI_ORDNER TEAMS.json --referenz SPIELER --ausgabe ORDNER --szene web/data/SZENE     # vorhandenes Blatt in die Szene legen
KI_ORDNER ist der Ordner von photo_ai.py (SPIELER/hinten.png, vorn.png, links.png, rechts.png), TEAMS.json dieselbe Datei wie dort (Farben je Mannschaft).
Schreibt ORDNER/MANNSCHAFT_kit.png und trägt Kosten in ORDNER/kosten.jsonl ein; ein zweiter Aufruf mit gleicher Eingabe kostet nichts (--neu erzwingt neu).
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import photo_ai as ai  # noqa: E402
import photo_ai_bench as bench  # noqa: E402

ASPECT = "1:1"
VIEWS = ("vorn", "hinten", "links", "rechts")


def prompt_for(team):
    """Prompt (Englisch) für das Kit-Blatt einer Mannschaft aus ihren Fakten (Farben, Rückenschrift). Die Rückennummer fehlt absichtlich: Der Viewer druckt sie je Spieler auf."""
    text = "; ".join(team.get("backText") or [])
    back_print = (f'The back of the shirt carries only the text "{text}" in small letters across the upper back, nothing else.' if text
                  else "The back of the shirt is completely plain: no number, no name, no text, no logo, no print of any kind, even if the input images show a number.")
    front = team.get("front") or "plain: no number and no text; at most a tiny club crest on the left chest"
    return "\n".join([
        "The input images are photographs of one youth football player from the front, the back and both sides.",
        "Create ONE sharp, clean product sheet of only the team's playing kit: every garment drawn separately, laid out in a tidy grid with generous empty space between the items, "
        "on a plain light grey background, evenly lit from the front, like a catalogue flat-lay. No person, no mannequin, no body, no hands, no feet, no boots, no shadows on the floor, no labels or captions.",
        "Layout, top to bottom: (1) the short-sleeved shirt twice, seen from the front on the left and from the back on the right, laid flat with the sleeves spread out; "
        "(2) the shorts twice, front on the left and back on the right; (3) the pair of socks, each sock shown fully flat and complete from the top band to the toe. "
        "Do not draw any undershirt, gloves or boots.",
        f"Kit: {team['shirt']} shirt, {team['shorts']} shorts, {team['socks']} socks. The front of the shirt is {front}. {back_print}",
        "Copy exactly from the input images: the exact colours, the collar and its trim, sleeve cuffs and stripes, hem, the shorts' waistband and side stripes, the sock bands, "
        "every logo and crest. Do not invent patterns, text or logos that are not visible in the input. Render each item crisp with clean edges.",
        "Output only the image.",
    ])


ROWS = (("shirtFront", "shirtBack"), ("shortsFront", "shortsBack"), ("sockL", "sockR"))      # Zeilen des Blatts, je links und rechts


def boxes_of(sheet, threshold=18, min_area=800):
    """Rechtecke (x, y, Breite, Höhe in Pixeln) der Stücke auf dem Blatt: die größten Zusammenhänge gegen den hellen Grund, nach Zeile (Trikot, Hose, Stutzen) und links/rechts geordnet.
    None, wenn nicht genau sechs gefunden werden (dann hat die KI ein anderes Blatt gezeichnet)."""
    background = np.median(sheet[5:25, 5:25].reshape(-1, 3), axis=0)
    mask = (np.linalg.norm(sheet.astype(float) - background, axis=2) > threshold).astype(np.uint8)      # ohne Schließen: Die Ärmel der beiden Trikots liegen dicht beieinander und würden verschmelzen
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    items = sorted((tuple(int(v) for v in stats[i, :4]) for i in range(1, count) if stats[i, 4] > min_area), key=lambda r: r[1])
    if len(items) != 2 * len(ROWS):
        return None
    out = {}
    for row, (left, right) in zip(ROWS, (sorted(items[i:i + 2], key=lambda r: r[0]) for i in range(0, len(items), 2))):
        out[row[0]], out[row[1]] = list(left), list(right)
    return out


def _run_around(rows, centre):
    """Der zusammenhängende Bereich der Zeilen (Pixel), in dem `centre` liegt, als (erste, letzte): vereinzelte Ausreißer zählen nicht."""
    have = set(int(r) for r in rows)
    c = int(round(centre))
    if c not in have:
        c = min(have, key=lambda r: abs(r - c))
    lo = hi = c
    while lo - 1 in have:
        lo -= 1
    while hi + 1 in have:
        hi += 1
    return lo, hi


def shirt_shape(mask):
    """Form des Trikots auf dem Blatt aus seiner Silhouette (bool, Höhe × Breite des Trikotrechtecks), alles als Anteil des Rechtecks (x, y):
    body = [linker Rand, rechter Rand, Oberkante des Rumpfs] (Mittel über die Zeilen 55 bis 75 % der Höhe bzw. die Mittelspalte),
    sleeveS = Ansatz des linken Ärmels (Mitte des Ärmels an der Rumpfkante), sleeveC = Mitte seines Bündchens (äußerste 6 % der Breite),
    sleeveW = Höhe des Ärmels (Anteil der Rechteckhöhe) am Ansatz und am Bündchen (der Viewer hält damit die Abbildung in der Ärmelfläche). None, wenn das Trikot keinen Ärmel hat."""
    h, w = mask.shape
    rows = range(int(0.55 * h), int(0.75 * h))
    left = float(np.median([np.nonzero(mask[r])[0].min() for r in rows if mask[r].any()])) / w
    right = float(np.median([np.nonzero(mask[r])[0].max() for r in rows if mask[r].any()])) / w
    col = np.nonzero(mask[:, w // 2])[0]
    top = float(col.min()) / h if len(col) else 0.0
    xs, ys = np.nonzero(mask.T)
    outer = mask[:, :max(1, int(left * w) - 2)]
    if outer.sum() < 30:
        return None
    oy, ox = np.nonzero(outer)
    cuff = ox <= ox.min() + 0.06 * w
    edge = np.nonzero(mask[:, max(0, int(left * w) - 3)])[0]
    if not cuff.any() or not len(edge):
        return None
    seam = _run_around(edge, np.median(edge))
    rim = _run_around(oy[cuff], np.median(oy[cuff]))
    return {"body": [round(left, 4), round(right, 4), round(top, 4)], "sleeveS": [round(left, 4), round((seam[0] + seam[1]) / 2 / h, 4)],
            "sleeveC": [round(float(ox[cuff].mean()) / w, 4), round((rim[0] + rim[1]) / 2 / h, 4)],
            "sleeveW": [round((seam[1] - seam[0] + 1) / h, 4), round((rim[1] - rim[0] + 1) / h, 4)]}


SHORTS_ROWS = 8


def shorts_shape(mask):
    """Umriss der Hose auf dem Blatt (bool, Höhe × Breite ihres Rechtecks): linker und rechter Rand (Anteil der Breite) in SHORTS_ROWS gleich verteilten Höhen (Mitte der jeweiligen Zeilengruppe).
    Der Bund ist schmaler als der Saum; ohne das tastete die Hülle neben der Hose den hellen Grund ab. None, wenn eine Zeile leer ist."""
    h, w = mask.shape
    rows = []
    for k in range(SHORTS_ROWS):
        band = mask[int(h * (k + 0.25) / SHORTS_ROWS):max(int(h * (k + 0.75) / SHORTS_ROWS), int(h * (k + 0.25) / SHORTS_ROWS) + 1)]
        cols = np.nonzero(band.any(axis=0))[0]
        if not len(cols):
            return None
        rows.append([round(float(cols.min()) / w, 4), round(float(cols.max() + 1) / w, 4)])
    return rows


def extend_edges(sheet, threshold=18):
    """Blatt mit nach außen fortgesetzten Rändern: Der helle Grund neben jedem Stück bekommt dessen Randfarben (Abbildung der Hülle trifft knapp daneben, dann stünde sonst Grau im Stoff)."""
    background = np.median(sheet[5:25, 5:25].reshape(-1, 3), axis=0)
    item = (np.linalg.norm(sheet.astype(float) - background, axis=2) > threshold).astype(np.uint8)
    item = cv2.erode(cv2.morphologyEx(item, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)), np.ones((3, 3), np.uint8))     # Rand innen: ohne den hellen Saum
    return cv2.inpaint(sheet, (1 - item).astype(np.uint8), 12, cv2.INPAINT_TELEA)


SPECK_BRIGHT = 55            # ein Fleck ist so viel heller (Helligkeitsstufen) als der Stoff des Stücks
SPECK_DARK = 80              # oder so viel dunkler (schwarzes Etikett an weißer Hose)
SPECK_AREA = 0.008           # und höchstens so groß (Anteil der Stückfläche) und kompakt (ausgefüllter Anteil des Umrissrechtecks, Seitenverhältnis): Etikett, Punkt, Lichtreflex; kein Streifen, Bündchen oder Kragen
SPECK_FILL = 0.6
SPECK_ASPECT = 5


def remove_specks(sheet, boxes):
    """Kleine helle oder dunkle Etiketten aus den Hosenfeldern entfernen; Drucke auf Trikot und Stutzen bleiben erhalten."""
    grey = cv2.cvtColor(sheet, cv2.COLOR_BGR2GRAY).astype(float)
    out = sheet.copy()
    # Etiketten sitzen an den Shorts; kleine Kontraste auf dem Trikot können Wappen oder Druck sein.
    for name in ("shortsFront", "shortsBack"):
        x, y, w, h = boxes[name]
        part = grey[y:y + h, x:x + w]
        item = np.linalg.norm(sheet[y:y + h, x:x + w].astype(float) - np.median(sheet[5:25, 5:25].reshape(-1, 3), axis=0), axis=2) > 18
        if item.sum() < 100:
            continue
        median = np.median(part[item])
        bright = ((part > median + SPECK_BRIGHT) | (part < median - SPECK_DARK)) & item
        count, labels, stats, _ = cv2.connectedComponentsWithStats(bright.astype(np.uint8))
        mask = np.zeros(part.shape, np.uint8)
        for k in range(1, count):
            area, bw, bh = stats[k, cv2.CC_STAT_AREA], stats[k, cv2.CC_STAT_WIDTH], stats[k, cv2.CC_STAT_HEIGHT]
            if area <= SPECK_AREA * item.sum() and area >= SPECK_FILL * bw * bh and max(bw, bh) <= SPECK_ASPECT * min(bw, bh):
                mask[labels == k] = 1
        if mask.any():
            out[y:y + h, x:x + w] = cv2.inpaint(out[y:y + h, x:x + w], cv2.dilate(mask, np.ones((5, 5), np.uint8)), 4, cv2.INPAINT_TELEA)
    return out


def to_scene(sheet_path, scene_dir, team):
    """Kit-Blatt in eine Szene legen (web/data/SZENE/kit/MANNSCHAFT.png mit fortgesetzten Rändern) und Rechtecke in meta.json eintragen (looks.kit.teams): der Viewer zeigt sie standardmäßig."""
    sheet = cv2.imread(str(sheet_path))
    boxes = boxes_of(sheet)
    if boxes is None:
        sys.exit(f"{sheet_path}: nicht genau sechs Kleidungsstücke gefunden; Blatt neu erzeugen (--neu)")
    scene_dir = Path(scene_dir)
    (scene_dir / "kit").mkdir(exist_ok=True)
    x, y, w, h = boxes["shirtFront"]
    background = np.median(sheet[5:25, 5:25].reshape(-1, 3), axis=0)
    shape = shirt_shape(np.linalg.norm(sheet[y:y + h, x:x + w].astype(float) - background, axis=2) > 18)
    if shape is None:
        sys.exit(f"{sheet_path}: Trikotform nicht lesbar (kein Ärmel gefunden); Blatt neu erzeugen (--neu)")
    for key in ("shortsFront", "shortsBack"):
        bx, by, bw, bh = boxes[key]
        shape[key] = shorts_shape(np.linalg.norm(sheet[by:by + bh, bx:bx + bw].astype(float) - background, axis=2) > 18)
    cv2.imwrite(str(scene_dir / "kit" / f"{team}.png"), extend_edges(remove_specks(sheet, boxes)))
    meta_path = scene_dir / "meta.json"
    meta = json.loads(meta_path.read_text())
    meta.setdefault("looks", {}).setdefault("kit", {}).setdefault("teams", {})[team] = {"file": f"kit/{team}.png", "size": [sheet.shape[1], sheet.shape[0]], "boxes": boxes, "shape": shape}
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    print(f"{team}: Kit-Blatt in {scene_dir / 'kit'}, {len(boxes)} Rechtecke in meta.json")


def main(a):
    out = Path(a.ausgabe) / f"{a.team}_kit.png"
    if a.szene:
        return to_scene(out, a.szene, a.team)
    folder = Path(a.ausgabe)
    folder.mkdir(parents=True, exist_ok=True)
    team = json.loads(Path(a.teams).read_text())[a.team]
    refs = [Path(a.ki) / s / f"{v}.png" for s in a.referenz for v in VIEWS if (Path(a.ki) / s / f"{v}.png").exists()]
    if not refs:
        sys.exit(f"Keine Ansichten von {a.referenz} in {a.ki}")
    prompt = prompt_for(team)
    digest = hashlib.sha256((prompt + a.modell + "".join(hashlib.sha256(r.read_bytes()).hexdigest() for r in refs)).encode()).hexdigest()[:16]
    meta_path = folder / f"{a.team}_kit.json"
    if out.exists() and meta_path.exists() and json.loads(meta_path.read_text()).get("digest") == digest and not a.neu:
        print(f"schon vorhanden (gleiche Eingabe): {out}, kostet nichts")
        return
    if a.trocken:
        print(prompt)
        print(f"\nEingabe: {len(refs)} Ansichten; Modell {a.modell}")
        return
    known = {m["id"]: m for m in bench.image_models()}
    if a.modell not in known:
        sys.exit(f"Unbekannt bei OpenRouter: {a.modell}")
    began = time.time()
    raw, resp = bench.generate_image(known[a.modell], prompt, bench.data_url(refs[0], bench.INPUT_HEIGHT), [bench.data_url(r, bench.INPUT_HEIGHT) for r in refs[1:]], aspect=ASPECT)
    cost, source = bench.cost_of(resp.get("usage"), known[a.modell].get("pricing"))
    if cost > a.max_kosten:
        print(f"Warnung: Kosten {cost:.3f} USD über der Grenze {a.max_kosten:.2f} USD")
    out.write_bytes(raw)
    meta_path.write_text(json.dumps({"digest": digest, "model": a.modell, "cost": cost, "inputs": [str(r) for r in refs], "prompt": prompt}, indent=1, ensure_ascii=False))
    bench.ledger(folder, kind="kit", case=a.team, model=a.modell, cost=cost, source=source, seconds=round(time.time() - began, 1))
    print(f"{a.team}: ${cost:.4f} -> {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("team")
    ap.add_argument("ki")
    ap.add_argument("teams")
    ap.add_argument("--referenz", nargs="+", required=True, help="Spieler dieser Mannschaft, deren Ansichten als Eingabe dienen")
    ap.add_argument("--ausgabe", required=True)
    ap.add_argument("--modell", default=ai.MODEL)
    ap.add_argument("--max-kosten", type=float, default=0.5)
    ap.add_argument("--neu", action="store_true")
    ap.add_argument("--trocken", action="store_true")
    ap.add_argument("--szene", help="Szenenordner (web/data/SZENE): vorhandenes Blatt dort ablegen und Rechtecke in meta.json eintragen, ohne die KI aufzurufen")
    main(ap.parse_args())
