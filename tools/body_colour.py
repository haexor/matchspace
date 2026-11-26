"""Trikotfarbe jeder Körperlesung: Welche Mannschaft zeigt die gelesene Person?

Das Körpermodell liest bei Zweikämpfen oft dieselbe Person doppelt (die vordere), und nach der Hüftlage allein kann sie der falschen Bahn zufallen: Der rote
und der grüne Spieler stehen im Bild fast übereinander. Die Farbe des Rumpfs entscheidet, wessen Haltung es ist. Gemessen wird das Mittel der Pixel im
Rumpf (Schultern bis Hüften, zur Mitte hin verkleinert, damit Arme und Hintergrund nicht eingehen), als Farbart (Anteile von Rot, Grün, Blau): unabhängig von der Helligkeit.
"""
import cv2
import numpy as np

L_SHOULDER, R_SHOULDER, L_HIP, R_HIP = 5, 6, 9, 10
VIDEO_FPS = 30000 / 1001
SHRINK = 0.6               # Anteil des Rumpfvierecks, der gemessen wird (zur Mitte hin)
MIN_AREA_PX = 12           # Pixel: kleiner ist der Rumpf zu klein für eine Farbe
MIN_BRIGHT = 120.0        # Summe von R, G, B, unter der ein Pixel (dunkler Ärmel, Schatten, Nummer) die Farbart verfälscht und nicht zählt
COLOUR_W = 1.0             # Gewicht der Farbart-Abweichung gegen den Abstand der Hüften (in Boxhöhen)
ISOLATION_M = 3.0          # m: so weit ist kein anderer Spieler weg, damit eine Lesung als eindeutig für die Referenzfarbe gilt
MIN_ROWS = 10              # eindeutige Lesungen, ab denen eine Bahn eine Referenzfarbe hat


def chroma(rgb: np.ndarray) -> np.ndarray:
    """Farbart: Anteile von Rot und Grün an der Summe (Blau ergibt sich); NaN bei schwarz."""
    rgb = np.asarray(rgb, float)
    s = rgb.sum(axis=-1, keepdims=True)
    return np.where(s > 1.0, rgb[..., :2] / np.maximum(s, 1.0), np.nan)


def torso_rgb(image: np.ndarray, kp: np.ndarray) -> np.ndarray:
    """Mittlere Farbe im verkleinerten Rumpfviereck der Gelenkpunkte kp (70, 2) im Bild; NaN, wenn es zu klein oder außerhalb ist."""
    quad = kp[[L_SHOULDER, R_SHOULDER, R_HIP, L_HIP]].astype(float)
    centre = quad.mean(axis=0)
    quad = centre + (quad - centre) * SHRINK
    mask = np.zeros(image.shape[:2], np.uint8)
    cv2.fillConvexPoly(mask, np.round(quad).astype(np.int32), 255)
    if int((mask > 0).sum()) < MIN_AREA_PX:
        return np.full(3, np.nan)
    px = image[mask > 0].reshape(-1, image.shape[2])[:, :3].astype(float)
    px = px[px.sum(axis=1) >= MIN_BRIGHT]
    return px.mean(axis=0) if len(px) >= MIN_AREA_PX // 2 else np.full(3, np.nan)


def torso_chroma(video: str, body: dict) -> np.ndarray:
    """Farbart (n, 2) des Rumpfs für jede Zeile der Körperlesung (body aus tools/veo_body.py); NaN, wo sie sich nicht messen lässt."""
    n = len(body["player"])
    out = np.full((n, 2), np.nan)
    cap = cv2.VideoCapture(str(video))
    ratio = VIDEO_FPS / 25
    for f in np.unique(body["frame"]):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(f * ratio)))
        ok, image = cap.read()
        if not ok:
            continue
        half = image.shape[0] // 2
        for r in np.flatnonzero(body["frame"] == f):
            li = int(body["lens"][r])
            lens = cv2.cvtColor(image[li * half:(li + 1) * half], cv2.COLOR_BGR2RGB)
            out[r] = chroma(torso_rgb(lens, body["kp2d"][r]))
    cap.release()
    return out


def team_of(name: str) -> str:
    return name.split("-")[0]


def references(body: dict, chromas: np.ndarray, tracks: dict, row_of: str = "row") -> dict:
    """Trikotfarbe je Mannschaft (Kennung vor dem Bindestrich: own, opponent, referee): Median der Farbart aller zugeordneten Lesungen, bei denen kein anderer
    Spieler näher als ISOLATION_M stand. Je Bahn streut die Farbe stark (Ärmel, Nummer, Schatten), je Mannschaft ist sie stabil, und nur der Unterschied
    zwischen den Mannschaften entscheidet. body: zugeordnete Lesungen (mit `row` = Zeile in chromas, `player` = Index in `ids`, `frame`);
    tracks: {Kennung: (total, 2)} in Metern. Mannschaften mit weniger als MIN_ROWS eindeutigen Lesungen fehlen."""
    ids = list(body["ids"])
    found = {}
    for k, name in enumerate(ids):
        for r in np.flatnonzero(body["player"] == k):
            f = int(body["frame"][r])
            c = chromas[body[row_of][r]]
            if np.isnan(c).any():
                continue
            others = [np.linalg.norm(tracks[o][f] - tracks[name][f]) for o in ids if o != name and not np.isnan(tracks[o][f, 0])]
            if not others or min(others) > ISOLATION_M:
                found.setdefault(team_of(name), []).append(c)
    return {t: np.median(np.array(v), axis=0) for t, v in found.items() if len(v) >= MIN_ROWS and t != "referee"}   # Schiedsrichter nicht als Gegenfarbe
