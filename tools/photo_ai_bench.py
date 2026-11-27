#!/usr/bin/env python3
"""Welche Bild-KI eignet sich, um aus einem kleinen Videoausschnitt eines Spielers eine scharfe Ansicht (hinten, vorn, Seite) zu machen?

Dieselben Ausschnitte und derselbe Text gehen an viele Modelle über OpenRouter. Danach urteilt ein Sprachmodell mit Bildverständnis (Nummer und
Schrift richtig? richtige Ansicht? ganzer Körper? Trikotfarben? Gesicht und Haare wie im Ausschnitt? Artefakte?), und ein Bericht (HTML) legt alle
Ergebnisse nebeneinander. Im Bericht kann man selbst Sterne vergeben (Browser-Speicher); die Rangliste rechnet aus Urteil, Sternen und Kosten.

Ablauf (Schlüssel OPENROUTER_API_KEY aus der Umgebung oder aus der Datei .env im Projektordner, die nicht eingecheckt wird; nie im Chat):
    python tools/photo_ai_bench.py modelle                       # Bildmodelle mit Bildeingabe auflisten (ohne Schlüssel)
    python tools/photo_ai_bench.py vorbereiten ORDNER --kandidaten DIR --faelle own-6:hinten,opponent-7:vorn [--eigene BILD:SPIELER:ANSICHT[:REFERENZ]]
    python tools/photo_ai_bench.py lauf ORDNER --modelle a/b,c/d [--probe]   # --probe: nur Prompts und Größen, kein Aufruf
    python tools/photo_ai_bench.py urteil ORDNER [--richter MODELL]
    python tools/photo_ai_bench.py kosten ORDNER                 # Kosten je Modell, je Fall und gesamt (auch aus kosten.jsonl)
    python tools/photo_ai_bench.py bericht ORDNER                # ORDNER/bericht.html

ORDNER enthält teams.json (je Mannschaft: shirt, shorts, socks, backText, extra, optional front = Beschreibung der Trikotvorderseite), cases.json, Eingaben, Ergebnisse, results.json, judge.json.
"""
import argparse
import base64
import html
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import cv2
import numpy as np

API = "https://openrouter.ai/api/v1"
DEFAULT_MODELS = [
    "google/gemini-nano-banana-2.1",        # Nano Banana
    "openai/gpt-image-2.5-sunburst",        # GPT Image 2.5 (zwei Varianten bei OpenRouter)
    "openai/gpt-image-2.5-flare",
    "meta/muse-image",                      # Meta Muse
    "black-forest-labs/flux-3-image",       # FLUX 3
    "x-ai/grok-imagine-image-2.0",          # Grok Imagine 2.0
]
MAX_COST_USD = 5.0                          # Lauf bricht ab, wenn die Kosten dieses Laufs diese Grenze überschreiten (--max-kosten)
JUDGE = "anthropic/claude-sonnet-5.5"
INPUT_HEIGHT = 768   # Ausschnitte werden für alle Modelle gleich auf diese Höhe vergrößert (Lanczos), damit kleine Bilder nicht abgelehnt werden
POSE_EN = {"hinten": "stands perfectly upright and square to the camera, facing directly away from it: exact back view, shoulders, hips and head all squared to the camera and not turned, weight evenly on both feet, like a standardised reference photo.",
           "vorn": "stands perfectly upright and square to the camera, facing directly toward it: exact front view, shoulders, hips and head squared to the camera and not turned, weight evenly on both feet, like a standardised reference photo.",
           "links": "stands perfectly upright in an exact side view, his left side toward the camera, facing toward the left edge of the image, head and body in the same plane, like a standardised reference photo.",
           "rechts": "stands perfectly upright in an exact side view, his right side toward the camera, facing toward the right edge of the image, head and body in the same plane, like a standardised reference photo."}
VIEW_EN = {"hinten": "from directly behind (back view)", "vorn": "from directly in front (front view, face visible)",
           "links": "from his left side (left profile)", "rechts": "from his right side (right profile)"}


class ApiError(Exception):
    """HTTP-Fehler einer Anfrage mit gelesenem Antworttext."""

    def __init__(self, code, body):
        super().__init__(f"HTTP {code}: {body[:400]}")
        self.code, self.body = code, body


