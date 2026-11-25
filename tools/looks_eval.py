#!/usr/bin/env python3
"""Wie scharf und wie richtig ist die Videotextur? Messung mit zurückgehaltenen Bildern, und Versuche, sie besser zu machen.

Die Textur eines Spielers (tools/veo_looks.py) wird aus den Bildern einer Szene gemittelt. Ob eine Änderung sie wirklich besser macht,
zeigt nur der Vergleich mit Bildern, die nicht in die Textur eingegangen sind: Die Szene wird in Sekundenblöcke geteilt, jeder fünfte Block
ist Prüfmaterial. Die Textur wird aus den übrigen gebaut und danach an den Prüfbildern gemessen: mittlere Farbabweichung zwischen Textur
und dem, was das Video an derselben Stelle zeigt. Eine erfundene Schärfe (Schmierstreifen, falsches Detail) steigt dort in der Abweichung,
echtes Detail senkt sie. "Ausgerichtet" heißt: vor dem Vergleich wird jedes Körperteil des Prüfbilds um bis zu wenige Pixel auf die
Textur geschoben (dadurch zählt nur der Inhalt der Textur, nicht der Fehler der Haltung im einzelnen Bild).

Aufruf (Bilder und Geometrie einmal einsammeln, dauert wie veo_looks.py einen Durchgang):
    .venv/bin/python tools/looks_eval.py sammeln SZENENVIDEO DETEKTIONEN.json KAMERA.json HINTERGRUND.png SZENENORDNER AUSGABE.pkl SPIELER...
und messen (rechnet nur noch aus der gesammelten Datei):
    .venv/bin/python tools/looks_eval.py messen AUSGABE.pkl [BILDORDNER] [--masken]
(--masken: zusätzlich Personenmasken mit models/yolo11x-seg.pt rechnen und die Variante "mit Personenmaske" messen)
"""
import pickle
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import veo_looks as vl  # noqa: E402

CROP_PAD = 24                    # Pixel Umgebung um den Spieler im gesammelten Ausschnitt (die Nachbarn müssen im Bild sein, damit die Maske sie trennt)
TEST_BLOCK, TEST_EVERY = 25, 5   # Bilder je Block, jeder wievielte Block ist Prüfmaterial


