"""Körperhaltung aus dem Körpermodell (tools/veo_body.py) in unser 20-Gelenk-Skelett und in Weltrichtungen (Hilfsmodul).

veo_body.py liefert je Person und Bild 70 Punkte (MHR70) in den Kamerakoordinaten ihres Bildausschnitts: x nach rechts, y nach unten, z in Blickrichtung. Hier:
 1. Auswahl und Mittelung der Punkte auf unsere 20 Gelenke (to_skeleton),
 2. Drehung aus dem Ausschnitt in die Welt (camera_axes): Die Achsen des Ausschnitts sind die wirklichen Blickrichtungen durch den Mittelpunkt und
    die Nachbarpixel; so stimmt die Drehung auch bei der Linsenverzerrung am Bildrand,
 3. Knochenrichtungen (pose_limits.directions_of) für die bestehende Kette aus Glättung, Grenzen und Boden. Die Längen der Knochen und die Lage
    auf dem Platz kommen nicht vom Modell, sondern aus der gemessenen Körpergröße und der Bahn: Das Modell liefert nur, wie der Körper steht.
"""
import numpy as np

# MHR70-Indizes (sam_3d_body/metadata/mhr70.py)
NOSE, L_EAR, R_EAR, L_SHOULDER, R_SHOULDER, L_ELBOW, R_ELBOW, L_HIP, R_HIP = 0, 3, 4, 5, 6, 7, 8, 9, 10
L_KNEE, R_KNEE, L_ANKLE, R_ANKLE = 11, 12, 13, 14
L_BIG_TOE, L_SMALL_TOE, L_HEEL, R_BIG_TOE, R_SMALL_TOE, R_HEEL = 15, 16, 17, 18, 19, 20
R_WRIST, L_WRIST, NECK = 41, 62, 69
PIXEL_STEP = 8.0     # Pixel: Abstand der Nachbarpixel, aus denen die Achsen des Ausschnitts folgen


def unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


def to_skeleton(kp: np.ndarray, names: list) -> np.ndarray:
    """(n, 70, 3) -> (n, 20, 3) in der Reihenfolge von names (synth_poses.NAMES). Becken = Mitte der Hüften, Kopf = Mitte der Ohren,
    Zehe = Mitte von großer und kleiner Zehe."""
    kp = np.asarray(kp, float)
    pick = {
        "pelvis": (kp[:, L_HIP] + kp[:, R_HIP]) / 2, "neck": kp[:, NECK], "head": (kp[:, L_EAR] + kp[:, R_EAR]) / 2, "nose": kp[:, NOSE],
        "lShoulder": kp[:, L_SHOULDER], "rShoulder": kp[:, R_SHOULDER], "lElbow": kp[:, L_ELBOW], "rElbow": kp[:, R_ELBOW],
        "lWrist": kp[:, L_WRIST], "rWrist": kp[:, R_WRIST], "lHip": kp[:, L_HIP], "rHip": kp[:, R_HIP],
        "lKnee": kp[:, L_KNEE], "rKnee": kp[:, R_KNEE], "lAnkle": kp[:, L_ANKLE], "rAnkle": kp[:, R_ANKLE],
        "lHeel": kp[:, L_HEEL], "rHeel": kp[:, R_HEEL],
        "lToe": (kp[:, L_BIG_TOE] + kp[:, L_SMALL_TOE]) / 2, "rToe": (kp[:, R_BIG_TOE] + kp[:, R_SMALL_TOE]) / 2,
    }
    return np.stack([pick[n] for n in names], axis=1)


def camera_axes(centre_ray, right_ray, down_ray) -> np.ndarray:
    """Matrix (3, 3), deren Spalten die Achsen x (rechts), y (unten), z (Blick) des Ausschnitts in Weltkoordinaten sind. Aus den Blickrichtungen durch
    den Mittelpunkt des Ausschnitts und durch ein Pixel rechts und ein Pixel darunter."""
    z = unit(np.asarray(centre_ray, float))
    x = unit(right_ray - (right_ray @ z) * z)
    y = down_ray - (down_ray @ z) * z
    y = unit(y - (y @ x) * x)
    return np.stack([x, y, z], axis=1)