def load_env():
    """KEY=WERT-Zeilen aus .env im Projektordner in die Umgebung übernehmen (schon gesetzte Werte bleiben); der Schlüssel wird nie ausgegeben."""
    path = Path(__file__).resolve().parent.parent / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip().removeprefix("export "), v.strip().strip("'\""))


def request(path, payload=None, timeout=300):
    load_env()
    key = os.environ.get("OPENROUTER_API_KEY")
    headers = {"Content-Type": "application/json", "X-Title": "MatchSpace Bild-KI-Test"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(API + path, data=None if payload is None else json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def cost_of(usage, pricing):
    """(Kosten in USD, Quelle). OpenRouter nennt die Kosten in usage.cost; fehlen sie, aus Token-Zahlen und Preisliste schätzen."""
    usage = usage or {}
    if usage.get("cost") is not None:
        return float(usage["cost"]), "openrouter"
    try:
        est = (usage.get("prompt_tokens") or 0) * float(pricing.get("prompt") or 0) + (usage.get("completion_tokens") or 0) * float(pricing.get("completion") or 0)
        return est, "geschätzt"
    except (TypeError, ValueError):
        return 0.0, "unbekannt"


def ledger(folder, **entry):
    """Jeden bezahlten Aufruf in kosten.jsonl festhalten (bleibt über Läufe und neu gestartete Berichte erhalten)."""
    entry["time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(Path(folder) / "kosten.jsonl", "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def data_url(path, height=None):
    img = cv2.imread(str(path))
    if height and img.shape[0] != height:
        img = cv2.resize(img, (round(img.shape[1] * height / img.shape[0]), height), interpolation=cv2.INTER_LANCZOS4)
    ok, buf = cv2.imencode(".png", img)
    return "data:image/png;base64," + base64.b64encode(buf).decode()


def image_models():
    out = []
    for m in request("/models?output_modalities=image")["data"]:
        a = m.get("architecture", {})
        if "image" in (a.get("input_modalities") or []):
            out.append(m)
    return out


def prompt_for(case, team, crop=True):
    """Prompt (Englisch, Bildmodelle verstehen ihn am besten) aus den Fakten des Falls. crop=False: kein Videoausschnitt dieser Ansicht, die Eingabebilder sind fertige Ansichten desselben Spielers."""
    lines = []
    shot = (f"Create a sharp, photorealistic, full-body photograph of exactly this player, seen {VIEW_EN[case['view']]}, "
            f"standing upright and relaxed, arms hanging down at the sides, feet shoulder-width apart, on short-mown grass, "
            f"neutral overcast daylight, portrait orientation 3:4, the whole body from head to boots fully inside the frame, no other people.")
    if crop:
        lines.append("The input is a small, blurry, low-resolution crop from a sports-camera video of one youth football player. " + shot)
        lines.append("Take only the identity and the kit from the crop: hair colour and hairstyle, skin tone, build, kit. Ignore the pose, the motion, the head and body turn and the camera angle of the crop; "
                     "he may be running or turned there, but in the result he " + POSE_EN[case["view"]] + " Do not invent a different person.")
    else:
        lines.append("The input images are finished photographs of one youth football player seen from other sides. " + shot)
        lines.append("Keep exactly his identity and kit from the input images: hair colour and hairstyle, hair length, skin tone, build, kit. In the result he " + POSE_EN[case["view"]] + " Do not invent a different person.")
    kit = f"Kit: {team['shirt']} short-sleeved shirt"
    if team.get("extra"):
        kit += f" ({team['extra']})"
    kit += f", {team['shorts']} shorts, {team['socks']} socks."
    lines.append(kit)
    if case["view"] == "hinten":
        text = "; ".join(team.get("backText") or [])
        if case["number"] == "?" and not text:
            lines.append("The back of the shirt is completely plain: no number, no name, no text, no logo, no print of any kind. Do not add any lettering or digits, even if you think the shirt should have some.")
        else:
            number = f"the player number \"{case['number']}\" in large block digits" if case["number"] != "?" else "no player number (the back has no digits at all)"
            lines.append(f"The back of the shirt carries this print and nothing else: {number}" +
                         (f", and above it, in a smaller size, the text \"{text}\" in white letters, spelled and capitalised exactly as written (keep upper and lower case)" if text else "") + ". Render every character exactly as given, legible and straight; do not add other logos, names or text.")
    elif case["view"] == "vorn":
        if crop:
            lines.append("Show the face clearly and sharply with the same features as in the crop; no sunglasses, no cap.")
        else:
            lines.append("His face is not visible in the input images: give him a natural, plausible face that fits his skin tone, hair and age; show it clearly and sharply; no sunglasses, no cap.")
        front = team.get("front") or "completely plain: no player number, no text, no sponsor, no logo; at most a tiny club crest on the left chest"
        lines.append(f"The front of the shirt is {front}. Do not print any number or lettering on the front unless stated here.")
    else:
        lines.append("Show a clean profile of head, hair and body.")
    lines.append("Output only the image.")
    return "\n".join(lines)


def generate_image(model_info, prompt, url, extra_urls=(), aspect="3:4"):
    """Ein Bild von einem OpenRouter-Modell holen: (PNG-Bytes, Antwort mit usage). Modelle mit Textausgabe über chat/completions, reine Bildmodelle über /images.
    Wirft ApiError (HTTP-Fehler mit Antworttext) oder RuntimeError (Antwort ohne Bild)."""
    model = model_info["id"]
    outputs = model_info["architecture"].get("output_modalities") or ["image"]
    payload = {"model": model, "modalities": ["image", "text"] if "text" in outputs else ["image"], "usage": {"include": True},
               "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}] + [{"type": "image_url", "image_url": {"url": u}} for u in (url, *extra_urls)]}]}
    if model.startswith("google/"):
        payload["image_config"] = {"aspect_ratio": aspect}
    try:
        resp = request("/chat/completions", payload)
        msg = resp["choices"][0]["message"]
        imgs = msg.get("images") or [p for p in (msg.get("content") or []) if isinstance(p, dict) and p.get("type") in ("image_url", "output_image")]
        if not imgs:
            raise RuntimeError("keine Bilddaten in der Antwort: " + json.dumps(msg)[:200])
        u = imgs[0]["image_url"]["url"] if "image_url" in imgs[0] else imgs[0]["url"]
        return (base64.b64decode(u.split(",", 1)[1]) if u.startswith("data:") else urllib.request.urlopen(u, timeout=120).read()), resp
    except urllib.error.HTTPError as err:
        body = err.read().decode()
        if err.code != 404 or "/api/v1/images" not in body:
            raise ApiError(err.code, body)
    # reine Bildmodelle: eigener Endpunkt (POST /api/v1/images) mit Referenzbild in input_references
    try:
        resp = request("/images", {"model": model, "prompt": prompt, "aspect_ratio": aspect, "response_format": "b64_json",
                                   "input_references": [{"type": "image_url", "image_url": {"url": u}} for u in (url, *extra_urls)]})
    except urllib.error.HTTPError as err:
        raise ApiError(err.code, err.read().decode())
    item = resp["data"][0]
    return (base64.b64decode(item["b64_json"]) if item.get("b64_json") else urllib.request.urlopen(item["url"], timeout=120).read()), resp


def cmd_modelle(a):
    for m in sorted(image_models(), key=lambda m: m["id"]):
        p = m.get("pricing", {})
        print(f"{m['id']:48s} Bild-Ausgabe {p.get('image') or '-':>8}  Token-Ausgabe {p.get('completion') or '-'}")


def cmd_vorbereiten(a):
    folder = Path(a.ordner)
    (folder / "eingabe").mkdir(parents=True, exist_ok=True)
    teams_path = folder / "teams.json"
    if not teams_path.exists():
        teams_path.write_text(json.dumps({
            "opponent": {"shirt": "green", "shorts": "white", "socks": "white", "backText": ["SV Musterstadt"], "extra": "black long undershirt sleeves", "test": True},
            "own": {"shirt": "red", "shorts": "red", "socks": "red", "backText": ["FC Beispiel"], "extra": "black long undershirt sleeves", "test": True}}, indent=1))
        print(f"-> {teams_path} (Platzhalter, bitte prüfen; Texte mit test=true sind erfunden und dienen nur dem Schriftvergleich)")
    index = json.loads((Path(a.kandidaten) / "index.json").read_text()) if a.kandidaten else {}
    cases = []
    for item in [x for x in (a.faelle or "").split(",") if x]:
        player, view = item.split(":")
        src = Path(a.kandidaten) / player / f"{view}.png"
        team = index[player]["team"]
        number = "".join(c for c in player.split("-")[-1] if c.isdigit())
        cases.append({"id": f"{player}-{view}", "player": player, "team": team, "view": view, "number": number if len(number) <= 2 else "?", "input": str(src)})
    for item in a.eigene or []:
        parts = item.split(":")
        src, player, view = parts[:3]
        team = player.split("-")[0]
        number = player.split("-")[-1]
        cases.append({"id": f"{player}-{view}-eigen", "player": player, "team": team, "view": view, "number": number, "input": src, "reference": parts[3] if len(parts) > 3 else None})
    for c in cases:
        dst = folder / "eingabe" / f"{c['id']}.png"
        cv2.imwrite(str(dst), cv2.imread(c["input"]))
        c["input"] = f"eingabe/{c['id']}.png"
        if c.get("reference"):
            ref = folder / "eingabe" / f"{c['id']}-referenz.png"
            cv2.imwrite(str(ref), cv2.imread(c["reference"]))
            c["reference"] = f"eingabe/{c['id']}-referenz.png"
    (folder / "cases.json").write_text(json.dumps(cases, indent=1, ensure_ascii=False))
    print(f"-> {len(cases)} Fälle in {folder / 'cases.json'}")


def cmd_lauf(a):
    folder = Path(a.ordner)
    cases = json.loads((folder / "cases.json").read_text())
    if a.faelle:
        cases = [c for c in cases if c["id"] in a.faelle.split(",")]
    teams = json.loads((folder / "teams.json").read_text())
    models = a.modelle.split(",") if a.modelle else DEFAULT_MODELS
    known = {m["id"]: m for m in image_models()}
    missing = [m for m in models if m not in known]
    if missing:
        sys.exit(f"Unbekannt bei OpenRouter (python tools/photo_ai_bench.py modelle): {missing}")
    results_path = folder / "results.json"
    results = json.loads(results_path.read_text()) if results_path.exists() else {}
    spent = 0.0
    for case in cases:
        prompt = prompt_for(case, teams[case["team"]])
        (folder / f"{case['id']}.prompt.txt").write_text(prompt)
        url = data_url(folder / case["input"], INPUT_HEIGHT)
        for model in models:
            key = f"{case['id']}|{model}"
            out = folder / "ergebnis" / case["id"] / (model.replace("/", "__") + ".png")
            if key in results and results[key].get("ok") and out.exists():
                continue
            if a.probe:
                print(f"[Probe] {key}: Aufruf an {model}")
                continue
            if spent >= a.max_kosten:
                print(f"Kostengrenze erreicht ({spent:.2f} von {a.max_kosten:.2f} USD), Lauf angehalten. Mit --max-kosten erhöhen und erneut starten.")
                return
            began = time.time()
            entry = {"ok": False}
            for attempt in range(3):
                try:
                    raw, resp = generate_image(known[model], prompt, url)
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(raw)
                    cost, source = cost_of(resp.get("usage"), known[model].get("pricing"))
                    entry = {"ok": True, "seconds": round(time.time() - began, 1), "cost": cost, "cost_source": source, "usage": resp.get("usage"), "file": str(out.relative_to(folder))}
                    spent += cost
                    ledger(folder, kind="bild", case=case["id"], model=model, cost=cost, source=source, seconds=entry["seconds"])
                    break
                except ApiError as err:
                    entry = {"ok": False, "error": str(err)}
                    if err.code in (400, 401, 402, 403, 404):
                        break
                    time.sleep(5)
                except Exception as err:   # noqa: BLE001
                    entry = {"ok": False, "error": str(err)[:300]}
                    time.sleep(5)
            results[key] = entry
            results_path.write_text(json.dumps(results, indent=1, ensure_ascii=False))
            print(f"{key}: {'ok ' + str(entry['seconds']) + ' s, Kosten $' + format(entry['cost'], '.4f') + ' (' + entry['cost_source'] + '), Summe dieses Laufs $' + format(spent, '.3f') if entry['ok'] else entry['error'][:120]}", flush=True)


JUDGE_PROMPT = """You judge an AI-generated image against the task and facts below. Image 1 is the small crop that was given to the AI. Image 2 is the AI result.
Task: a sharp, photorealistic full-body photo of the SAME youth football player in image 1, seen {view}, standing upright, arms down.
Facts: shirt {shirt}, shorts {shorts}, socks {socks}. Player number {number}. Required shirt-back print: text "{text}" above the number (only if view is from behind).
Answer with JSON only, no other text, with these keys:
 "view_correct": true/false (is the player seen from the requested side?),
 "full_body": true/false (head to boots inside the frame),
 "number_read": string (the number you can read on the shirt back, "" if not visible),
 "text_read": string (the text above the number, "" if none),
 "number_correct": true/false, "text_correct": true/false (exact spelling),
 "kit_colours_ok": 1-5 (shirt, shorts, socks match the facts),
 "identity": 1-5 (hair, skin tone, build look like the person in image 1),
 "photoreal": 1-5 (looks like a real photograph, no plastic skin or distortions),
 "artifacts": 1-5 (5 = none: no extra limbs, melted hands, garbled logos, extra people),
 "note": short German sentence on the main flaw."""


def cmd_urteil(a):
    folder = Path(a.ordner)
    cases = {c["id"]: c for c in json.loads((folder / "cases.json").read_text())}
    teams = json.loads((folder / "teams.json").read_text())
    results = json.loads((folder / "results.json").read_text())
    judge_path = folder / "judge.json"
    judged = json.loads(judge_path.read_text()) if judge_path.exists() else {}
    for key, res in results.items():
        if not res.get("ok") or (key in judged and "error" not in judged[key]):
            continue
        case_id, model = key.split("|")
        case = cases[case_id]
        team = teams[case["team"]]
        prompt = JUDGE_PROMPT.format(view=VIEW_EN[case["view"]], shirt=team["shirt"], shorts=team["shorts"], socks=team["socks"], number=case["number"], text="; ".join(team.get("backText") or []))
        payload = {"model": a.richter, "usage": {"include": True}, "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": data_url(folder / case["input"], INPUT_HEIGHT)}},
            {"type": "image_url", "image_url": {"url": data_url(folder / res["file"])}}]}]}
        try:
            resp = request("/chat/completions", payload)
            text = resp["choices"][0]["message"]["content"]
            judged[key] = json.loads(text[text.index("{"):text.rindex("}") + 1])
            jc, source = cost_of(resp.get("usage"), {})
            judged[key]["_cost"] = jc
            ledger(folder, kind="urteil", case=case_id, model=a.richter, bewertet=model, cost=jc, source=source)
        except Exception as err:   # noqa: BLE001
            judged[key] = {"error": str(err)[:200]}
        judge_path.write_text(json.dumps(judged, indent=1, ensure_ascii=False))
        print(key, judged[key].get("note", judged[key].get("error")), flush=True)


