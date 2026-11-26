#!/usr/bin/env python3
"""Aus den Videoausschnitten je Spieler (tools/photo_candidates.py) mit einer Bild-KI scharfe Ansichten erzeugen (Rück-, Vorder-, Seitenansicht).

Das Modell kommt aus dem Vergleich in tools/photo_ai_bench.py (Standard: GPT Image 2.5 „sunburst“, Ersatz: Meta Muse). Der Prompt wird aus Fakten gebaut,
nicht geraten: Rückennummer aus der Spieler-Kennung, Trikotfarben und Rückenschrift je Mannschaft aus teams.json (einmal je Verein eintragen, auch was vorn auf dem Trikot steht: `front`), Haare,
Hautton und Statur aus dem Ausschnitt. Zwischengespeichert wird je Spieler, Ansicht, Modell und Eingabe: nur Neues kostet Geld, ein zweiter Lauf nichts.

Aufruf (Schlüssel OPENROUTER_API_KEY aus der Umgebung oder .env im Projektordner):
    python tools/photo_ai.py plan   KANDIDATEN TEAMS.json                       # Anzahl Bilder und Kosten, ohne Aufruf
    python tools/photo_ai.py lauf   KANDIDATEN TEAMS.json --ausgabe ORDNER      # erzeugen (Standard: alle vier Ansichten)
        [--ansichten hinten,vorn,links,rechts] [--spieler own-6 ...] [--modell M] [--ersatz M] [--max-kosten 3.0] [--trocken]
KANDIDATEN ist der Ordner von photo_candidates.py (index.json, SPIELER/ANSICHT.png).
Schreibt ORDNER/SPIELER/ANSICHT.png, ORDNER/index.json (Modell, Kosten, Prompt-Prüfsumme, Eingabe) und ORDNER/kosten.jsonl.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).parent))
import photo_ai_bench as bench  # noqa: E402

MODEL = "openai/gpt-image-2.5-sunburst"
FALLBACK = "meta/muse-image"
VIEWS = ("hinten", "vorn", "links", "rechts")
MAX_COST = 3.0
ALL_VIEWS = ("hinten", "vorn", "links", "rechts")
SIDES = ("links", "rechts")
REF_ORDER = {"hinten": ("vorn", "links", "rechts"), "vorn": ("hinten", "links", "rechts"),
             "links": ("vorn", "hinten", "rechts"), "rechts": ("vorn", "hinten", "links")}   # welche fertigen Ansichten als Eingabe für eine fehlende dienen
VIEW_NAME = {"hinten": "from behind", "vorn": "from the front", "links": "from his left side", "rechts": "from his right side"}
BENCH_LEDGER = Path(__file__).resolve().parent.parent / "data/work/ki-bench/kosten.jsonl"
SPREAD = 1.25          # Aufschlag für Wiederholungen bei Fehlern/Ablehnung in der Schätzung


def price_stats(model, known=None):
    """(Ø, min, max) USD je Bild aus den bezahlten Läufen des Vergleichs; ohne Daten aus der Preisliste von OpenRouter, sonst None."""
    costs = []
    if BENCH_LEDGER.exists():
        for line in BENCH_LEDGER.read_text().splitlines():
            e = json.loads(line)
            if e.get("kind") == "bild" and e.get("model") == model:
                costs.append(e["cost"])
    if costs:
        return sum(costs) / len(costs), min(costs), max(costs)
    price = float(((known or {}).get(model, {}).get("pricing") or {}).get("image") or 0)
    return (price, price, price) if price else None


def number_of(player):
    digits = "".join(c for c in player.split("-")[-1] if c.isdigit())
    return digits if 0 < len(digits) <= 2 else "?"   # Kennungen ab 1000 sind keine Trikotnummern


def jobs(cand_dir, teams, views, only, folder=None):
    """Alle (Spieler, Ansicht)-Aufträge, für die es einen Ausschnitt gibt, samt Prompt und Prüfsumme."""
    index = json.loads((Path(cand_dir) / "index.json").read_text())
    out = []
    for player, entry in index.items():
        if only and player not in only:
            continue
        team = teams.get(entry["team"])
        for v in views:
            src = Path(cand_dir) / player / f"{v}.png"
            if v not in entry["views"] or not src.exists():
                continue
            if team is None:
                sys.exit(f"Mannschaft {entry['team']!r} fehlt in teams.json (shirt, shorts, socks, backText, extra, front).")
            case = {"id": f"{player}-{v}", "player": player, "team": entry["team"], "view": v, "number": number_of(player)}
            prompt = bench.prompt_for(case, team)
            # Vorderansicht: die erzeugte Rückansicht desselben Spielers als zweites Bild, Seiten: Vorder- und Rückansicht, damit Haare, Gesicht und Statur zusammenpassen
            refs = []
            if folder and v == "vorn":
                refs = [Path(folder) / player / "hinten.png"]
            elif folder and v in ("links", "rechts"):
                refs = [Path(folder) / player / "vorn.png", Path(folder) / player / "hinten.png"]
            refs = [r for r in refs if r.exists()]
            if v == "vorn" and refs:
                prompt += ("\nImage 2 shows the same player from behind (already finished): his hair colour, hairstyle, hair length, skin tone, build and kit must match it exactly; "
                           "image 1 is the reference for the face and the front.")
            elif v in ("links", "rechts") and refs:
                names = {"vorn.png": "from the front", "hinten.png": "from behind"}
                prompt += "\n" + " ".join(f"Image {i + 2} shows the same player {names[r.name]} (already finished)." for i, r in enumerate(refs)) + \
                          " His face, hair colour, hairstyle, hair length, skin tone, build and kit must match them exactly; image 1 is only the reference for the side."
            digest = hashlib.sha256(prompt.encode() + src.read_bytes() + b"".join(r.read_bytes() for r in refs)).hexdigest()[:16]
            out.append({"case": case, "prompt": prompt, "src": src, "refs": refs, "digest": digest})
    return out


def fill_jobs(cand_dir, teams, views, only, folder, stage):
    """Ansichten, für die es keinen Videoausschnitt gibt, aus den fertigen Ansichten desselben Spielers erzeugen (statt sie aus dem Video zu füllen).
    stage "front_back": fehlendes hinten/vorn; stage "side": links, wenn beide Seiten fehlen (die andere Seite wird gespiegelt, siehe mirror_sides)."""
    index = json.loads((Path(cand_dir) / "index.json").read_text())
    out = []
    for player, entry in index.items():
        if only and player not in only:
            continue
        have = {v for v in ALL_VIEWS if (Path(folder) / player / f"{v}.png").exists()}
        if not have:
            continue
        team = teams.get(entry["team"])
        for v in views:
            if v in entry["views"] or v in have:
                continue
            if stage == "front_back" and v not in ("hinten", "vorn"):
                continue
            if stage == "side" and (v != "links" or any(sd in have for sd in SIDES)):
                continue
            refs = [Path(folder) / player / f"{r}.png" for r in REF_ORDER[v] if r in have]
            if not refs or team is None:
                continue
            case = {"id": f"{player}-{v}", "player": player, "team": entry["team"], "view": v, "number": number_of(player)}
            prompt = bench.prompt_for(case, team, crop=False)
            prompt += "\n" + " ".join(f"Image {i + 1} shows the same player {VIEW_NAME[r.stem]}." for i, r in enumerate(refs))
            digest = hashlib.sha256(prompt.encode() + b"".join(r.read_bytes() for r in refs)).hexdigest()[:16]
            out.append({"case": case, "prompt": prompt, "src": None, "refs": refs, "digest": digest})
    return out


def mirror_sides(folder, views, only=None):
    """Fehlt von einem Spieler genau eine Seite, ist sie das gespiegelte Bild der anderen (kostenlos, gleiche Person). Gibt die gespiegelten Dateien zurück."""
    folder = Path(folder)
    index_path = folder / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    done = []
    for d in sorted(p for p in folder.iterdir() if p.is_dir()):
        if only and d.name not in only:
            continue
        for src, dst in (("links", "rechts"), ("rechts", "links")):
            a, b = d / f"{src}.png", d / f"{dst}.png"
            if dst in views and a.exists() and not b.exists():
                cv2.imwrite(str(b), cv2.flip(cv2.imread(str(a)), 1))
                index.setdefault(d.name, {})[dst] = {"ok": True, "model": "gespiegelt", "cost": 0.0, "digest": "mirror:" + hashlib.sha256(a.read_bytes()).hexdigest()[:16], "mirrored_from": src}
                done.append(str(b))
    index_path.write_text(json.dumps(index, indent=1, ensure_ascii=False))
    return done


def fill_estimate(cand_dir, views, only, folder):
    """Wie viele Ansichten ohne Ausschnitt aus anderen Ansichten erzeugt werden müssen (ohne die gespiegelten) und wie viele gespiegelt werden."""
    index = json.loads((Path(cand_dir) / "index.json").read_text())
    gen = mirror = 0
    for player, entry in index.items():
        if (only and player not in only) or not entry["views"]:
            continue
        crops = set(entry["views"])
        gen += sum(1 for v in ("hinten", "vorn") if v in views and v not in crops and not (Path(folder) / player / f"{v}.png").exists())
        sides = [v for v in SIDES if v in views]
        have_side = [v for v in sides if v in crops or (Path(folder) / player / f"{v}.png").exists()]
        if len(sides) == 2 and not have_side:
            gen += 1
            mirror += 1
        elif len(sides) == 2 and len(have_side) == 1:
            mirror += 1
    return gen, mirror


def cached(index, job, models, folder):
    e = index.get(job["case"]["player"], {}).get(job["case"]["view"])
    if isinstance(models, str):
        models = (models,)
    return bool(e and e.get("ok") and e.get("digest") == job["digest"] and e.get("model") in models and (folder / job["case"]["player"] / f"{job['case']['view']}.png").exists())


def cmd_plan(a, jobs_=None):
    teams = json.loads(Path(a.teams).read_text())
    views = tuple(a.ansichten.split(","))
    folder = Path(getattr(a, "ausgabe", None) or "/nonexistent")
    todo = jobs(a.kandidaten, teams, views, set(a.spieler or []), folder)
    index = json.loads((folder / "index.json").read_text()) if (folder / "index.json").exists() else {}
    models = tuple(m for m in (a.modell, a.ersatz) if m)
    new = [j for j in todo if not cached(index, j, models, folder)]
    players = sorted({j["case"]["player"] for j in todo})
    stats = price_stats(a.modell)
    if not stats:   # kein Vergleichslauf vorhanden: Preisliste von OpenRouter (frei abrufbar)
        try:
            stats = price_stats(a.modell, {m["id"]: m for m in bench.image_models()})
        except Exception:   # noqa: BLE001
            stats = None
    print(f"{len(players)} Spieler mit Ausschnitt, {len(todo)} Ansichten ({', '.join(views)}), davon schon vorhanden {len(todo) - len(new)}, neu {len(new)}.")
    for t, v in sorted({(j['case']['team'], j['case']['view']) for j in todo}):
        print(f"  {t:9s} {v:7s} {sum(1 for j in todo if j['case']['team'] == t and j['case']['view'] == v)} Bilder")
    if stats:
        avg, lo, hi = stats
        print(f"Preis {a.modell}: Ø {avg:.3f}, {lo:.3f}–{hi:.3f} USD je Bild (aus dem Vergleich). Neu: Ø {len(new) * avg * SPREAD:.2f} USD (mit {int((SPREAD - 1) * 100)} % Aufschlag für Wiederholungen), "
              f"Obergrenze {max(len(new) * hi, len(new) * avg * SPREAD):.2f} USD.")
    else:
        print(f"Kein Preis für {a.modell} bekannt (python tools/photo_ai_bench.py modelle).")
    gen, mirror = fill_estimate(a.kandidaten, views, set(a.spieler or []), folder)
    if gen or mirror:
        print(f"Ohne Ausschnitt: {gen} Ansichten werden aus den anderen Ansichten desselben Spielers erzeugt, {mirror} Seiten gespiegelt (kostenlos).")
    cmd_plan.extra = gen
    return new


def mirror_needed(a):
    gen, mirror = fill_estimate(a.kandidaten, tuple(a.ansichten.split(",")), set(a.spieler or []), a.ausgabe)
    return bool(mirror)


def cmd_lauf(a):
    new = cmd_plan(a)
    for name, team in json.loads(Path(a.teams).read_text()).items():
        if team.get("test"):
            print(f"Hinweis: Mannschaft {name!r} hat test=true, ihre Rückenschrift ist erfunden (nur für Versuche).")
    if a.trocken or (not new and not getattr(cmd_plan, "extra", 0) and not mirror_needed(a)):
        return
    folder = Path(a.ausgabe)
    folder.mkdir(parents=True, exist_ok=True)
    teams = json.loads(Path(a.teams).read_text())
    index_path = folder / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    known = {m["id"]: m for m in bench.image_models()}
    models = [a.modell] + ([a.ersatz] if a.ersatz else [])
    cache_models = tuple(models)
    missing = [m for m in models if m not in known]
    if missing:
        sys.exit(f"Unbekannt bei OpenRouter: {missing}")
    spent = 0.0

    def run(batch):
        nonlocal spent
        for job in batch:
            case, player, view = job["case"], job["case"]["player"], job["case"]["view"]
            if spent >= a.max_kosten:
                print(f"Kostengrenze erreicht ({spent:.2f} von {a.max_kosten:.2f} USD), angehalten. Erneut starten (nur Fehlendes wird erzeugt) oder --max-kosten erhöhen.")
                break
            inputs = ([job["src"]] if job["src"] else []) + list(job["refs"])
            url = bench.data_url(inputs[0], bench.INPUT_HEIGHT)
            result = None
            for model in models:
                began = time.time()
                for attempt in range(2):
                    try:
                        raw, resp = bench.generate_image(known[model], job["prompt"], url, [bench.data_url(r, bench.INPUT_HEIGHT) for r in inputs[1:]])
                        cost, source = bench.cost_of(resp.get("usage"), known[model].get("pricing"))
                        spent += cost
                        out = folder / player / f"{view}.png"
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_bytes(raw)
                        bench.ledger(folder, kind="bild", case=case["id"], model=model, cost=cost, source=source, seconds=round(time.time() - began, 1))
                        result = {"ok": True, "model": model, "cost": cost, "digest": job["digest"], "input": str(inputs[0]), "from_crop": bool(job["src"]), "team": case["team"], "number": case["number"]}
                        break
                    except bench.ApiError as err:
                        result = {"ok": False, "error": str(err)[:300]}
                        if err.code in (400, 401, 402, 403, 404):   # Ablehnung/Konto: Wiederholung am selben Modell nützt nichts
                            break
                        time.sleep(5)
                    except Exception as err:   # noqa: BLE001
                        result = {"ok": False, "error": str(err)[:300]}
                        time.sleep(5)
                if result and result["ok"]:
                    break
                print(f"{case['id']}: {model} fehlgeschlagen ({result['error'][:100]})", flush=True)
            index.setdefault(player, {})[view] = result
            index_path.write_text(json.dumps(index, indent=1, ensure_ascii=False))
            if result["ok"]:
                print(f"{case['id']}: {result['model']} ${result['cost']:.4f} (Summe ${spent:.3f})", flush=True)
    # in Stufen, jede sieht die fertigen Bilder der vorigen: Rücken, Vorderseite (bekommt den Rücken), dann Ansichten ohne Ausschnitt aus den vorhandenen erzeugen,
    # dann die Seiten (bekommen Vorder- und Rückseite), die fehlende Seite aus der anderen erzeugen bzw. spiegeln
    views = tuple(a.ansichten.split(","))
    only = set(a.spieler or [])

    def crop_stage(stage):
        nonlocal index
        index = json.loads(index_path.read_text()) if index_path.exists() else index
        run([j for j in jobs(a.kandidaten, teams, views, only, folder) if j["case"]["view"] in stage and not cached(index, j, cache_models, folder)])

    def fill_stage(stage):
        nonlocal index
        index = json.loads(index_path.read_text()) if index_path.exists() else index
        run([j for j in fill_jobs(a.kandidaten, teams, views, only, folder, stage) if not cached(index, j, cache_models, folder)])

    crop_stage(("hinten",))
    crop_stage(("vorn",))
    fill_stage("front_back")
    crop_stage(("links", "rechts"))
    fill_stage("side")
    index = json.loads(index_path.read_text()) if index_path.exists() else index
    mirrored = mirror_sides(folder, views, only)
    if mirrored:
        print(f"{len(mirrored)} Seiten gespiegelt (kostenlos).")
    print(f"-> {folder} (Kosten dieses Laufs ${spent:.3f})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("plan", cmd_plan), ("lauf", cmd_lauf)):
        p = sub.add_parser(name)
        p.add_argument("kandidaten")
        p.add_argument("teams")
        p.add_argument("--ausgabe")
        p.add_argument("--ansichten", default=",".join(VIEWS))
        p.add_argument("--spieler", nargs="*")
        p.add_argument("--modell", default=MODEL)
        p.add_argument("--ersatz", default=FALLBACK, help="zweites Modell, wenn das erste ablehnt oder ausfällt; leer = keins")
        p.add_argument("--max-kosten", type=float, default=MAX_COST)
        p.add_argument("--trocken", action="store_true")
        p.set_defaults(fn=fn)
    a = ap.parse_args()
    if a.cmd == "plan" and not a.ausgabe:
        a.ausgabe = None
    a.fn(a)