def world_joints(body: dict, entity_id: str, total: int, cam, rays, names: list, lens_names=("left", "right")) -> np.ndarray:
    """Gelenke (total, 20, 3) relativ zum Becken in Weltachsen (x, y Platz, z oben); NaN, wo keine Person gelesen wurde.
    body: Inhalt von veo_body.py mit zusätzlich ids (Spieler je Zeile nach Index); rays(cam, linse, pixel) -> Richtungen (veo_camera.rays)."""
    out = np.full((total, len(names), 3), np.nan)
    ids = list(body["ids"])
    rows = np.flatnonzero(np.array([ids[p] for p in body["player"]]) == entity_id) if len(body["player"]) else []
    for r in rows:
        f = int(body["frame"][r])
        if not 0 <= f < total:
            continue
        lens = lens_names[int(body["lens"][r])]
        x0, y0, x1, y1 = body["box"][r]
        c = np.array([(x0 + x1) / 2, (y0 + y1) / 2])
        d = rays(cam, lens, [c, c + [PIXEL_STEP, 0], c + [0, PIXEL_STEP]])
        R = camera_axes(d[0], d[1], d[2])
        joints = to_skeleton(body["kp3d"][r][None], names)[0]
        out[f] = (joints - joints[names.index("pelvis")]) @ R.T
    return out


MAX_SHIFT = 1.0      # m: so weit darf die Korrektur der Position höchstens gehen (darüber ist eher das Modell falsch als die Bahn)
SMOOTH_FRAMES = 5.0  # Bilder: Glättung der Korrektur (Gauß); das Pixelrauschen springt, der Fehler der Bahn im Zweikampf bleibt über Sekunden


HIP_HEIGHT = 0.85    # m: Höhe der Hüfte, in der die Bahn ins Bild gelegt wird (nur zur Zuordnung; ein paar Zentimeter spielen dort keine Rolle)
MIN_APART = 0.15     # Anteil der Boxhöhe: so nah dürfen die gelesenen Hüften zweier Personen im selben Bild nicht sein (dieselbe Person doppelt gefunden)
ASSIGN_GATE = 0.35   # Anteil der Boxhöhe: so weit darf eine gelesene Hüfte von der erwarteten Hüfte einer Bahn entfernt sein


