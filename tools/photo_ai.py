#!/usr/bin/env python3
"""Aus den Videoausschnitten je Spieler (tools/photo_candidates.py) mit einer Bild-KI scharfe Ansichten erzeugen (Rück-, Vorder-, Seitenansicht).

Das Modell kommt aus dem Vergleich in tools/photo_ai_bench.py (Standard: GPT Image 2.5 „sunburst“, Ersatz: Meta Muse). Der Prompt wird aus Fakten gebaut,
nicht geraten: Rückennummer aus der Spieler-Kennung, Trikotfarben und Rückenschrift je Mannschaft aus teams.json (einmal je Verein eintragen, auch was vorn auf dem Trikot steht: `front`), Haare,
Hautton und Statur aus dem Ausschnitt. Zwischengespeichert wird je Spieler, Ansicht, Modell und Eingabe: nur Neues kostet Geld, ein zweiter Lauf nichts.

Aufruf (Schlüssel OPENROUTER_API_KEY aus der Umgebung oder .env im Projektordner):
    python tools/photo_ai.py plan   KANDIDATEN TEAMS.json                       # Anzahl Bilder und Kosten, ohne Aufruf
    python tools/photo_ai.py lauf   KANDIDATEN TEAMS.json --ausgabe ORDNER      # erzeugen (Standard: nur hinten, vorn)
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

sys.path.insert(0, str(Path(__file__).parent))
import photo_ai_bench as bench  # noqa: E402

MODEL = "openai/gpt-image-2.5-sunburst"
FALLBACK = "meta/muse-image"
VIEWS = ("hinten", "vorn")
MAX_COST = 3.0
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
            # Vorderansicht: die erzeugte Rückansicht desselben Spielers als zweites Bild, damit Haare und Statur zusammenpassen
            ref = Path(folder) / player / "hinten.png" if folder and v == "vorn" else None
            ref = ref if ref and ref.exists() else None
            if ref:
                prompt += ("\nImage 2 shows the same player from behind (already finished): his hair colour, hairstyle, hair length, skin tone, build and kit must match it exactly; "
                           "image 1 is the reference for the face and the front.")
            digest = hashlib.sha256(prompt.encode() + src.read_bytes() + (ref.read_bytes() if ref else b"")).hexdigest()[:16]
            out.append({"case": case, "prompt": prompt, "src": src, "ref": ref, "digest": digest})
    return out


def cached(index, job, model, folder):
    e = index.get(job["case"]["player"], {}).get(job["case"]["view"])
    return bool(e and e.get("ok") and e.get("digest") == job["digest"] and e.get("model") == model and (folder / job["case"]["player"] / f"{job['case']['view']}.png").exists())


def cmd_plan(a, jobs_=None):
    teams = json.loads(Path(a.teams).read_text())
    views = tuple(a.ansichten.split(","))
    folder = Path(getattr(a, "ausgabe", None) or "/nonexistent")
    todo = jobs(a.kandidaten, teams, views, set(a.spieler or []), folder)
    index = json.loads((folder / "index.json").read_text()) if (folder / "index.json").exists() else {}
    new = [j for j in todo if not cached(index, j, a.modell, folder)]
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
    return new


def cmd_lauf(a):
    new = cmd_plan(a)
    for name, team in json.loads(Path(a.teams).read_text()).items():
        if team.get("test"):
            print(f"Hinweis: Mannschaft {name!r} hat test=true, ihre Rückenschrift ist erfunden (nur für Versuche).")
    if a.trocken or not new:
        return
    folder = Path(a.ausgabe)
    folder.mkdir(parents=True, exist_ok=True)
    teams = json.loads(Path(a.teams).read_text())
    index_path = folder / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    known = {m["id"]: m for m in bench.image_models()}
    models = [a.modell] + ([a.ersatz] if a.ersatz else [])
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
            url = bench.data_url(job["src"], bench.INPUT_HEIGHT)
            result = None
            for model in models:
                began = time.time()
                for attempt in range(2):
                    try:
                        raw, resp = bench.generate_image(known[model], job["prompt"], url, [bench.data_url(job["ref"], bench.INPUT_HEIGHT)] if job["ref"] else ())
                        cost, source = bench.cost_of(resp.get("usage"), known[model].get("pricing"))
                        spent += cost
                        out = folder / player / f"{view}.png"
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_bytes(raw)
                        bench.ledger(folder, kind="bild", case=case["id"], model=model, cost=cost, source=source, seconds=round(time.time() - began, 1))
                        result = {"ok": True, "model": model, "cost": cost, "digest": job["digest"], "input": str(job["src"]), "team": case["team"], "number": case["number"]}
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
    # Rückansichten zuerst; die Vorderansichten bekommen danach die fertige Rückansicht als zweites Bild
    run([j for j in new if j["case"]["view"] != "vorn"])
    index = json.loads(index_path.read_text()) if index_path.exists() else index
    run([j for j in jobs(a.kandidaten, teams, tuple(a.ansichten.split(",")), set(a.spieler or []), folder) if not cached(index, j, a.modell, folder) and j["case"]["view"] == "vorn"])
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
