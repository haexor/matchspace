#!/usr/bin/env python3
"""Das Spielerkit (Trikot, Hose, Stutzen, Schuhe) als sauberes Einzelteile-Bild von der Bild-KI erzeugen lassen.

Warum: Auf den Ansichten der Spieler (tools/photo_ai.py) sind Trikot, Hose, Stutzen und Schuhe ein Körper in einer Textur, ihre Kanten verlaufen ineinander (Zacken am Saum,
Stutzen gehen in die Schuhe über, schwammige Flächen). Hier bekommt die Bild-KI die vier fertigen Ansichten eines Spielers und zeichnet daraus ein Blatt mit den Kleidungsstücken
einzeln und getrennt auf neutralem Grund (Trikot vorn und hinten, Hose, Stutzen, Schuhe). Das Blatt ist die Vorlage für eigene Kleidungsnetze statt der Körpertextur.

Aufruf (Schlüssel OPENROUTER_API_KEY aus der Umgebung oder .env im Projektordner):
    python tools/kit_sheet.py SPIELER KI_ORDNER TEAMS.json --ausgabe ORDNER [--modell M] [--max-kosten 0.5] [--neu]
KI_ORDNER ist der Ordner von photo_ai.py (SPIELER/hinten.png, vorn.png, links.png, rechts.png), TEAMS.json dieselbe Datei wie dort (Farben je Mannschaft).
Schreibt ORDNER/SPIELER_kit.png und trägt Kosten in ORDNER/kosten.jsonl ein; ein zweiter Aufruf mit gleicher Eingabe kostet nichts (--neu erzwingt neu).
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import photo_ai as ai  # noqa: E402
import photo_ai_bench as bench  # noqa: E402

ASPECT = "1:1"
VIEWS = ("vorn", "hinten", "links", "rechts")


def prompt_for(team, number):
    """Prompt (Englisch) für das Kit-Blatt eines Spielers aus den Fakten der Mannschaft (Farben, Rückenschrift, Unterhemd) und der Rückennummer."""
    back = []
    text = "; ".join(team.get("backText") or [])
    if number != "?":
        back.append(f'the player number "{number}" in large block digits')
    if text:
        back.append(f'above it the text "{text}"')
    back_print = ("The back of the shirt carries " + " and ".join(back) + ", nothing else.") if back else "The back of the shirt is plain, without any print."
    front = team.get("front") or "plain: no number and no text; at most a tiny club crest on the left chest"
    lines = [
        "The input images are photographs of one youth football player from the front, the back and both sides.",
        "Create ONE sharp, clean product sheet of only his playing kit: every garment drawn separately, laid out in a tidy grid with generous empty space between the items, "
        "on a plain light grey background, evenly lit from the front, like a catalogue flat-lay. No person, no mannequin, no body, no hands, no feet, no shadows on the floor, no labels or captions.",
        "Layout, top to bottom: (1) the short-sleeved shirt twice, seen from the front on the left and from the back on the right, laid flat with the sleeves spread out; "
        "(2) the shorts twice, front on the left and back on the right; (3) the pair of socks, each sock shown fully flat and complete from the top band to the toe, "
        "separate from the boots; (4) the pair of football boots, shown from the side, separate from the socks.",
        f"Kit: {team['shirt']} shirt, {team['shorts']} shorts, {team['socks']} socks. "
        + (f"Under the shirt he wears {team['extra']}: show them as a separate long-sleeved base layer, laid flat. " if team.get("extra") else "")
        + f"The front of the shirt is {front}. {back_print}",
        "Copy exactly from the input images: the exact colours, the collar and its trim, sleeve cuffs and stripes, hem, the shorts' waistband and side stripes, the sock bands, the boots' colours, "
        "every logo and crest. Do not invent patterns, text or logos that are not visible in the input. Render each item crisp with clean edges.",
        "Output only the image.",
    ]
    return "\n".join(lines)


def main(a):
    folder = Path(a.ausgabe)
    folder.mkdir(parents=True, exist_ok=True)
    teams = json.loads(Path(a.teams).read_text())
    index = json.loads((Path(a.ki) / "index.json").read_text())
    team = teams[json.loads((Path(a.ki).parent / "kandidaten" / "index.json").read_text())[a.spieler]["team"]] if (Path(a.ki).parent / "kandidaten" / "index.json").exists() else teams[a.team]
    refs = [Path(a.ki) / a.spieler / f"{v}.png" for v in VIEWS if (Path(a.ki) / a.spieler / f"{v}.png").exists()]
    if not refs:
        sys.exit(f"Keine Ansichten von {a.spieler} in {a.ki}")
    number = ai.number_of(a.spieler)
    prompt = prompt_for(team, number)
    digest = hashlib.sha256((prompt + a.modell + "".join(hashlib.sha256(r.read_bytes()).hexdigest() for r in refs)).encode()).hexdigest()[:16]
    out = folder / f"{a.spieler}_kit.png"
    meta_path = folder / f"{a.spieler}_kit.json"
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
    bench.ledger(folder, kind="kit", case=a.spieler, model=a.modell, cost=cost, source=source, seconds=round(time.time() - began, 1))
    print(f"{a.spieler}: ${cost:.4f} -> {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spieler")
    ap.add_argument("ki")
    ap.add_argument("teams")
    ap.add_argument("--ausgabe", required=True)
    ap.add_argument("--team", help="Mannschaft in TEAMS.json, wenn KI_ORDNER/../kandidaten/index.json fehlt")
    ap.add_argument("--modell", default=ai.MODEL)
    ap.add_argument("--max-kosten", type=float, default=0.5)
    ap.add_argument("--neu", action="store_true")
    ap.add_argument("--trocken", action="store_true")
    main(ap.parse_args())