REPORT = """<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bild-KI-Vergleich</title><style>
:root{color-scheme:dark;--bg:#14181c;--fg:#e8eaed;--mu:#9aa3ad;--ln:#2b323a}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.4 system-ui,sans-serif;padding:16px}
h1,h2{margin:.2em 0}table{border-collapse:collapse}td,th{border:1px solid var(--ln);padding:4px 8px;text-align:left;vertical-align:top}th{color:var(--mu);font-weight:500}
.grid{display:flex;gap:10px;overflow-x:auto;padding-bottom:10px}.cell{flex:0 0 230px;border:1px solid var(--ln);border-radius:6px;padding:6px;background:#1a2026}.cell img{width:100%;border-radius:4px;background:#000}
.cell small{display:block;color:var(--mu)}.stars button{background:none;border:0;color:#556;font-size:18px;cursor:pointer;padding:0 1px}.stars button.on{color:#f2c200}
.ok{color:#6fcf97}.no{color:#eb5757}.w{display:inline-flex;gap:6px;align-items:center;margin-right:14px;color:var(--mu)}input[type=range]{width:90px}.scroll{overflow-x:auto}
</style></head><body><h1>Bild-KI-Vergleich</h1>
<p style="color:var(--mu)">Gewichte einstellen, Sterne in den Bildern vergeben (werden im Browser gespeichert). Rangliste = gewichtetes Mittel aus Urteil des Sprachmodells und deinen Sternen.</p>
<div id="weights"></div><h2>Rangliste</h2><div class="scroll"><table id="rank"></table></div><div id="cases"></div>
<script>
const DATA = __DATA__;
const W = {zahl:3, text:2, ansicht:1, koerper:1, farben:1.5, identitaet:2.5, foto:1.5, artefakte:1.5, sterne:4};
const labels = {zahl:'Nummer richtig', text:'Schrift richtig', ansicht:'Ansicht richtig', koerper:'ganzer Körper', farben:'Trikotfarben', identitaet:'Aussehen wie Vorlage', foto:'Fotorealismus', artefakte:'ohne Fehler', sterne:'meine Sterne'};
const saved = JSON.parse(localStorage.getItem('ki-bench-weights')||'{}'); Object.assign(W, saved);
const stars = JSON.parse(localStorage.getItem('ki-bench-stars-'+DATA.id)||'{}');
function score(j, key){ if(!j||j.error) return null; const b=x=>x?1:0, n=x=>(x-1)/4;
  const parts={zahl:b(j.number_correct),text:b(j.text_correct),ansicht:b(j.view_correct),koerper:b(j.full_body),farben:n(j.kit_colours_ok),identitaet:n(j.identity),foto:n(j.photoreal),artefakte:n(j.artifacts)};
  const st = stars[key]; if(st) parts.sterne=(st-1)/4; return parts; }
function rank(){ const rows={}; for(const [key,res] of Object.entries(DATA.results)){ const [c,m]=key.split('|'); const p=score(DATA.judge[key],key); (rows[m]??={n:0,sum:0,cost:0,sec:0,ok:0,fail:0,sumw:0}); const r=rows[m];
    if(!res.ok){r.fail++;continue} r.ok++; r.cost+=res.cost||0; r.sec+=res.seconds||0; if(!p) continue; let s=0,sw=0; for(const k in W){ if(p[k]!==undefined){s+=W[k]*p[k];sw+=W[k]} } if(sw){r.sum+=s/sw;r.n++} }
  const list=Object.entries(rows).map(([m,r])=>({m,score:r.n?r.sum/r.n:0,n:r.n,cost:r.ok?r.cost/r.ok:0,sec:r.ok?r.sec/r.ok:0,okn:r.ok,fail:r.fail})).sort((a,b)=>b.score-a.score);
  document.getElementById('rank').innerHTML='<tr><th>#</th><th>Modell</th><th>Punkte (0–100)</th><th>Bilder</th><th>Kosten/Bild</th><th>Kosten gesamt</th><th>Sekunden</th><th>Fehlgeschlagen</th></tr>'+list.map((r,i)=>`<tr><td>${i+1}</td><td>${r.m}</td><td>${(r.score*100).toFixed(0)}</td><td>${r.n}</td><td>${r.cost?'$'+r.cost.toFixed(4):'–'}</td><td>${r.cost?'$'+(r.cost*r.okn).toFixed(3):'–'}</td><td>${r.sec.toFixed(0)}</td><td>${r.fail}</td></tr>`).join(''); }
function weights(){ const el=document.getElementById('weights'); el.innerHTML=Object.keys(W).map(k=>`<span class="w">${labels[k]} <input type="range" min="0" max="5" step="0.5" value="${W[k]}" data-k="${k}"> <b>${W[k]}</b></span>`).join('');
  el.querySelectorAll('input').forEach(i=>i.oninput=()=>{W[i.dataset.k]=Number(i.value);localStorage.setItem('ki-bench-weights',JSON.stringify(W));weights();rank();sync()}); }
function cases(){ const out=[]; for(const c of DATA.cases){ let h=`<h2>${c.id}</h2><div class="grid"><div class="cell"><img src="${c.input}"><small>Eingabe (Video-Ausschnitt)</small></div>`;
    if(c.reference) h+=`<div class="cell"><img src="${c.reference}"><small>Referenz (von Hand)</small></div>`;
    for(const m of DATA.models){ const key=c.id+'|'+m, res=DATA.results[key], j=DATA.judge[key]; if(!res){continue}
      if(!res.ok){h+=`<div class="cell"><small>${m}</small><small class="no">${(res.error||'').slice(0,160)}</small></div>`;continue}
      const t=(v,l)=>v===undefined?'':`<span class="${v?'ok':'no'}">${l}${v?' ✓':' ✗'}</span> `;
      const st=[1,2,3,4,5].map(n=>`<button data-k="${key}" data-n="${n}" class="${(stars[key]||0)>=n?'on':''}">★</button>`).join('');
      h+=`<div class="cell"><img src="${res.file}" loading="lazy"><small><b>${m}</b> · ${res.seconds}s ${res.cost?'· $'+res.cost.toFixed(3):''}</small>`+(j&&!j.error?`<small>${t(j.number_correct,'Nr')}${t(j.text_correct,'Text')}${t(j.view_correct,'Ansicht')}${t(j.full_body,'Körper')}</small><small>Farben ${j.kit_colours_ok} · Person ${j.identity} · Foto ${j.photoreal} · Fehler ${j.artifacts}</small><small>${j.note||''}</small>`:'')+`<div class="stars">${st}</div></div>`; }
    out.push(h+'</div>'); }
  const el=document.getElementById('cases'); el.innerHTML=out.join('');
  el.querySelectorAll('.stars button').forEach(b=>b.onclick=()=>{const k=b.dataset.k,n=Number(b.dataset.n); stars[k]=(stars[k]===n?0:n); localStorage.setItem('ki-bench-stars-'+DATA.id,JSON.stringify(stars)); cases(); rank(); sync()}); }
function sync(){ fetch('/sterne',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({stars,weights:W})}).catch(()=>{}); }
weights(); rank(); cases(); sync();
</script></body></html>"""


