#!/usr/bin/env python3
"""Liest Rückennummern aus dem Video, mit einem eigenen kleinen Netz, das lokal läuft.

  1. Ausschnitte: Aus den Gelenkpunkten jeder Erkennung ({det}.keypoints.npz, tools/veo_keypoints.py) wird der
     Rücken geschnitten, wenn der Spieler der Kamera den Rücken zeigt (linke Schulter im Bild links der
     rechten), von knapp über der Schulterlinie bis zur Hüfte, entzerrt auf 40×32 Pixel in Graustufen.
  2. Lesen: Ein kleines Faltungsnetz gibt Wahrscheinlichkeiten über 100 Klassen (0 = keine Nummer lesbar,
     1–99). Trainiert wird es nur auf künstlichen Rücken (tools/jersey_synth.py) und auf Vorderansichten aus
     den eigenen Videos als „keine Nummer“; Fremddaten (Veo) fließen nicht ein.
  3. Die Lesungen je Erkennung landen in {det}.numbers.npz (keine Bilder). Über die Nummer je Spur stimmt
     tools/jersey_identity.py ab.

Kein Bild verlässt den Rechner; Prüfausschnitte (--crops) nur unter data/work/.

Aufruf:
    .venv/bin/python tools/jersey_reader.py train [--out models/jersey-digits.pt] [--negatives DET.json ...] [--seed 0]
        Nachtrainieren an sicheren eigenen Lesungen: --init MODELL --pseudo DET.json ... --camera KAMERA.json
    .venv/bin/python tools/jersey_reader.py read SZENENVIDEO DETEKTIONEN.json KAMERA.json [--crops ORDNER]
"""
import argparse
import json
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from multiprocessing import Pool
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import jersey_synth  # noqa: E402
from jersey_identity import CLASSES, MAX_NO_NUMBER, NO_NUMBER, Reading  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
MODEL = REPO / "models" / "jersey-digits.pt"
CROP_H, CROP_W = jersey_synth.CROP_H, jersey_synth.CROP_W
L_SHOULDER, R_SHOULDER, L_HIP, R_HIP = 5, 6, 11, 12
MIN_CONF = 0.3        # Mindestsicherheit von Schultern und Hüften
MIN_DX = 2.0          # px: so weit muss die linke Schulter links der rechten liegen (Rücken zur Kamera)
MIN_HEIGHT = 18.0     # px Schulter bis Hüfte: darunter wird nicht gelesen
FULL_HEIGHT = 28.0    # px: ab hier zählt eine Lesung voll
MIN_WEIGHT = 0.3      # Gewicht einer Lesung bei MIN_HEIGHT
ABOVE, BELOW = 0.15, 0.05   # Ausschnitt: so viel Rumpfhöhe über der Schulter- und unter der Hüftlinie
HALF_WIDTH = (0.7, 0.45)    # halbe Breite: größer aus 0,7 × Schulterabstand und 0,45 × Rumpfhöhe
EVERY = 2             # jedes wievielte Bild gelesen wird
CACHE_FORMAT = 2.0
PSEUDO_CONFIDENCE = 0.98   # Selbsttraining: nur Spuren, deren Nummer der Leser schon so sicher
PSEUDO_AGREEMENT = 0.8     # und so einig bestimmt hat
TTA = ((0, 0, 1.0), (-1, 0, 1.0), (1, 0, 1.0), (0, 0, 0.93), (0, 0, 1.07))   # Verschiebung x, y in px und Maßstab


# ---------- Ausschnitte ----------

def is_back_view(kp: np.ndarray) -> bool:
    """Zeigt der Spieler der Kamera den Rücken? Die Nase hilft nicht: das Posenmodell meldet sie auch von hinten."""
    if min(kp[L_SHOULDER, 2], kp[R_SHOULDER, 2], kp[L_HIP, 2], kp[R_HIP, 2]) < MIN_CONF:
        return False
    return bool(kp[L_SHOULDER, 0] < kp[R_SHOULDER, 0] - MIN_DX)


def is_front_view(kp: np.ndarray) -> bool:
    if min(kp[L_SHOULDER, 2], kp[R_SHOULDER, 2], kp[L_HIP, 2], kp[R_HIP, 2]) < MIN_CONF:
        return False
    return bool(kp[L_SHOULDER, 0] > kp[R_SHOULDER, 0] + MIN_DX)