def assign_rows(body: dict, tracks: dict, project, gate=ASSIGN_GATE, hip_height=HIP_HEIGHT) -> tuple:
    """Jede gelesene Person genau einer Bahn zuordnen, jede Bahn höchstens einer Person (ein Spieler existiert nur einmal).
    Das Modell liest jede Box für sich; steht der gesuchte Spieler fast ganz hinter einem anderen, findet es den anderen. Hier wird je Bild und
    Linse alles zusammen entschieden: Kosten = Abstand der gelesenen Hüfte zur erwarteten Hüfte der Bahn (Bahn auf Hüfthöhe ins Bild gelegt) in
    Boxhöhen; das Verfahren (Ungarisch) wählt die Zuordnung mit der kleinsten Summe, Paare über gate fallen weg. So wird eine vertauschte Person der
    richtigen Bahn zugeordnet, und eine doppelt gefundene bleibt bei der Bahn, die besser passt; die andere Bahn gilt in diesem Bild als verdeckt.
    Liegen zwei gelesene Hüften näher als MIN_APART Boxhöhen, ist es dieselbe Person: Es bleibt die, die besser zu ihrer Bahn passt; die andere Bahn
    gilt als verdeckt (auch wenn beide Bahnen nah beieinander liegen und jede für sich zur Hüfte passen würde).
    tracks: {Kennung: (total, 2) Bodenpunkt}; project(linse, (n, 3) Punkte der Welt) -> (n, 2) Pixel der Linse.
    Rückgabe: (body mit neuem player je Zeile ohne die nicht zugeordneten, Zahl umgehängter Zeilen, Zahl aussortierter Zeilen)."""
    from scipy.optimize import linear_sum_assignment
    n = len(body["player"])
    if not n:
        return body, 0, 0
    ids = list(body["ids"])
    index = {i: k for k, i in enumerate(ids)}
    hip = (body["kp2d"][:, L_HIP] + body["kp2d"][:, R_HIP]) / 2
    box = body["box"]
    height = np.maximum(box[:, 3] - box[:, 1], 1.0)
    keep, player, best = np.zeros(n, bool), body["player"].copy(), np.full(n, np.inf)
    key = body["frame"] * 2 + body["lens"]
    for k in np.unique(key):
        rows = np.flatnonzero(key == k)
        f, lens = int(body["frame"][rows[0]]), int(body["lens"][rows[0]])
        names = [i for i in tracks if i in index and not np.isnan(tracks[i][f, 0])]
        if not names:
            continue
        expected = np.asarray(project(lens, np.array([[*tracks[i][f], hip_height] for i in names])), float)
        cost = np.linalg.norm(hip[rows][:, None, :] - expected[None, :, :], axis=2) / height[rows][:, None]
        for a, r in enumerate(rows):   # bei gleichem Abstand gewinnt die Bahn, deren Box es war
            if ids[body["player"][r]] in names:
                cost[a, names.index(ids[body["player"][r]])] -= 0.02
        cost = np.where(np.isnan(cost), 1e6, cost)
        for a, b in zip(*linear_sum_assignment(np.minimum(cost, 1e3))):
            if cost[a, b] <= gate:
                keep[rows[a]] = True
                player[rows[a]] = index[names[b]]
                best[rows[a]] = cost[a, b]
        for i in rows:   # dieselbe Person doppelt: die schlechter passende fällt weg
            for j in rows:
                if i < j and keep[i] and keep[j] and np.linalg.norm(hip[i] - hip[j]) < MIN_APART * min(height[i], height[j]):
                    keep[i if best[i] > best[j] else j] = False
    moved = int((keep & (player != body["player"])).sum())
    out = {key_: (v[keep] if isinstance(v, np.ndarray) and len(v) == n else v) for key_, v in body.items()}
    out["player"] = player[keep]
    return out, moved, int(n - keep.sum())


def fill_gaps(directions: np.ndarray, present: np.ndarray, max_gap: int) -> tuple:
    """Knochenrichtungen (T, 20, 3) mit NaN in den Bildern ohne gelesene Haltung: Lücken bis max_gap Bilder zwischen zwei gelesenen Bildern
    (verdeckter Spieler, der sich nicht in Luft auflöst) werden zwischen den Nachbarn überbrückt (Richtungen gemischt und normiert), solange
    der Spieler da ist (present). Davor und danach wird nichts erfunden. Rückgabe: (Richtungen, Maske der überbrückten Bilder)."""
    out = directions.copy()
    seen = ~np.isnan(directions[:, 1, 0])
    filled = np.zeros(len(directions), bool)
    idx = np.flatnonzero(seen)
    for a, b in zip(idx[:-1], idx[1:]):
        if b - a < 2 or b - a - 1 > max_gap:
            continue
        for t in range(a + 1, b):
            if not present[t]:
                continue
            w = (t - a) / (b - a)
            mix = (1 - w) * directions[a] + w * directions[b]
            norm = np.linalg.norm(mix, axis=-1, keepdims=True)
            out[t] = np.where(norm > 1e-6, mix / np.maximum(norm, 1e-12), directions[a])
            filled[t] = True
    return out, filled


GROUND_Z = 0.12      # m: Fußpunkte unter dieser Höhe stehen auf dem Rasen; nur sie legen die Tiefe fest (ihre Höhe ist bekannt)
FOOT_POINTS = (("lAnkle", (L_ANKLE,)), ("rAnkle", (R_ANKLE,)), ("lHeel", (L_HEEL,)), ("rHeel", (R_HEEL,)),
               ("lToe", (L_BIG_TOE, L_SMALL_TOE)), ("rToe", (R_BIG_TOE, R_SMALL_TOE)))


