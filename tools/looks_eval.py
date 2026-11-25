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
    .venv/bin/python tools/looks_eval.py messen AUSGABE.pkl [BILDORDNER]
"""
import pickle
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import veo_looks as vl  # noqa: E402

TEST_BLOCK, TEST_EVERY = 25, 5   # Bilder je Block, jeder wievielte Block ist Prüfmaterial
MAX_ALIGN = 2.5                  # Pixel: so weit darf ein Körperteil im Bild auf die Textur geschoben werden
MIN_ALIGN_TEXELS = 24            # weniger sichtbare Stellen: kein Schieben
RIDGE = 0.02                     # Gewicht der Bremse gegen große Verschiebungen (Anteil der Spur)


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
            x0, y0 = int(max(np.floor(uv[:, 0].min() - 4), 0)), int(max(np.floor(uv[:, 1].min() - 4), 0))
            x1, y1 = int(np.ceil(uv[:, 0].max() + 5)), int(np.ceil(uv[:, 1].max() + 5))
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


def gradient(crop, uv):
    """Farbe (N, 3) und ihre Ableitung nach x und y (N, 3) an Bildpunkten uv eines Ausschnitts."""
    c = vl.sample(crop, uv)
    gx = (vl.sample(crop, uv + (0.5, 0)) - vl.sample(crop, uv - (0.5, 0)))
    gy = (vl.sample(crop, uv + (0, 0.5)) - vl.sample(crop, uv - (0, 0.5)))
    return c, gx, gy


def solve_shift(res, gx, gy, w, ridge, prior=None):
    """Verschiebung d (2,), die sum w * |res + d_x gx + d_y gy|² klein macht (res = Farbe - Bezug); Bremse zieht zu `prior`."""
    prior = np.zeros(2) if prior is None else prior
    a = np.array([[np.sum(w[:, None] * gx * gx), np.sum(w[:, None] * gx * gy)], [np.sum(w[:, None] * gx * gy), np.sum(w[:, None] * gy * gy)]])
    b = -np.array([np.sum(w[:, None] * gx * res), np.sum(w[:, None] * gy * res)])
    lam = ridge * np.trace(a) + 1e-6
    d = np.linalg.solve(a + lam * np.eye(2), b + lam * prior)
    return np.clip(d, -MAX_ALIGN, MAX_ALIGN)


def align(obs, ref, ref_ok, index, segment, passes=2, ridge=RIDGE, whole=True):
    """Verschiebung (Körper gesamt, dann je Körperteil darüber hinaus) eines Ausschnitts auf den Bezug `ref` (je Stelle der Kachel).
    Gibt die Verschiebung je sichtbarer Stelle (N, 2) zurück."""
    cell = obs["cell"].astype(int)
    texel = index[cell]
    ok = ref_ok[texel]
    shift = np.zeros((len(cell), 2))
    wt = obs["weight"] * ok
    if ok.sum() < MIN_ALIGN_TEXELS:
        return shift
    body = np.zeros(2)
    seg = np.zeros((segment.max() + 1, 2))
    for _ in range(passes):
        for stage in ((0, 1) if whole else (1,)):
            if stage == 0:
                uv = obs["uv"] + body
                c, gx, gy = gradient(obs["crop"], uv)
                good = (np.linalg.norm(c - ref[texel], axis=1) < vl.OUTLIER) & ok
                if good.sum() >= MIN_ALIGN_TEXELS:
                    body = body + solve_shift(c[good] - ref[texel][good], gx[good], gy[good], wt[good], ridge)
                    body = np.clip(body, -MAX_ALIGN, MAX_ALIGN)
            else:
                uv = obs["uv"] + body + seg[segment[cell]]
                c, gx, gy = gradient(obs["crop"], uv)
                good = (np.linalg.norm(c - ref[texel], axis=1) < vl.OUTLIER) & ok
                for s in range(len(seg)):
                    m = good & (segment[cell] == s)
                    if m.sum() >= MIN_ALIGN_TEXELS:
                        seg[s] = np.clip(seg[s] + solve_shift(c[m] - ref[texel][m], gx[m], gy[m], wt[m], ridge * 5), -MAX_ALIGN, MAX_ALIGN)
    return body + seg[segment[cell]]


def build(observations, index, segment, aligned=None, rounds=2):
    """Textur (Kachel² × 3, Gewicht) aus Ausschnitten wie in veo_looks.main: Mittel mit Gewichten, im zweiten Durchgang ohne Ausreißer.
    `aligned`: Verschiebungen je Ausschnitt (Liste von (N, 2)), sonst keine."""
    size = vl.TILE * vl.TILE
    mean = None
    for rnd in range(rounds):
        sums, wsum = np.zeros((size, 3)), np.zeros(size)
        for k, o in enumerate(observations):
            uv = o["uv"] + (aligned[k] if aligned is not None else 0)
            colour = vl.sample(o["crop"], uv)
            texel = index[o["cell"].astype(int)]
            w = o["weight"].astype(np.float64)
            if rnd > 0:
                w = w * (np.linalg.norm(colour - mean[texel], axis=1) < vl.OUTLIER)
            for ch in range(3):
                sums[:, ch] += np.bincount(texel, w * colour[:, ch], minlength=size)
            wsum += np.bincount(texel, w, minlength=size)
        mean = sums / np.maximum(wsum, 1e-9)[:, None]
    return mean, wsum


def refined(observations, index, segment, steps=3, ridge=RIDGE):
    """Textur mit dichter Ausrichtung: erst Mittel ohne Verschiebung, dann in `steps` Runden jeden Ausschnitt auf das bisherige Mittel
    schieben und neu mitteln."""
    tex, wt = build(observations, index, segment)
    for _ in range(steps):
        sh = [align(o, tex, wt >= vl.ENOUGH, index, segment, ridge=ridge) for o in observations]
        tex, wt = build(observations, index, segment, aligned=sh)
    return tex, wt


def error(tex, wt, observations, index, segment, aligned):
    """Mittlere absolute Farbabweichung (über Kanäle und Stellen, gewichtet) der Prüfbilder zur Textur, getrennt nach Körperteilgruppe."""
    groups = {"Rumpf": ("torso",), "Kopf": ("head",), "Arme": ("upperarm", "lowerarm"), "Beine": ("thigh", "calf")}
    names = np.array([s.split("_")[0] for s in SEG_NAMES])
    sums = {g: [0.0, 0.0] for g in groups}
    for k, o in enumerate(observations):
        cell = o["cell"].astype(int)
        texel = index[cell]
        uv = o["uv"] + (aligned[k] if aligned is not None else 0)
        colour = vl.sample(o["crop"], uv)
        w = o["weight"] * (wt[texel] >= vl.ENOUGH) * (o["facing"].astype(float) > 0.5)
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


def measure(pkl_path, image_dir=None):
    pack = pickle.load(open(pkl_path, "rb"))
    index, segment = pack["index"], pack["segment"]
    variants = {"Mittel (bisher)": lambda tr: build(tr, index, segment),
                "ausgerichtet, 3 Runden": lambda tr: refined(tr, index, segment, 3),
                "ausgerichtet, 3 Runden, streng": lambda tr: refined(tr, index, segment, 3, ridge=0.1)}
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
            nominal = error(tex, wt, test, index, segment, None)
            sh = [align(o, tex, wt >= vl.ENOUGH, index, segment) for o in test]
            lined = error(tex, wt, test, index, segment, sh)
            sharp = sharpness(tex, wt)
            rows[name].append((nominal, lined, sharp))
            print(f"  {name:34s} Schärfe {sharp:5.1f} | unausgerichtet " + " ".join(f"{g} {v:5.2f}" for g, v in nominal.items()) +
                  " | ausgerichtet " + " ".join(f"{g} {v:5.2f}" for g, v in lined.items()) + f"  [{time.time() - began:.0f} s]", flush=True)
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
        print(f"  {name:34s} Schärfe {np.mean([v[2] for v in vals]):5.1f} | unausgerichtet " + " ".join(f"{g} {v:5.2f}" for g, v in nom.items()) +
              " | ausgerichtet " + " ".join(f"{g} {v:5.2f}" for g, v in lin.items()))


if __name__ == "__main__":
    if len(sys.argv) >= 9 and sys.argv[1] == "sammeln":
        collect(*sys.argv[2:8], sys.argv[8:])
    elif len(sys.argv) in (3, 4) and sys.argv[1] == "messen":
        measure(*sys.argv[2:])
    else:
        sys.exit(__doc__)
