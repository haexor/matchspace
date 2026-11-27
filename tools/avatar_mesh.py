"""Das Körpernetz des Viewers je Bild: Oberfläche an den Texeln der Videotextur (Teil von tools/veo_looks.py, Daten aus tools/avatar_bake.py).

Der Viewer zeichnet jeden Spieler mit einem festen Netz, dessen Punkte feste Texturkoordinaten haben (web/avatar-look.js: Körperteil, Polarwinkel um
die Achse, Lage t entlang der Achse). Hier wird dieselbe Abbildung rückwärts gerechnet: zu jedem Texel der Kachel das Dreieck des Netzes, das dort
liegt (einmal, in der Grundhaltung), und daraus je Bild die Weltposition und Normale dieses Texels mit den Knochenmatrizen des Viewers (Hautgewichte).
"""
import pickle

import numpy as np


def matrix(elements):
    """THREE.Matrix4.elements (spaltenweise) -> 4 × 4."""
    return np.asarray(elements, float).reshape(4, 4).T


class AvatarMesh:
    def __init__(self, path, segments, tile):
        data = pickle.load(open(path, "rb"))
        st = data["static"]
        self.frames = data["frames"]
        self.rest = st["position"].reshape(-1, 3).astype(float)
        self.rest_n = st["normal"].reshape(-1, 3).astype(float)
        self.skin_i = st["skinIndex"].reshape(-1, 4).astype(int)
        self.skin_w = st["skinWeight"].reshape(-1, 4).astype(float)
        self.look = st["look"].reshape(-1, 4).astype(float)
        self.wear = np.asarray(st["wear"], float).reshape(-1, 4) if st.get("wear") is not None else None      # Kleidungsfelder je Punkt (Meter, positiv = bedeckt): Trikot, Hose, Stutzen, Schuh
        self.faces = st["index"].reshape(-1, 3).astype(int)
        self.nbones = len(st["bones"])
        self.bone_names = list(st["bones"])
        self.bind = matrix(st["bind"]) if "bind" in st else None
        self.bone_inverses = np.asarray(st["boneInverses"], float).reshape(-1, 4, 4).transpose(0, 2, 1) if "boneInverses" in st else None
        self.tile = tile
        self.to_world = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])   # Viewer (y oben) -> Welt der Szenendaten (z oben, gemessen)
        self._map(segments)

    def _map(self, segments):
        """Je Texel der Kachel: Dreieck (3 Netzpunkte) und Schwerpunktkoordinaten; -1 = kein Netz dort."""
        T = self.tile
        self.tri = np.full((T * T, 3), -1, int)
        self.bary = np.zeros((T * T, 3))
        look = self.look
        angle = np.arctan2(look[:, 1], look[:, 0])
        part = look[:, 3].astype(int)
        for s, (_, (x, y, w, h), (t0, t1), _) in enumerate(segments):
            faces = self.faces[(part[self.faces] == s).all(axis=1)]
            for face in faces:
                a, t = angle[face].copy(), look[face, 2]
                shifts = (0.0,)
                if a.max() - a.min() > np.pi:   # Dreieck über die Naht bei ±180°: negative Winkel um 360° nach oben
                    a = np.where(a < 0, a + 2 * np.pi, a)
                    shifts = (0.0, 2 * np.pi)
                # Texelmitten im Rechteck des Dreiecks
                u0, u1 = (a.min() + np.pi) / (2 * np.pi) * w, (a.max() + np.pi) / (2 * np.pi) * w
                v0, v1 = (t.min() - t0) / (t1 - t0) * h, (t.max() - t0) / (t1 - t0) * h
                cols = np.arange(int(np.floor(u0 - 0.5)), int(np.ceil(u1 - 0.5)) + 1)
                rows = np.arange(int(np.floor(v0 - 0.5)), int(np.ceil(v1 - 0.5)) + 1)
                if not len(cols) or not len(rows):
                    continue
                cc, rr = np.meshgrid(cols, rows)
                cc, rr = cc.ravel(), rr.ravel()
                ta = (cc + 0.5) / w * 2 * np.pi - np.pi
                tt = t0 + (rr + 0.5) / h * (t1 - t0)
                # Texel in der Spalte außerhalb 0..w-1 gehört zur anderen Seite der Naht
                col_in = cc % w
                inside_rows = (rr >= 0) & (rr < h)
                for shift in shifts:
                    pa = ta + shift
                    # Schwerpunktkoordinaten in (Winkel, t)
                    d = (a[1] - a[0]) * (t[2] - t[0]) - (a[2] - a[0]) * (t[1] - t[0])
                    if abs(d) < 1e-12:
                        continue
                    l1 = ((pa - a[0]) * (t[2] - t[0]) - (a[2] - a[0]) * (tt - t[0])) / d
                    l2 = ((a[1] - a[0]) * (tt - t[0]) - (pa - a[0]) * (t[1] - t[0])) / d
                    l0 = 1 - l1 - l2
                    ok = (l0 >= -1e-9) & (l1 >= -1e-9) & (l2 >= -1e-9) & inside_rows
                    for k in np.flatnonzero(ok):
                        at = (y + rr[k]) * T + x + col_in[k]
                        if self.tri[at, 0] < 0:
                            self.tri[at] = face
                            self.bary[at] = (l0[k], l1[k], l2[k])
        self.covered = self.tri[:, 0] >= 0

    def posed(self, f, entity):
        """Netzpunkte (V, 3) und Normalen im Bild f für die Figur `entity`, in der Welt der Szenendaten; None, wenn die Figur dort nicht gezeichnet wird."""
        fr = self.frames.get(f)
        if fr is None or entity not in fr:
            return None
        d = fr[entity]
        mw, bind, bind_inv = matrix(d["mw"]), matrix(d["bind"]), matrix(d["bindInv"])
        bones = d["bones"][: self.nbones * 16].reshape(self.nbones, 4, 4).transpose(0, 2, 1)
        v = np.concatenate([self.rest, np.ones((len(self.rest), 1))], axis=1) @ bind.T   # (V, 4)
        skinned = np.zeros_like(v)
        n = self.rest_n @ bind[:3, :3].T
        skinned_n = np.zeros_like(n)
        for k in range(4):
            m = bones[self.skin_i[:, k]]               # (V, 4, 4)
            w = self.skin_w[:, k][:, None]
            skinned += w * np.einsum("vij,vj->vi", m, v)
            skinned_n += w * np.einsum("vij,vj->vi", m[:, :3, :3], n)
        world = (skinned @ bind_inv.T @ mw.T)[:, :3]
        normal = skinned_n @ (mw @ bind_inv)[:3, :3].T
        normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-9)
        return world @ self.to_world.T, normal @ self.to_world.T

    def points(self, f, entity, index):
        """Weltpunkte und Normalen (len(index), 3) an den Texeln `index` (Kachelnummern); NaN, wo das Netz keinen Texel hat oder die Figur fehlt."""
        out = self.posed(f, entity)
        if out is None:
            return None
        pos, nor = out
        tri, bary = self.tri[index], self.bary[index]
        ok = tri[:, 0] >= 0
        safe = np.where(ok[:, None], tri, 0)
        p = (pos[safe] * bary[..., None]).sum(axis=1)
        n = (nor[safe] * bary[..., None]).sum(axis=1)
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
        p[~ok] = np.nan
        n[~ok] = np.nan
        return p, n

    def texel_wear(self, index):
        """Kleidungsfelder (Trikot, Hose, Stutzen, Schuh; Meter, positiv = bedeckt) an den Texeln `index`; NaN, wo das Netz keinen Texel hat; None ohne Daten im Netz."""
        if self.wear is None:
            return None
        tri, bary = self.tri[index], self.bary[index]
        ok = tri[:, 0] >= 0
        out = (self.wear[np.where(ok[:, None], tri, 0)] * bary[..., None]).sum(axis=1)
        out[~ok] = np.nan
        return out

    def joints(self):
        """Gelenke der Grundhaltung (Meter, Welt der Bindung: y oben, +z vorn, links = +x) nach Knochenname."""
        return {n: np.linalg.inv(self.bone_inverses[i])[:3, 3] for i, n in enumerate(self.bone_names)}

    def rest_points(self, index):
        """Punkte und Normalen (len(index), 3) an den Texeln `index` in der Grundhaltung; NaN, wo das Netz keinen Texel hat."""
        world = (np.concatenate([self.rest, np.ones((len(self.rest), 1))], axis=1) @ self.bind.T)[:, :3]
        normal = self.rest_n @ self.bind[:3, :3].T
        tri, bary = self.tri[index], self.bary[index]
        ok = tri[:, 0] >= 0
        safe = np.where(ok[:, None], tri, 0)
        p = (world[safe] * bary[..., None]).sum(axis=1)
        n = (normal[safe] * bary[..., None]).sum(axis=1)
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
        p[~ok] = np.nan
        n[~ok] = np.nan
        return p, n