def _axis(kp: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    shoulders = (kp[L_SHOULDER, :2] + kp[R_SHOULDER, :2]) / 2
    hips = (kp[L_HIP, :2] + kp[R_HIP, :2]) / 2
    return shoulders.astype(np.float64), hips.astype(np.float64)


def back_height(kp: np.ndarray) -> float:
    shoulders, hips = _axis(kp)
    return float(np.linalg.norm(hips - shoulders))


def back_quad(kp: np.ndarray) -> np.ndarray:
    """Viereck des Rückens im Bild (oben links, oben rechts, unten rechts, unten links), entlang der Rumpfachse."""
    shoulders, hips = _axis(kp)
    down = hips - shoulders
    h = max(np.linalg.norm(down), 1e-6)
    down /= h
    across = np.array([-down[1], down[0]])
    if across[0] < 0:
        across = -across
    half = max(HALF_WIDTH[0] * abs(kp[L_SHOULDER, 0] - kp[R_SHOULDER, 0]), HALF_WIDTH[1] * h)
    top, bottom = shoulders - down * ABOVE * h, hips + down * BELOW * h
    return np.array([top - across * half, top + across * half, bottom + across * half, bottom - across * half])


def crop_back(image: np.ndarray, quad: np.ndarray) -> np.ndarray:
    """Entzerrter Graustufenausschnitt CROP_H × CROP_W mit gestrecktem Kontrast."""
    dst = np.float32([[0, 0], [CROP_W, 0], [CROP_W, CROP_H], [0, CROP_H]])
    m = cv2.getPerspectiveTransform(quad.astype(np.float32), dst)
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return jersey_synth.normalise(cv2.warpPerspective(gray, m, (CROP_W, CROP_H), flags=cv2.INTER_LINEAR,
                                                      borderMode=cv2.BORDER_REPLICATE))


def back_crop(image: np.ndarray, kp: np.ndarray) -> np.ndarray | None:
    """Ausschnitt des Rückens oder None, wenn er zu klein ist."""
    if back_height(kp) < MIN_HEIGHT:
        return None
    return crop_back(image, back_quad(kp))


def reading_weight(height_px: float) -> float:
    share = np.clip((height_px - MIN_HEIGHT) / (FULL_HEIGHT - MIN_HEIGHT), 0.0, 1.0)
    return float(MIN_WEIGHT + (1.0 - MIN_WEIGHT) * share)


def check_private_dir(path: str | Path) -> Path:
    """Ausschnitte und Berichte dürfen nur unter data/work/ liegen (nicht eingecheckt, nicht im Viewer)."""
    p = Path(path)
    p = (p if p.is_absolute() else Path.cwd() / p).resolve()
    if not p.is_relative_to((REPO / "data" / "work").resolve()):
        raise ValueError(f"{path} liegt nicht unter data/work/; Ausschnitte von Spielern bleiben dort")
    return p


# ---------- Netz ----------

def build_net():
    import torch.nn as nn

    def block(a, b):
        return [nn.Conv2d(a, b, 3, padding=1), nn.BatchNorm2d(b), nn.ReLU(inplace=True),
                nn.Conv2d(b, b, 3, padding=1), nn.BatchNorm2d(b), nn.ReLU(inplace=True), nn.MaxPool2d(2)]
    return nn.Sequential(*block(1, 32), *block(32, 64), *block(64, 128), nn.Flatten(), nn.Dropout(0.3),
                         nn.Linear(128 * (CROP_H // 8) * (CROP_W // 8), 128), nn.ReLU(inplace=True),
                         nn.Dropout(0.3), nn.Linear(128, CLASSES))


def _to_tensor(x: np.ndarray, device):
    import torch
    return torch.from_numpy(x.astype(np.float32) / 127.5 - 1.0).unsqueeze(1).to(device)


def load_net(model_path: str | Path = MODEL):
    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    net = build_net().to(device)
    net.load_state_dict(torch.load(model_path, map_location=device, weights_only=True))
    net.eval()
    return net, device


def predict(net, device, crops: np.ndarray, chunk: int = 2048) -> np.ndarray:
    import torch
    out = []
    with torch.no_grad():
        for a in range(0, len(crops), chunk):
            out.append(torch.softmax(net(_to_tensor(crops[a:a + chunk], device)), 1).cpu().numpy())
    return np.concatenate(out) if out else np.zeros((0, CLASSES), np.float32)


def predict_steady(net, device, crops: np.ndarray) -> np.ndarray:
    """Jeden Ausschnitt leicht verschoben und skaliert mehrfach lesen und mitteln: ungenaue Gelenkpunkte
    verschieben den Ausschnitt um ein, zwei Pixel; das soll die Lesung nicht kippen."""
    if not len(crops):
        return predict(net, device, crops)
    out = np.zeros((len(crops), CLASSES), np.float64)
    for dx, dy, scale in TTA:
        m = cv2.getRotationMatrix2D((CROP_W / 2, CROP_H / 2), 0, scale)
        m[:, 2] += (dx, dy)
        moved = np.stack([cv2.warpAffine(c, m, (CROP_W, CROP_H), borderMode=cv2.BORDER_REPLICATE) for c in crops])
        out += predict(net, device, moved)
    return (out / len(TTA)).astype(np.float32)


def _synth_part(args):
    seed, n = args
    return jersey_synth.batch(n, np.random.default_rng(seed))


def synth_set(n: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    parts = [(seed * 100003 + k, 2000) for k in range(max(n // 2000, 1))]
    with Pool() as pool:
        res = pool.map(_synth_part, parts)
    return np.concatenate([r[0] for r in res]), np.concatenate([r[1] for r in res])


def front_crops(det_path: str | Path, limit: int = 20000) -> np.ndarray:
    """Vorderansichten aus einer eigenen Szene als Beispiele für „keine Nummer“ (nur im Speicher)."""
    det = json.loads(Path(det_path).read_text())
    kp_all = np.load(f"{det_path}.keypoints.npz")
    kp, index = kp_all["kp"], kp_all["index"]
    out = []
    cap = cv2.VideoCapture(str(det["video"]) if Path(det["video"]).exists() else str(Path(det_path).with_suffix("").with_suffix(".mp4")))
    half = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) // 2
    f = 0
    while len(out) < limit:
        ok, image = cap.read()
        if not ok or f >= len(index):
            break
        if f % EVERY == 0:
            for li in range(2):
                lens = image[li * half:(li + 1) * half]
                for k in range(*index[f, li]):
                    if is_front_view(kp[k]) and back_height(kp[k]) >= MIN_HEIGHT:
                        out.append(crop_back(lens, back_quad(kp[k])))
        f += 1
    cap.release()
    return np.array(out, np.uint8).reshape(-1, CROP_H, CROP_W)


def crops_at(video: str | Path, det_path: str | Path, wanted: set[tuple[int, int, int]]) -> dict:
    """Rückenausschnitte der gewünschten Erkennungen (Bild, Linse, Box), nur im Speicher."""
    kp_all = np.load(f"{det_path}.keypoints.npz")
    kp, index = kp_all["kp"], kp_all["index"]
    last = max((w[0] for w in wanted), default=-1)
    out = {}
    cap = cv2.VideoCapture(str(video))
    half = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) // 2
    f = 0
    while f <= last:
        ok, image = cap.read()
        if not ok:
            break
        for li in range(2):
            a, b = index[f, li]
            for j in range(b - a):
                if (f, li, j) in wanted:
                    crop = back_crop(image[li * half:(li + 1) * half], kp[a + j])
                    if crop is not None:
                        out[(f, li, j)] = crop
        f += 1
    cap.release()
    return out


def pseudo_crops(det_path: str, camera_path: str, model_path: str | Path = MODEL) -> tuple[np.ndarray, np.ndarray]:
    """Selbsttraining ohne Fremddaten: Rücken aus Spuren, deren Nummer der Leser schon sehr sicher und einig
    bestimmt hat, mit dieser Nummer als Klasse. Bringt dem Netz die echte Trikotschrift bei."""
    import veo_camera
    from own_scene import own_identities
    import jersey_identity
    det = json.loads(Path(det_path).read_text())
    video = det["video"]
    ids = own_identities(det, veo_camera.load(camera_path), len(det["frames"]), video)
    tracks = {f"{k[0]}-{k[1]}": v[2] for k, v in ids.items()}
    teams = {name: name.rsplit("-", 1)[0] for name in tracks}
    scene = read_scene(video, det_path, model_path)
    votes = jersey_identity.vote(readings_for_tracks(scene, tracks), teams, det["fps"])
    label = {n: v.number for n, v in votes.items()
             if v.number is not None and v.confidence >= PSEUDO_CONFIDENCE and v.agreement >= PSEUDO_AGREEMENT}
    owner = {(f, int(r[3]), int(r[8])): label[n] for n in label for f, r in tracks[n].items()}
    wanted = {(int(f), int(li), int(j)) for f, li, j, p in zip(scene.frame, scene.lens, scene.box, scene.probs)
              if (int(f), int(li), int(j)) in owner and p[NO_NUMBER] < MAX_NO_NUMBER}
    crops = crops_at(video, det_path, wanted)
    keys = sorted(crops)
    print(f"Selbsttraining aus {det_path}: Nummern {sorted(set(label.values()))}, {len(keys)} Rücken", flush=True)
    return (np.array([crops[k] for k in keys], np.uint8).reshape(-1, CROP_H, CROP_W),
            np.array([owner[k] for k in keys], np.int64))


def train(out: Path, negatives: list[str], seed: int, samples: int, epochs: int,
          pseudo: list[str] = (), camera: str | None = None, init: Path | None = None) -> float:
    import torch
    torch.manual_seed(seed)
    began = time.time()
    x, y = synth_set(samples, seed)
    real = [front_crops(p) for p in negatives]
    if real:
        neg = np.concatenate(real)
        x, y = np.concatenate([x, neg]), np.concatenate([y, np.full(len(neg), NO_NUMBER)])
        print(f"{len(neg)} Vorderansichten aus eigenen Szenen als „keine Nummer“", flush=True)
    found = [pseudo_crops(p, camera, init or MODEL) for p in pseudo]
    if found:
        px, py = np.concatenate([f[0] for f in found]), np.concatenate([f[1] for f in found])
        repeat = max(int(0.1 * len(x) / max(len(px), 1)), 1)   # echte Rücken etwa ein Zehntel des Trainings
        x, y = np.concatenate([x] + [px] * repeat), np.concatenate([y] + [py] * repeat)
    xv, yv = synth_set(10000, seed + 1)
    print(f"{len(x)} Trainingsausschnitte, {len(xv)} zum Prüfen ({time.time() - began:.0f} s)", flush=True)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    net = build_net().to(device)
    if init:
        net.load_state_dict(torch.load(init, map_location=device, weights_only=True))
    opt = torch.optim.AdamW(net.parameters(), lr=2e-3, weight_decay=1e-4)
    steps = epochs * (len(x) // 512)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=1e-3 if init else 3e-3, total_steps=steps)
    rng = np.random.default_rng(seed)
    yt = torch.from_numpy(y).to(device)
    xt = _to_tensor(x, device)
    for epoch in range(epochs):
        net.train()
        order = torch.from_numpy(rng.permutation(len(x))).to(device)
        for a in range(0, len(x) - 511, 512):
            idx = order[a:a + 512]
            loss = torch.nn.functional.cross_entropy(net(xt[idx]), yt[idx], label_smoothing=0.05)
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
        net.eval()
        acc = float((predict(net, device, xv).argmax(1) == yv).mean())
        print(f"  Runde {epoch + 1}/{epochs}: Verlust {loss.item():.3f}, Treffer auf Prüfsatz {acc:.1%}", flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(net.state_dict(), out)
    print(f"-> {out} ({time.time() - began:.0f} s)")
    return acc


# ---------- Lesen ----------

@dataclass
class SceneReadings:
    """Lesungen aller Rücken einer Szene, je Erkennung (Bild, Linse, Box)."""
    frame: np.ndarray    # int32[R]
    lens: np.ndarray     # int8[R]
    box: np.ndarray      # int32[R]
    probs: np.ndarray    # float16[R, CLASSES]
    height: np.ndarray   # float32[R], Schulter bis Hüfte in px


def _stamp(video, det_path, model_path) -> np.ndarray:
    return np.array([Path(video).stat().st_mtime, Path(det_path).stat().st_mtime, Path(model_path).stat().st_mtime,
                     CACHE_FORMAT])


def read_scene(video: str | Path, det_path: str | Path, model_path: str | Path = MODEL,
               crops_dir: str | Path | None = None) -> SceneReadings:
    """Liest alle Rücken der Szene (jedes EVERY-te Bild); Zwischenspeicher {det}.numbers.npz."""
    cache = Path(f"{det_path}.numbers.npz")
    stamp = _stamp(video, det_path, model_path)
    if cache.exists() and crops_dir is None:
        c = np.load(cache)
        if np.array_equal(c["stamp"], stamp):
            return SceneReadings(c["frame"], c["lens"], c["box"], c["probs"], c["height"])
    kp_all = np.load(f"{det_path}.keypoints.npz")
    kp, index = kp_all["kp"], kp_all["index"]
    crops, meta = [], []
    cap = cv2.VideoCapture(str(video))
    half = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) // 2
    f = 0
    while f < len(index):
        ok, image = cap.read()
        if not ok:
            break
        if f % EVERY == 0:
            for li in range(2):
                a, b = index[f, li]
                lens = image[li * half:(li + 1) * half]
                for k in range(a, b):
                    if not is_back_view(kp[k]):
                        continue
                    crop = back_crop(lens, kp[k])
                    if crop is not None:
                        crops.append(crop)
                        meta.append((f, li, k - a, back_height(kp[k])))
        f += 1
    cap.release()
    net, device = load_net(model_path)
    probs = predict_steady(net, device, np.array(crops, np.uint8).reshape(-1, CROP_H, CROP_W))
    m = np.array(meta, np.float64).reshape(-1, 4)
    out = SceneReadings(m[:, 0].astype(np.int32), m[:, 1].astype(np.int8), m[:, 2].astype(np.int32),
                        probs.astype(np.float16), m[:, 3].astype(np.float32))
    np.savez_compressed(cache, frame=out.frame, lens=out.lens, box=out.box, probs=out.probs, height=out.height,
                        stamp=stamp)
    if crops_dir is not None:
        _write_crops(check_private_dir(crops_dir), crops, out)
    return out


def _write_crops(folder: Path, crops: list[np.ndarray], readings: SceneReadings) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for i, crop in enumerate(crops):
        best = int(np.argmax(readings.probs[i]))
        cv2.imwrite(str(folder / f"f{readings.frame[i]:04d}_l{readings.lens[i]}_b{readings.box[i]:02d}_n{best:02d}.png"), crop)


def readings_for_tracks(scene: SceneReadings, tracks: Mapping[str, Mapping[int, np.ndarray]]) -> list[Reading]:
    """Lesungen den Spuren zuordnen: Spurzeile r mit Linse r[3] und Boxnummer r[8] (tools/track_players.detections)."""
    owner = {}
    for track, frames in tracks.items():
        for f, r in frames.items():
            owner[(int(f), int(r[3]), int(r[8]))] = track
    out = []
    for i in range(len(scene.frame)):
        track = owner.get((int(scene.frame[i]), int(scene.lens[i]), int(scene.box[i])))
        if track is not None:
            out.append(Reading(track, int(scene.frame[i]), scene.probs[i].astype(np.float64), reading_weight(float(scene.height[i]))))
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train")
    t.add_argument("--out", type=Path, default=MODEL)
    t.add_argument("--negatives", nargs="*", default=[])
    t.add_argument("--seed", type=int, default=0)
    t.add_argument("--samples", type=int, default=400000)
    t.add_argument("--epochs", type=int, default=12)
    t.add_argument("--pseudo", nargs="*", default=[], help="Szenen fürs Selbsttraining (DETEKTIONEN.json)")
    t.add_argument("--camera", help="Kamera der Szenen fürs Selbsttraining")
    t.add_argument("--init", type=Path, help="mit diesem Modell beginnen (Nachtrainieren)")
    r = sub.add_parser("read")
    r.add_argument("video")
    r.add_argument("det")
    r.add_argument("camera")
    r.add_argument("--crops")
    r.add_argument("--model", default=str(MODEL))
    args = ap.parse_args(argv)
    if args.cmd == "train":
        try:
            train(args.out, args.negatives, args.seed, args.samples, args.epochs, args.pseudo, args.camera, args.init)
        except jersey_synth.FontNotFound as err:
            sys.exit(f"Keine Schrift für die Trainingsbilder: {err}")
        return
    if args.crops:
        check_private_dir(args.crops)
    import jersey_identity
    import track_players
    import veo_camera
    from own_scene import TEAM_OF_COLOUR
    began = time.time()
    scene = read_scene(args.video, args.det, args.model, args.crops)
    det = json.loads(Path(args.det).read_text())
    tracks = track_players.track(det, veo_camera.load(args.camera))
    named = {f"{TEAM_OF_COLOUR.get(tr['colour'], 'opponent')}-{k}": tr["frames"] for k, tr in enumerate(tracks)}
    teams = {name: name.split("-")[0] for name in named}
    votes = jersey_identity.vote(readings_for_tracks(scene, named), teams, det["fps"])
    print(f"{len(scene.frame)} Rücken gelesen in {time.time() - began:.0f} s")
    for name, v in sorted(votes.items(), key=lambda kv: -kv[1].windows):
        if v.ranked:
            print(f"  {name:16s} {str(v.number or '?'):>3s}  beste {v.ranked[0][0]:2d} ({v.ranked[0][1]:.2f}), "
                  f"Fenster {v.windows}, über {v.span_s:.1f} s, Einigkeit {v.agreement:.0%}")


if __name__ == "__main__":
    main()