def is_test(f):
    return (f // TEST_BLOCK) % TEST_EVERY == TEST_EVERY - 1


def collect(video, det_path, camera_path, background_path, scene_dir, out_path, ids):
    """Je Bild und gewähltem Spieler: Ausschnitt des Videobilds, sichtbare Stellen, ihre Bildpunkte darin und Gewichte."""
    began = time.time()
    sc = vl.load_scene(video, det_path, camera_path, background_path, scene_dir)
    ids = set(ids)
    missing = ids - {p["id"] for p in sc["players"]}
    if missing:
        sys.exit(f"Nicht in der Szene (oder ohne Gelenkpunkte im Video): {sorted(missing)}")
    names = {k: p["id"] for k, p in enumerate(sc["players"])}
    data = {i: [] for i in ids}
    H = sc["H"]
    for f, image in vl.frames(sc):
        for o in vl.observe(sc, f, image, only=ids):
            uv = o["uv"]
            x0, y0 = int(max(np.floor(uv[:, 0].min() - CROP_PAD), 0)), int(max(np.floor(uv[:, 1].min() - CROP_PAD), 0))
            x1, y1 = int(np.ceil(uv[:, 0].max() + CROP_PAD + 1)), int(np.ceil(uv[:, 1].max() + CROP_PAD + 1))
            lens = image[o["lens"] * H:(o["lens"] + 1) * H]
            crop = lens[y0:min(y1, H), x0:x1].copy()
            data[names[o["player"]]].append({
                "f": f, "crop": crop, "uv": (uv - (x0, y0)).astype(np.float32), "cell": o["cell"].astype(np.uint16),
                "weight": o["weight"].astype(np.float32), "facing": o["facing"].astype(np.float16), "dist": o["dist"].astype(np.float16)})
        if f % 100 == 0:
            print(f"  Bild {f} [{time.time() - began:.0f} s]", flush=True)
    pickle.dump({"index": sc["index"], "segment": sc["segment"], "segments": [c["name"] for c in sc["cells"]], "data": data},
                open(out_path, "wb"), protocol=4)
    print(f"-> {out_path} ({sum(len(v) for v in data.values())} Ausschnitte), {time.time() - began:.0f} s")


def align(obs, ref, ref_ok, index, segment):
    """Verschiebung (N, 2) eines Ausschnitts auf den Bezug `ref` (je Stelle der Kachel); Rechnung wie in veo_looks.align."""
    cell = obs["cell"].astype(int)
    texel = index[cell]
    return vl.align(obs["crop"], obs["uv"], segment[cell], obs["weight"], ref[texel], ref_ok[texel])


def add_masks(observations, scale=3, batch=16):
    """Personenmaske je Ausschnitt (o["mask"], bool, Größe des Ausschnitts): das Segmentierungsmodell (models/yolo11x-seg.pt) läuft auf dem vergrößerten
    Ausschnitt; gewählt wird die Person, in der die meisten sichtbaren Stellen des Spielers liegen. Ohne Treffer (weniger als 30 % der Stellen) bleibt
    o["mask"] = None. Maske um 1 Pixel verbreitert, weil dünne Arme sonst am Rand wegfallen."""
    from ultralytics import YOLO
    model = YOLO(str(Path(__file__).parent.parent / "models" / "yolo11x-seg.pt"))
    found = 0
    for start in range(0, len(observations), batch):
        group = observations[start:start + batch]
        big = [cv2.resize(o["crop"], None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC) for o in group]
        results = model.predict(big, classes=[0], imgsz=640, conf=0.15, retina_masks=True, verbose=False)
        for o, r in zip(group, results):
            o["mask"] = None
            if r.masks is None or not len(r.masks.data):
                continue
            h, w = o["crop"].shape[:2]
            masks = r.masks.data.cpu().numpy() > 0.5
            ui = np.clip((o["uv"][:, 0] * scale).astype(int), 0, masks.shape[2] - 1)
            vi = np.clip((o["uv"][:, 1] * scale).astype(int), 0, masks.shape[1] - 1)
            score = masks[:, vi, ui].mean(axis=1)
            best = int(score.argmax())
            if score[best] < 0.3:
                continue
            small = cv2.resize(masks[best].astype(np.uint8), (w, h), interpolation=cv2.INTER_AREA) > 0
            o["mask"] = cv2.dilate(small.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
            found += 1
    return found


def quality(observations, ref=None):
    """Güte je Beobachtung und Stelle: frontal gesehen und nah (Pixel je Meter), auf das 95-%-Quantil des Spielers bezogen (höchstens 1)."""
    q = [o["facing"].astype(np.float32) / o["dist"].astype(np.float32) for o in observations]
    ref = ref or float(np.quantile(np.concatenate(q), 0.95))
    return [np.minimum(x / ref, 1.0) for x in q], ref


def build(observations, index, segment, aligned=None, rounds=2, power=0.0, use_mask=False):
    """Textur (Kachel² × 3, Gewicht) aus Ausschnitten wie in veo_looks.main: Mittel mit Gewichten, im zweiten Durchgang ohne Ausreißer.
    `aligned`: Verschiebungen je Ausschnitt (Liste von (N, 2)), sonst keine."""
    size = vl.TILE * vl.TILE
    mean = None
    qs, _ = quality(observations)
    for rnd in range(rounds):
        sums, wq, wsum = np.zeros((size, 3)), np.zeros(size), np.zeros(size)
        for k, o in enumerate(observations):
            uv = o["uv"] + (aligned[k] if aligned is not None else 0)
            colour = vl.sample(o["crop"], uv)
            texel = index[o["cell"].astype(int)]
            w0 = o["weight"].astype(np.float64)
            if use_mask and o.get("mask") is not None:
                mh, mw = o["mask"].shape
                inside = o["mask"][np.clip(np.round(uv[:, 1] - 0.5).astype(int), 0, mh - 1), np.clip(np.round(uv[:, 0] - 0.5).astype(int), 0, mw - 1)]
                w0 = w0 * inside
            if rnd > 0:
                w0 = w0 * (np.linalg.norm(colour - mean[texel], axis=1) < vl.OUTLIER)
            w = w0 * qs[k].astype(np.float64) ** power   # Güte: nahe, frontale Bilder zählen mehr ("power" = Schärfe vor Rauschen)
            for ch in range(3):
                sums[:, ch] += np.bincount(texel, w * colour[:, ch], minlength=size)
            wq += np.bincount(texel, w, minlength=size)
            wsum += np.bincount(texel, w0, minlength=size)   # "gesehen" bleibt unabhängig von der Güte
        mean = sums / np.maximum(wq, 1e-9)[:, None]
    return mean, wsum


def refined(observations, index, segment, steps=3, power=0.0):
    """Textur mit dichter Ausrichtung: erst Mittel ohne Verschiebung, dann in `steps` Runden jeden Ausschnitt auf das bisherige Mittel
    schieben und neu mitteln."""
    tex, wt = build(observations, index, segment, power=power)
    for _ in range(steps):
        sh = [align(o, tex, wt >= vl.ENOUGH, index, segment) for o in observations]
        tex, wt = build(observations, index, segment, aligned=sh, power=power)
    return tex, wt


def error(tex, wt, observations, index, segment, aligned, sharp_test=False):
    """Mittlere absolute Farbabweichung (über Kanäle und Stellen, gewichtet) der Prüfbilder zur Textur, getrennt nach Körperteilgruppe."""
    groups = {"Rumpf": ("torso",), "Kopf": ("head",), "Arme": ("upperarm", "lowerarm"), "Beine": ("thigh", "calf")}
    names = np.array([s.split("_")[0] for s in SEG_NAMES])
    sums = {g: [0.0, 0.0] for g in groups}
    qs, _ = quality(observations)
    for k, o in enumerate(observations):
        cell = o["cell"].astype(int)
        texel = index[cell]
        uv = o["uv"] + (aligned[k] if aligned is not None else 0)
        colour = vl.sample(o["crop"], uv)
        w = o["weight"] * (wt[texel] >= vl.ENOUGH) * (o["facing"].astype(float) > 0.5)
        if sharp_test:
            w = w * qs[k].astype(float) ** 6   # nur die schärfsten Prüfbilder (nah und frontal) zählen
        d = np.abs(colour - tex[texel]).mean(axis=1)
        d = np.minimum(d, vl.OUTLIER)
        for g, parts in groups.items():
            m = np.isin(names[segment[cell]], parts)
            sums[g][0] += float((w * d)[m].sum())
            sums[g][1] += float(w[m].sum())
    return {g: s[0] / max(s[1], 1e-9) for g, s in sums.items()}


def sharpness(tex, wt, segment_name="torso"):
    """Mittlere Steilheit (Farbstufen je Texel) im Rumpf der Kachel, nur gesehene Stellen: wie viel Feinzeichnung die Textur hat."""
    x, y, w, h = next(s[1] for s in vl.SEGMENTS if s[0] == segment_name)
    img = tex.reshape(vl.TILE, vl.TILE, 3)[y:y + h, x:x + w]
    ok = (wt.reshape(vl.TILE, vl.TILE)[y:y + h, x:x + w] >= vl.ENOUGH)
    gx, gy = np.abs(np.diff(img, axis=1))[:-1], np.abs(np.diff(img, axis=0))[:, :-1]
    m = ok[:-1, :-1] & ok[1:, :-1] & ok[:-1, 1:]
    return float(((gx + gy).mean(axis=-1))[m].mean()) if m.any() else float("nan")


SEG_NAMES = [s[0] for s in vl.SEGMENTS]


def measure(pkl_path, image_dir=None, masken=False):
    pack = pickle.load(open(pkl_path, "rb"))
    index, segment = pack["index"], pack["segment"]
    if masken:
        for pid, obs in pack["data"].items():
            print(f"Masken {pid}: {add_masks(obs)} von {len(obs)}", flush=True)
    variants = {"Mittel (bisher)": lambda tr: build(tr, index, segment),
                "mit Personenmaske": lambda tr: build(tr, index, segment, use_mask=True),
                "Güte hoch 2": lambda tr: build(tr, index, segment, power=2),
                "Güte hoch 4": lambda tr: build(tr, index, segment, power=4),
                "Güte hoch 8": lambda tr: build(tr, index, segment, power=8),
                "ausgerichtet + Güte hoch 4": lambda tr: refined(tr, index, segment, 3, power=4)}
    rows = {v: [] for v in variants}
    for pid, obs in pack["data"].items():
        train = [o for o in obs if not is_test(o["f"])]
        test = [o for o in obs if is_test(o["f"])]
        if len(train) < 20 or len(test) < 5:
            print(pid, "zu wenig Bilder")
            continue
        print(f"{pid}: {len(train)} Bilder zum Bauen, {len(test)} zum Prüfen", flush=True)
        textures = {}
        for name, fn in variants.items():
            began = time.time()
            tex, wt = fn(train)
            textures[name] = (tex, wt)
            sh = [align(o, tex, wt >= vl.ENOUGH, index, segment) for o in test]
            nominal = error(tex, wt, test, index, segment, sh)                       # alle Prüfbilder
            lined = error(tex, wt, test, index, segment, sh, sharp_test=True)         # nur die schärfsten
            sharp = sharpness(tex, wt)
            rows[name].append((nominal, lined, sharp))
            print(f"  {name:34s} Schärfe {sharp:5.1f} | alle Prüfbilder " + " ".join(f"{g} {v:5.2f}" for g, v in nominal.items()) +
                  " | scharfe Prüfbilder " + " ".join(f"{g} {v:5.2f}" for g, v in lined.items()) + f"  [{time.time() - began:.0f} s]", flush=True)
        if image_dir:
            Path(image_dir).mkdir(parents=True, exist_ok=True)
            seg_rect = [s[1] for s in vl.SEGMENTS if s[0] in ("torso", "head")]
            strips = []
            for name, (tex, wt) in textures.items():
                img = np.clip(tex.reshape(vl.TILE, vl.TILE, 3), 0, 255).astype(np.uint8)
                strips.append(cv2.resize(img[0:64, 0:96], None, fx=6, fy=6, interpolation=cv2.INTER_NEAREST))
            cv2.imwrite(str(Path(image_dir) / f"{pid}.png"), np.hstack(strips))
    print("\nMittel über alle Spieler (Abweichung in Farbstufen, kleiner ist besser):")
    for name, vals in rows.items():
        if not vals:
            continue
        nom = {g: np.mean([v[0][g] for v in vals]) for g in vals[0][0]}
        lin = {g: np.mean([v[1][g] for v in vals]) for g in vals[0][1]}
        print(f"  {name:34s} Schärfe {np.mean([v[2] for v in vals]):5.1f} | alle Prüfbilder " + " ".join(f"{g} {v:5.2f}" for g, v in nom.items()) +
              " | scharfe Prüfbilder " + " ".join(f"{g} {v:5.2f}" for g, v in lin.items()))


if __name__ == "__main__":
    args = [a for a in sys.argv if a != "--masken"]
    if len(args) >= 9 and args[1] == "sammeln":
        collect(*args[2:8], args[8:])
    elif len(args) in (3, 4) and args[1] == "messen":
        measure(*args[2:], masken="--masken" in sys.argv)
    else:
        sys.exit(__doc__)