def position_from_feet(body: dict, entity_id: str, total: int, cam, rays, joints: np.ndarray, names: list, lens_names=("left", "right")) -> np.ndarray:
    """Bodenpunkt des Spielers (total, 2) aus seinen Füßen im Bild: Für jeden Fußpunkt (Knöchel, Ferse, Zehe), der nach der Haltung auf dem Rasen steht
    (Höhe unter GROUND_Z), trifft der Sehstrahl durch den Bildpunkt des Modells die Ebene in dieser Höhe; abzüglich des Versatzes des Punkts zum Bodenpunkt
    (joints (total, 20, 3): Gelenke relativ zum Bodenpunkt, Höhe absolut) ergibt das den Bodenpunkt, gemittelt über die Fußpunkte. Die Höhe eines Fußes am
    Boden ist auf einen Zentimeter bekannt; beim Becken (Höhe nur auf Zentimeter genau) würde dieselbe Rechnung die Tiefe um Dezimeter verschieben,
    weil die Kamera flach auf den Platz sieht. NaN, wo keine Person gelesen wurde oder kein Fuß am Boden stand."""
    out = np.full((total, 2), np.nan)
    ids = list(body["ids"])
    rows = np.flatnonzero(np.array([ids[p] for p in body["player"]]) == entity_id) if len(body["player"]) else []
    index = {n: i for i, n in enumerate(names)}
    for r in rows:
        f = int(body["frame"][r])
        if not 0 <= f < total or np.isnan(joints[f, 0, 0]):
            continue
        name = lens_names[int(body["lens"][r])]
        eye = np.asarray(cam["lenses"][name]["centre"], float)
        votes = []
        for joint, picks in FOOT_POINTS:
            rel = joints[f, index[joint]]
            if rel[2] > GROUND_Z:
                continue
            d = rays(cam, name, [body["kp2d"][r][list(picks)].mean(axis=0)])[0]
            if d[2] >= -1e-6:
                continue
            t = (rel[2] - eye[2]) / d[2]
            votes.append(eye[:2] + t * d[:2] - rel[:2])
        if votes:
            out[f] = np.mean(votes, axis=0)
    return out


def refine_position(pos: np.ndarray, seen: np.ndarray, use: np.ndarray, max_shift=MAX_SHIFT, sigma=SMOOTH_FRAMES) -> np.ndarray:
    """Bahn pos (total, 2) um den geglätteten Unterschied zu den im Bild gesehenen Beckenpunkten seen korrigieren, in den Bildern use.
    Nur der langsame Teil des Unterschieds geht ein (Pixelrauschen in der Tiefe wäre sonst Zittern); er wird auf max_shift begrenzt.
    Lücken im Unterschied werden von den Nachbarn überbrückt."""
    from scipy.ndimage import gaussian_filter1d
    diff = seen - pos
    ok = use & ~np.isnan(diff[:, 0]) & ~np.isnan(pos[:, 0])
    out = pos.copy()
    if ok.sum() < 3:
        return out
    idx = np.arange(len(pos))
    filled = np.column_stack([np.interp(idx, idx[ok], diff[ok, k]) for k in range(2)])
    smooth = gaussian_filter1d(filled, sigma, axis=0, mode="nearest")
    norm = np.linalg.norm(smooth, axis=1, keepdims=True)
    smooth = smooth * np.minimum(1.0, max_shift / np.maximum(norm, 1e-9))
    span = np.zeros(len(pos), bool)
    span[idx[ok].min(): idx[ok].max() + 1] = True        # nur zwischen dem ersten und letzten gesehenen Bild, nicht davor und dahinter erfinden
    use_frames = use & span & ~np.isnan(pos[:, 0])
    out[use_frames] += smooth[use_frames]
    return out