def cmd_kosten(a):
    folder = Path(a.ordner)
    path = folder / "kosten.jsonl"
    if not path.exists():
        sys.exit("Noch keine Kosten erfasst (kosten.jsonl fehlt).")
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    by_model, by_case, judge_total = {}, {}, 0.0
    for r in rows:
        if r["kind"] == "urteil":
            judge_total += r["cost"]
            continue
        m = by_model.setdefault(r["model"], {"n": 0, "cost": 0.0, "sec": 0.0, "est": 0})
        m["n"] += 1
        m["cost"] += r["cost"]
        m["sec"] += r.get("seconds") or 0
        m["est"] += r["source"] != "openrouter"
        by_case[r["case"]] = by_case.get(r["case"], 0.0) + r["cost"]
    print(f"{'Modell':44s} {'Bilder':>6s} {'Summe USD':>10s} {'je Bild':>9s} {'Sek./Bild':>9s}")
    for model, m in sorted(by_model.items(), key=lambda kv: kv[1]["cost"] / max(kv[1]["n"], 1)):
        print(f"{model:44s} {m['n']:6d} {m['cost']:10.4f} {m['cost'] / m['n']:9.4f} {m['sec'] / m['n']:9.1f}" + ("  (teils geschätzt)" if m["est"] else ""))
    images = sum(m["cost"] for m in by_model.values())
    print(f"\nBilder gesamt ${images:.4f}, Urteile ${judge_total:.4f}, Summe ${images + judge_total:.4f}")


