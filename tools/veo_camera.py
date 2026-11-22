#!/usr/bin/env python3
"""Kalibriert die beiden Bildhälften des Veo-Panoramas an den Platzlinien und misst den Platz aus.

Kameramodell: Veos eigene Linsendaten aus camera_alignment.json (Brennweite, Bildmitte,
Verzeichnung nach dem Rationalmodell von OpenCV, Ausrichtung der beiden Linsen zueinander).
Die Bildhälften des Panoramas sind das Sensorbild in anderem Maßstab, und unterhalb einer
Zeile (rund 608 von 1024) ist das Bild senkrecht um etwa das Doppelte gestaucht: Gerade
Linien haben dort einen Knick. Diese Abbildung Sensor -> Bildhälfte (Versatz, Maßstab,
Knickzeile, Stauchung je Linse) wird hier bestimmt, dazu Standort und Blickrichtung der
Kamera sowie Länge und Breite des Platzes. Veos eigene Platzlage wird nicht verwendet: Veo
legt vier angeklickte Ecken zugrunde und nimmt 105 m Länge an.

Vorgehen: Aus vielen Bildern wird ein Hintergrundbild ohne Spieler gerechnet (Median).
Jede Linie des Normplatzes wird im Bild entlang ihrer vorhergesagten Lage verfolgt und
bleibt dabei ihrer Normlinie fest zugeordnet. Bei den Außenlinien zählt die erste Linie von
innen, weil dahinter oft ein heller Randstein liegt. Den Maßstab liefern die genormten Maße:
Tor 7,32 × 2,44 m, Mittelkreis 9,15 m, Strafraum 16,5 × 40,32 m, Torraum 5,5 × 18,32 m.

Start: etwa 19 von Hand abgelesene Punkte je Hälfte (Ecken, Mittellinie, Mittelkreis,
Strafraum, Torraum, Torpfosten unten und oben).

Aufruf:
    .venv/bin/python tools/veo_camera.py VIDEO HANDPUNKTE.json CAMERA_ALIGNMENT.json AUSGABE.json [KONTROLLBILD.jpg]

VIDEO darf auch ein fertiges Hintergrundbild sein. Andere Werkzeuge nutzen load(), project(),
rays() und to_ground(). Weltkoordinaten: Meter, Ursprung Anstoßpunkt, x längs, y quer (von
der Kamera weg), z hoch.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter, map_coordinates
from scipy.optimize import least_squares
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

LENSES = ("left", "right")
BOX, BOX_W, SIX, SIX_W, RADIUS, SPOT = 16.5, 40.32, 5.5, 18.32, 9.15, 11.0
GOAL_W, GOAL_H = 7.32, 2.44
MAP_START = (0.0, 1.895, 0.0, 1.476, 608.7, 2.011)  # Versatz u, Maßstab u, Versatz v, Maßstab v, Knickzeile, Stauchung
                                                    # (gemessen am Spiel vom 2026-11-01, Bildhälfte 2048 × 1024)
BOUNDARY = ("touch-", "touch+", "goalL", "goalR")
STEP = 0.5     # Raster quer zur Linie beim Verfolgen (Pixel)
PEAK = 10.0    # Mindestkontrast einer Linie gegen beide Seiten
CLIP = 25.0    # mehr Kontrast zählt nicht: schwache Linien sind so viel wert wie kräftige
JUMP = 100.0   # Preis je Rasterschritt Seitenversatz zwischen Nachbarpunkten


# ---------------------------------------------------------------- Kameramodell

def _factor(r2, k):
    return (1 + k[0] * r2 + k[1] * r2**2 + k[2] * r2**3) / (1 + k[3] * r2 + k[4] * r2**2 + k[5] * r2**3)


def _prepare(cam):
    """Rechnet je Linse die Drehung Welt -> Linse und den Linsenmittelpunkt aus."""
    cam["position"] = np.asarray(cam["position"], float)
    to_camera = Rotation.from_rotvec(cam["rotation"]).as_matrix()
    for p in cam["lenses"].values():
        for key in ("R", "t", "K", "dist", "map"):
            p[key] = np.asarray(p[key], float)
        p["W"] = p["R"].T @ to_camera
        p["centre"] = cam["position"] + to_camera.T @ p["t"]
    return cam


def project(cam, lens, points):
    """Weltpunkte (n, 3) -> Pixel in der Bildhälfte (n, 2); NaN hinter der Linse."""
    p = cam["lenses"][lens]
    pl = (np.asarray(points, float).reshape(-1, 3) - p["centre"]) @ p["W"].T
    z = np.where(pl[:, 2] > 0.05, pl[:, 2], np.nan)
    a, b = pl[:, 0] / z, pl[:, 1] / z
    fac = _factor(a * a + b * b, p["dist"])
    fx, fy, cx, cy = p["K"]
    au, bu, av, bv, v0, kappa = p["map"]
    u = (fx * a * fac + cx - au) / bu
    v = (fy * b * fac + cy - av) / bv
    return np.column_stack([u, np.where(v > v0, v0 + (v - v0) / kappa, v)])


def rays(cam, lens, pixels):
    """Pixel (n, 2) -> Blickrichtungen in Weltkoordinaten (n, 3), Länge 1."""
    p = cam["lenses"][lens]
    px = np.asarray(pixels, float).reshape(-1, 2)
    fx, fy, cx, cy = p["K"]
    au, bu, av, bv, v0, kappa = p["map"]
    v = np.where(px[:, 1] > v0, v0 + (px[:, 1] - v0) * kappa, px[:, 1])
    xd, yd = (au + bu * px[:, 0] - cx) / fx, (av + bv * v - cy) / fy
    rd = np.hypot(xd, yd)
    k = p["dist"]
    r = rd.copy()
    for _ in range(20):  # Newton: r · Faktor(r²) = rd nach r auflösen
        r2 = r * r
        num, den = 1 + k[0] * r2 + k[1] * r2**2 + k[2] * r2**3, 1 + k[3] * r2 + k[4] * r2**2 + k[5] * r2**3
        dnum, dden = 2 * k[0] * r + 4 * k[1] * r**3 + 6 * k[2] * r**5, 2 * k[3] * r + 4 * k[4] * r**3 + 6 * k[5] * r**5
        r = np.clip(r - (r * num / den - rd) / (num / den + r * (dnum * den - num * dden) / den**2), 0, 6)
    s = r / np.maximum(rd, 1e-12)
    d = np.column_stack([xd * s, yd * s, np.ones(len(px))])
    return (d / np.linalg.norm(d, axis=1, keepdims=True)) @ p["W"]


def to_ground(cam, lens, pixels, height=0.0):
    """Pixel (n, 2) -> Punkt auf der Ebene z = height (n, 2) und Entfernung von der Kamera; NaN über dem Horizont."""
    d = rays(cam, lens, pixels)
    pos = cam["lenses"][lens]["centre"]
    with np.errstate(divide="ignore", invalid="ignore"):
        t = (height - pos[2]) / d[:, 2]
    t = np.where((d[:, 2] < -1e-6) & (t > 0), t, np.nan)
    return pos[:2] + d[:, :2] * t[:, None], t


def load(path):
    return _prepare(json.loads(Path(path).read_text()))


def read_veo(path):
    """Veos Linsendaten und Veos Schätzung der Kameralage (nur als Startwert)."""
    al = json.loads(Path(path).read_text())["alignment"]

    def numbers(text):
        return np.array([float(v) for v in text.split(",")])
    lenses = {}
    for name in LENSES:
        m = numbers(al[f"lens_{name}2camera"]).reshape(4, 4)
        k = numbers(al[f"intrinsic_{name}"]).reshape(3, 3)
        d = numbers(al[f"distortion_{name}"])     # Reihenfolge wie OpenCV: k1, k2, p1, p2, k3, k4, k5, k6, ...
        if np.abs(d[[2, 3]]).max() > 0 or np.abs(d[8:]).max() > 0:
            raise SystemExit("Die Verzeichnung enthält Anteile, die dieses Modell nicht kennt (p1, p2, s1..s4, tau).")
        lenses[name] = {"R": m[:3, :3], "t": m[:3, 3], "K": np.array([k[0, 0], k[1, 1], k[0, 2], k[1, 2]]), "dist": d[[0, 1, 4, 5, 6, 7]]}
    c = numbers(al["camera2world"]).reshape(4, 4)
    swap = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], float)   # Veo: y nach unten, z vom Standort weg
    return lenses, Rotation.from_matrix((swap @ c[:3, :3]).T).as_rotvec(), swap @ c[:3, 3], float(al.get("field_length", 105.0))


def veo_corners(path, size):
    """Die vier in Veo angeklickten Platzecken als Handpunkte je Linse (oft einige Meter daneben)."""
    stacked = json.loads(Path(path).read_text())["selected_corners"]["corners_stacked"]
    out = {lens: [] for lens in LENSES}
    for key, (along, across) in {"cl": (-1, -1), "fl": (-1, 1), "cr": (1, -1), "fr": (1, 1)}.items():
        for i, lens in enumerate(LENSES):
            c = stacked[key][lens]
            if c["valid"] > 0:
                out[lens].append([along, 0, across, 0, 0, c["stacked"][0] * size[0], c["stacked"][1] * 2 * size[1] - i * size[1]])
    return {lens: np.array(v, float).reshape(-1, 7) for lens, v in out.items()}


# ---------------------------------------------------------------- Normplatz und Linien im Bild

def model_lines(length, width, step=0.05):
    """Linien des Normplatzes und die Torlatten als Punktfolgen (n, 3), Punktabstand step in Metern."""
    hl, hw = length / 2, width / 2

    def seg(a, b):
        a, b = np.array(a, float), np.array(b, float)
        n = int(np.linalg.norm(b - a) / step) + 2
        p = a + np.linspace(0, 1, n)[:, None] * (b - a)
        return p if p.shape[1] == 3 else np.column_stack([p, np.zeros(n)])

    def arc(cx, a0, a1):
        ang = np.linspace(a0, a1, int(abs(a1 - a0) * RADIUS / step) + 2)
        return np.column_stack([cx + RADIUS * np.cos(ang), RADIUS * np.sin(ang), np.zeros(len(ang))])

    lines = {"touch-": seg((-hl, -hw), (hl, -hw)), "touch+": seg((-hl, hw), (hl, hw)), "half": seg((0, -hw), (0, hw)),
             "circle": arc(0, 0, 2 * np.pi)}
    half = np.arccos((BOX - SPOT) / RADIUS)
    for s, tag in ((-1, "L"), (1, "R")):
        g = s * hl
        lines["goal" + tag] = seg((g, -hw), (g, hw))
        for name, depth, wide in (("box", BOX, BOX_W), ("six", SIX, SIX_W)):
            lines[name + tag + "a"] = seg((g, -wide / 2), (g - s * depth, -wide / 2))
            lines[name + tag + "b"] = seg((g - s * depth, -wide / 2), (g - s * depth, wide / 2))
            lines[name + tag + "c"] = seg((g - s * depth, wide / 2), (g, wide / 2))
        turn = np.pi if s == 1 else 0.0
        lines["arc" + tag] = arc(g - s * SPOT, turn - half, turn + half)
        lines["bar" + tag] = seg((g, -GOAL_W / 2, GOAL_H), (g, GOAL_W / 2, GOAL_H))
    return lines


def background(video, samples=41):
    cap = cv2.VideoCapture(video)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    stack = []
    for k in range(samples):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int((k + 0.5) * total / samples))
        ok, image = cap.read()
        if ok:
            stack.append(image)
    return np.median(np.stack(stack), axis=0).astype(np.uint8)


def brightness(image):
    """Helligkeit für die Liniensuche: Weiß hat viel Blau und Rot, Rasen und gelbe Linien nicht."""
    return gaussian_filter(np.minimum(image[..., 0], image[..., 2]).astype(np.float32), 0.7)


def trace(bright, uv, inside, reach, boundary):
    """Folgt einer hellen Linie entlang der vorhergesagten Kurve uv (n, 2), höchstens reach Pixel daneben.

    inside: dieselbe Kurve, ein Stück ins Platzinnere verschoben. Bei Außenlinien (boundary) zählt
    nur die erste Linie von innen. Rückgabe: Punkte auf der Linie (m, 2)."""
    h, w = bright.shape
    ok = ~np.isnan(uv).any(axis=1) & ~np.isnan(inside).any(axis=1) & (uv[:, 0] > 8) & (uv[:, 0] < w - 9) & (uv[:, 1] > 8) & (uv[:, 1] < h - 9)
    out = []
    edges = np.flatnonzero(np.diff(np.concatenate([[0], ok.astype(int), [0]])))
    for a, b in zip(edges[::2], edges[1::2]):
        run = uv[a:b]
        if len(run) < 3:
            continue
        s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(run, axis=0), axis=1))])
        if s[-1] < 8:
            continue
        t = np.arange(0, s[-1], 1.0)
        p = np.column_stack([np.interp(t, s, run[:, 0]), np.interp(t, s, run[:, 1])])
        tan = np.gradient(p, axis=0)
        tan /= np.maximum(np.linalg.norm(tan, axis=1, keepdims=True), 1e-9)
        nrm = np.column_stack([-tan[:, 1], tan[:, 0]])
        inward = np.column_stack([np.interp(t, s, inside[a:b, 0]), np.interp(t, s, inside[a:b, 1])]) - p
        if np.median((inward * nrm).sum(axis=1)) < 0:
            nrm = -nrm                                   # positive Versätze zeigen ins Platzinnere
        pad = int(4 / STEP)
        off = np.arange(-reach - 4, reach + 4 + STEP / 2, STEP)
        q = p[:, None, :] + off[None, :, None] * nrm[:, None, :]
        v = map_coordinates(bright, [q[..., 1], q[..., 0]], order=1, mode="nearest")
        k = v.shape[1] - 2 * pad
        # Kontrast gegen beide Seiten, für dünne (2 px) und breite (4 px) Linien
        score = np.maximum.reduce([v[:, pad:pad + k] - np.maximum(v[:, pad - d:pad - d + k], v[:, pad + d:pad + d + k]) for d in (int(2 / STEP), int(4 / STEP))])
        off = off[pad:pad + k]
        if boundary:
            peak = (score > PEAK) & (score >= np.roll(score, 1, axis=1)) & (score >= np.roll(score, -1, axis=1))
            first = np.where(peak.any(axis=1), k - 1 - peak[:, ::-1].argmax(axis=1), -1)     # innerste Linie = größter Versatz
            beyond = np.arange(k)[None, :] < (first[:, None] - int(1.5 / STEP))
            score = np.where(beyond & (first[:, None] >= 0), 0.0, score)
        # Glatter Weg mit dem meisten Kontrast (Viterbi)
        n = len(p)
        cost = -np.clip(score, 0, CLIP)
        total = cost[0].copy()
        back = np.zeros((n, k), np.int8)
        for i in range(1, n):
            cand = np.stack([np.concatenate([[np.inf], total[:-1]]) + JUMP, total, np.concatenate([total[1:], [np.inf]]) + JUMP])
            pick = cand.argmin(axis=0)
            back[i] = pick - 1
            total = cand[pick, np.arange(k)] + cost[i]
        j = int(total.argmin())
        path = np.zeros(n, int)
        for i in range(n - 1, -1, -1):
            path[i] = j
            j += back[i, j]
        rows = np.arange(n)
        num = den = 0.0
        for d in (-2, -1, 0, 1, 2):                      # Lage genauer als das Raster: Schwerpunkt des Kontrasts
            c = np.clip(score[rows, np.clip(path + d, 0, k - 1)], 0, None)
            num, den = num + c * d * STEP, den + c
        fine = off[path] + num / np.maximum(den, 1e-6)
        good = (score[rows, path] > PEAK) & (path > 1) & (path < k - 2)
        out.append((p + fine[:, None] * nrm)[good][::2])
    return np.concatenate(out) if out else np.zeros((0, 2))


# ---------------------------------------------------------------- Anpassung

class Fit:
    """Unbekannte x: Drehvektor Welt -> Kamera (3), Standort (3), Länge, Breite, je Linse die Abbildung Sensor -> Bildhälfte (6)."""

    def __init__(self, image, landmarks, veo_lenses):
        h = image.shape[0] // 2
        self.size = [image.shape[1], h]
        self.bright = {lens: brightness(image[i * h:(i + 1) * h]) for i, lens in enumerate(LENSES)}
        self.landmarks = landmarks
        self.veo = veo_lenses
        self.traced = {lens: {} for lens in LENSES}

    def camera(self, x):
        return _prepare({"position": x[3:6], "rotation": x[0:3], "pitch": {"length": x[6], "width": x[7]},
                         "lenses": {lens: {**self.veo[lens], "map": x[8 + 6 * i:14 + 6 * i]} for i, lens in enumerate(LENSES)}})

    def landmark_residuals(self, x):
        cam = self.camera(x)
        out = []
        for lens in LENSES:
            lm = self.landmarks[lens]
            world = np.column_stack([lm[:, 0] * x[6] / 2 + lm[:, 1], lm[:, 2] * x[7] / 2 + lm[:, 3], lm[:, 4]])
            out.append(np.nan_to_num(project(cam, lens, world) - lm[:, 5:7], nan=500.0).ravel())
        return np.concatenate(out)

    def retrace(self, x, reach):
        cam = self.camera(x)
        for lens in LENSES:
            self.traced[lens] = {}
            for name, pts in model_lines(x[6], x[7]).items():
                inner = pts.copy()
                inner[:, :2] *= 1 - 0.5 / np.maximum(np.linalg.norm(pts[:, :2], axis=1, keepdims=True), 1.0)
                found = trace(self.bright[lens], project(cam, lens, pts), project(cam, lens, inner), reach, name in BOUNDARY)
                if len(found) >= 8:
                    self.traced[lens][name] = found

    def line_residuals(self, x):
        """Abstand jedes verfolgten Bildpunkts zur Projektion seiner Normlinie, mit Vorzeichen (Pixel)."""
        cam = self.camera(x)
        lines = model_lines(x[6], x[7], step=0.04)
        out = {}
        for lens in LENSES:
            for name, pts in self.traced[lens].items():
                uv = project(cam, lens, lines[name])
                uv = uv[~np.isnan(uv).any(axis=1)]
                if len(uv) < 3:
                    out[lens, name] = np.full(len(pts), 30.0)
                    continue
                j = np.clip(cKDTree(uv).query(pts)[1], 1, len(uv) - 2)
                tan = uv[j + 1] - uv[j - 1]
                tan /= np.maximum(np.linalg.norm(tan, axis=1, keepdims=True), 1e-9)
                d = pts - uv[j]
                out[lens, name] = np.clip(d[:, 0] * tan[:, 1] - d[:, 1] * tan[:, 0], -30, 30)
        return out

    def solve(self, x, free, lines=True, hand_weight=0.5):
        def embed(v):
            full = x.copy()
            full[free] = v
            return full

        def residuals(v):
            full = embed(v)
            if not lines:
                return self.landmark_residuals(full)
            r = self.line_residuals(full)
            return np.concatenate([self.landmark_residuals(full) * hand_weight] + [r[k] for k in sorted(r)])
        return embed(least_squares(residuals, x[free], loss="soft_l1", f_scale=2 if lines else 6, x_scale="jac", max_nfev=300).x)


def free_parameters(*names):
    m = np.zeros(20, bool)
    m[0:8] = True                     # Lage der Kamera und Platzmaße
    for i in range(2):
        m[[8 + 6 * i, 10 + 6 * i]] = "offset" in names
        m[[9 + 6 * i, 11 + 6 * i]] = "scale" in names
        m[[12 + 6 * i, 13 + 6 * i]] = "kink" in names
    return m


def main(video, landmarks_path, veo_path, out_path, check=None):
    image = cv2.imread(video) if Path(video).suffix.lower() in (".png", ".jpg", ".jpeg") else background(video)
    size = [image.shape[1], image.shape[0] // 2]
    by_hand = landmarks_path != "-"
    landmarks = {lens: np.array(json.loads(Path(landmarks_path).read_text())[lens], float) for lens in LENSES} if by_hand else veo_corners(veo_path, size)
    veo_lenses, rotation, position, veo_length = read_veo(veo_path)
    fit = Fit(image, landmarks, veo_lenses)
    start = np.array(MAP_START) * [1, 2048 / size[0], 1, 1024 / size[1], size[1] / 1024, 1]   # andere Auflösung der Bildhälften
    hand_weight = 0.5 if by_hand else 0.05

    def hand(x):
        return np.linalg.norm(fit.landmark_residuals(x).reshape(-1, 2), axis=1)

    def first(length):
        return np.array([*rotation, *(position * length / veo_length), length, length * 0.6, *start, *start])

    # 1. Start nur aus den Handpunkten.
    if by_hand:
        x = fit.solve(first(92.0), free_parameters(), lines=False)
        x = fit.solve(x, free_parameters("offset"), lines=False)
    else:
        # Aus vier Ecken allein folgt kein Maßstab. Für jede angenommene Platzlänge wird die Kamera an die
        # Ecken angepasst; richtig ist die Länge, bei der die genormten Linien (Mittelkreis, Strafraum,
        # Torraum) im Bild dort liegen, wo das Modell sie erwartet.
        best = None
        for length in np.arange(80.0, 122.0, 2.0):
            free = free_parameters()
            free[6] = False
            x = fit.solve(first(length), free, lines=False)
            fit.retrace(x, 6)
            found = sum(len(v) for lens in LENSES for name, v in fit.traced[lens].items() if name not in BOUNDARY and name != "half" and not name.startswith("bar"))
            if best is None or found > best[0]:
                best = (found, x)
        x = best[1]
        print(f"Ohne Handpunkte: Start aus Veos vier Ecken, Platzlänge {x[6]:.0f} m passt am besten zu den genormten Linien", flush=True)
    print(f"Start: Fehler der Handpunkte Median {np.median(hand(x)):.1f} px, größter {hand(x).max():.1f} px; "
          f"Platz {x[6]:.1f} × {x[7]:.1f} m, Kamera {x[3]:.1f}/{x[4]:.1f}/{x[5]:.1f}", flush=True)

    # 2. Verfeinern an den verfolgten Linien; die Suchbreite schrumpft mit jedem Durchgang.
    for reach in (12, 8, 5, 4, 4) if by_hand else (16, 12, 8, 5, 4, 4):
        fit.retrace(x, reach)
        x = fit.solve(x, free_parameters("offset", "scale", "kink") if by_hand or reach < 16 else free_parameters("offset"), hand_weight=hand_weight)
        r = np.abs(np.concatenate(list(fit.line_residuals(x).values())))
        print(f"Suchbreite {reach:2d} px: {len(r)} Linienpunkte, Abweichung Median {np.median(r):.2f} px, 90 % unter {np.percentile(r, 90):.2f} px; "
              f"Platz {x[6]:.2f} × {x[7]:.2f} m, Kamera {x[3]:.2f}/{x[4]:.2f}/{x[5]:.2f}", flush=True)
    fit.retrace(x, 4)
    residuals = fit.line_residuals(x)
    r = np.abs(np.concatenate(list(residuals.values())))
    print(f"Handpunkte danach: Fehler Median {np.median(hand(x)):.1f} px, größter {hand(x).max():.1f} px", flush=True)
    expected = [name for name in model_lines(x[6], x[7]) if not name.startswith("bar")]
    missing = sorted(name for name in expected if not any(name in fit.traced[lens] for lens in LENSES))
    if missing or np.percentile(r, 90) > 2.0:
        print(f"ACHTUNG: Ergebnis prüfen. Nicht gefundene Linien: {', '.join(missing) or 'keine'}; 90 % der Linienpunkte liegen näher als {np.percentile(r, 90):.1f} px "
              "an ihrer Normlinie (gut ist rund 1 px). Kontrollbild ansehen und notfalls Handpunkte angeben.", flush=True)

    cam = fit.camera(x)
    result = {"pitch": {"length": float(x[6]), "width": float(x[7])}, "position": x[3:6].tolist(), "rotation": x[0:3].tolist(), "lensSize": fit.size,
              "model": "Welt -> Kamera: rotation (Drehvektor), position. Kamera -> Linse: R, t. Lochkamera K = fx, fy, cx, cy im Sensorbild mit "
                       "Verzeichnung dist = k1..k6: Faktor (1 + k1 r² + k2 r⁴ + k3 r⁶) / (1 + k4 r² + k5 r⁴ + k6 r⁶). "
                       "Sensor -> Bildhälfte: u = (us - map0) / map1, v = (vs - map2) / map3; unterhalb der Zeile map4 ist v um map5 gestaucht.",
              "lenses": {lens: {k: np.asarray(cam["lenses"][lens][k], float).tolist() for k in ("R", "t", "K", "dist", "map")} for lens in LENSES},
              "fit": {"start": "Handpunkte" if by_hand else "Veo-Ecken", "linesFound": len(expected) - len(missing), "linesExpected": len(expected), "lineMedianPx": float(np.median(r)), "lineP90Px": float(np.percentile(r, 90)),
                      "landmarkMedianPx": float(np.median(hand(x))), "landmarkMaxPx": float(hand(x).max())}}
    lines = model_lines(x[6], x[7], step=0.04)
    for lens in LENSES:
        cm = []
        for name, pts in fit.traced[lens].items():
            if name.startswith("bar"):
                continue
            ground, _ = to_ground(cam, lens, pts)
            keep = ~np.isnan(ground).any(axis=1)
            cm.append(cKDTree(lines[name][:, :2]).query(ground[keep])[0] * 100)
        cm = np.concatenate(cm)
        result["fit"][lens] = {"linePoints": int(len(cm)), "medianCm": float(np.median(cm)), "p90Cm": float(np.percentile(cm, 90))}
        print(f"{lens}: {len(cm)} Linienpunkte, am Boden im Mittel {np.median(cm):.0f} cm neben ihrer Normlinie, 90 % unter {np.percentile(cm, 90):.0f} cm")
    Path(out_path).write_text(json.dumps(result, indent=1))
    print(f"Platz {x[6]:.2f} × {x[7]:.2f} m -> {out_path}")

    if check:
        h = fit.size[1]
        for i, lens in enumerate(LENSES):
            for c in model_lines(x[6], x[7], step=0.25).values():
                uv = project(cam, lens, c)
                for a, b in zip(uv[:-1], uv[1:]):
                    if not np.isnan(a).any() and not np.isnan(b).any() and all(0 <= p[0] < fit.size[0] and 0 <= p[1] < h for p in (a, b)):
                        cv2.line(image, (int(round(a[0])), int(round(a[1])) + i * h), (int(round(b[0])), int(round(b[1])) + i * h), (255, 0, 255), 1, cv2.LINE_AA)
        cv2.imwrite(check, image)
        print(check)


if __name__ == "__main__":
    if len(sys.argv) not in (5, 6):
        sys.exit(__doc__)
    main(*sys.argv[1:])