def cmd_bericht(a):
    folder = Path(a.ordner)
    cases = json.loads((folder / "cases.json").read_text())
    results = json.loads((folder / "results.json").read_text()) if (folder / "results.json").exists() else {}
    judge = json.loads((folder / "judge.json").read_text()) if (folder / "judge.json").exists() else {}
    models = sorted({k.split("|")[1] for k in results})
    data = {"id": folder.name, "cases": cases, "results": results, "judge": judge, "models": models}
    (folder / "bericht.html").write_text(REPORT.replace("__DATA__", json.dumps(data, ensure_ascii=False)))
    print(f"-> {folder / 'bericht.html'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("modelle")
    p = sub.add_parser("vorbereiten")
    p.add_argument("ordner")
    p.add_argument("--kandidaten")
    p.add_argument("--faelle")
    p.add_argument("--eigene", action="append")
    p = sub.add_parser("lauf")
    p.add_argument("ordner")
    p.add_argument("--modelle")
    p.add_argument("--faelle", help="nur diese Fälle (Komma-getrennte IDs aus cases.json)")
    p.add_argument("--probe", action="store_true")
    p.add_argument("--max-kosten", type=float, default=MAX_COST_USD, dest="max_kosten", help="Abbruch, wenn die Kosten dieses Laufs diese Summe (USD) erreichen")
    p = sub.add_parser("urteil")
    p.add_argument("ordner")
    p.add_argument("--richter", default=JUDGE)
    p = sub.add_parser("kosten")
    p.add_argument("ordner")
    p = sub.add_parser("bericht")
    p.add_argument("ordner")
    a = ap.parse_args()
    {"modelle": cmd_modelle, "vorbereiten": cmd_vorbereiten, "lauf": cmd_lauf, "urteil": cmd_urteil, "kosten": cmd_kosten, "bericht": cmd_bericht}[a.cmd](a)
