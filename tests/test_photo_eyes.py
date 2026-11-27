"""Augen- und Ohrhöhe als Abbildungsebenen beim Übertragen der Fotos (looks_from_photo.py): Augen und Ohren des Fotos landen auf denen des Avatarnetzes; dunkle Flecken am Ohr."""
import unittest

import cv2
import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import looks_from_photo as lfp


def keypoints(eye_l, eye_r, conf_l=0.9, conf_r=0.9):
    kp = np.zeros((17, 2))
    conf = np.zeros(17)
    kp[1], kp[2] = eye_l, eye_r
    conf[1], conf[2] = conf_l, conf_r
    return kp, conf


class EyeLineTest(unittest.TestCase):
    def test_mean_of_both_eyes(self):
        kp, conf = keypoints((100, 200), (140, 210))
        v, u = lfp.eye_line(kp, conf, 0.5)
        self.assertAlmostEqual(v, 205.0)
        self.assertAlmostEqual(u, 120.0)

    def test_uncertain_eye_is_ignored(self):
        kp, conf = keypoints((100, 200), (140, 400), conf_r=0.1)
        v, u = lfp.eye_line(kp, conf, 0.5)
        self.assertAlmostEqual(v, 200.0)
        self.assertAlmostEqual(u, 100.0)

    def test_no_certain_eye_gives_none(self):
        kp, conf = keypoints((100, 200), (140, 210), conf_l=0.1, conf_r=0.2)
        self.assertIsNone(lfp.eye_line(kp, conf, 0.5))


class EarPointTest(unittest.TestCase):
    def test_uses_the_certain_ear_only(self):
        kp, conf = np.zeros((17, 2)), np.zeros(17)
        kp[3], kp[4] = (575, 164), (568, 149)
        conf[3], conf[4] = 0.98, 0.01
        self.assertEqual(lfp.ear_point(kp, conf, 0.4), (164.0, 575.0))

    def test_no_certain_ear_gives_none(self):
        self.assertIsNone(lfp.ear_point(np.zeros((17, 2)), np.zeros(17) + 0.1, 0.4))


class EarFleckTest(unittest.TestCase):
    def tile(self):
        tile = np.full((60, 60, 3), (90, 140, 200), np.uint8)       # Hautton
        tile[:, :12] = 10                                             # breite dunkle Fläche: Haar
        tile[20:40, 30:32] = 5                                        # dünner schwarzer Strich
        return tile

    def test_thin_dark_line_in_the_zone_is_removed_hair_stays(self):
        zone = np.zeros((60, 60), bool)
        zone[:, 12:] = True
        out = lfp.remove_ear_flecks(self.tile(), zone)
        self.assertGreater(int(out[30, 30].mean()), 80)
        self.assertLess(int(out[30, 5].mean()), 20)

    def test_outside_the_zone_nothing_changes(self):
        tile = self.tile()
        out = lfp.remove_ear_flecks(tile, np.zeros((60, 60), bool))
        self.assertTrue((out == tile).all())


class EarPaintTest(unittest.TestCase):
    def test_ear_texels_get_the_cheek_colour(self):
        tile = np.full((40, 40, 3), (20, 20, 20), np.uint8)        # dunkel: Haar rundherum
        tile[30:38, 5:15] = (90, 140, 200)                         # Wange
        ear = np.zeros((40, 40), bool)
        ear[10:20, 25:30] = True
        cheek = np.zeros((40, 40), bool)
        cheek[30:38, 5:15] = True
        out = lfp.paint_ear(tile, ear, cheek)
        self.assertEqual(tuple(out[15, 27]), (90, 140, 200))
        self.assertEqual(tuple(out[2, 2]), (20, 20, 20))

    def test_without_cheek_nothing_changes(self):
        tile = np.full((20, 20, 3), 30, np.uint8)
        ear = np.zeros((20, 20), bool)
        ear[5:9, 5:9] = True
        out = lfp.paint_ear(tile, ear, np.zeros((20, 20), bool))
        self.assertTrue((out == tile).all())


class ModelFaceTest(unittest.TestCase):
    def setUp(self):
        n = 30
        self.shape = (n, n)
        self.tile = np.full((n, n, 3), (10, 10, 10), np.uint8)
        # Texel: links die Vorderseite des Gesichts (z > 0, Mitte, Mundhöhe), rechts der Hinterkopf
        xs = np.tile(np.linspace(-0.04, 0.04, n), n)
        self.P = np.zeros((n * n, 3))
        self.P[:, 0] = xs
        self.P[:, 1] = 1.72      # über der Haarkante am Nacken (NECK_LOW) und unter der Stirn (FACE_TOP)
        self.P[:, 2] = 0.09
        self.P[(np.arange(n * n) // n) < 10, 2] = -0.08      # obere Zeilen: Hinterkopf
        self.ok = np.ones(n * n, bool)

    def test_front_gets_the_skin_colour_back_stays(self):
        skin = (90, 140, 200)
        out = lfp.model_face(self.tile, self.shape, self.P, self.ok, skin)
        self.assertTrue((np.abs(out[20, 15].astype(int) - np.array(skin)) < 6).all())
        self.assertLess(int(out[2, 15].mean()), 20)

    def test_lips_are_redder_than_the_skin(self):
        self.P[:, 1] = lfp.LIPS_Y
        out = lfp.model_face(self.tile, self.shape, self.P, self.ok, (90, 140, 200))
        mid = out[20, 15].astype(int)
        self.assertLess(mid[0], 90)
        self.assertLess(mid[1], 140)


class ModelNeckTest(unittest.TestCase):
    NECK = np.array([0.0, 1.53, -0.045])

    def tile_and_points(self, y):
        n = 40
        tile = np.full((n, n, 3), (30, 160, 20), np.uint8)       # Trikot
        P = np.zeros((n * n, 3))
        P[:, 0] = np.tile(np.linspace(-0.14, 0.14, n), n)          # x quer über Hals und Schulter
        P[:, 1] = y
        P[:, 2] = self.NECK[2]
        return tile, P, np.ones(n * n, bool)

    def test_above_the_neckline_is_skin_shoulder_stays_shirt(self):
        tile, P, ok = self.tile_and_points(self.NECK[1] + 0.05)      # 5 cm über dem Halsknochen: über dem Ausschnitt in der Mitte, seitlich (Schulterkante, x 14 cm) darunter
        out = lfp.model_neck(tile, P, (90, 140, 200), ok, self.NECK)
        self.assertTrue((np.abs(out[20, 20].astype(int) - np.array((90, 140, 200))) < 6).all())      # Mitte: Hals
        self.assertTrue((np.abs(out[20, 1].astype(int) - np.array((30, 160, 20))) < 4).all())        # Rand: Schulter bleibt Trikot

    def test_below_the_neckline_nothing_changes(self):
        tile, P, ok = self.tile_and_points(1.40)
        out = lfp.model_neck(tile, P, (90, 140, 200), ok, self.NECK)
        self.assertTrue((out == tile).all())


class ProjectionTest(unittest.TestCase):
    def fm(self, with_eyes):
        y = [1.45, 1.81]
        v = [300.0, 100.0]       # Schulter, Scheitel der Maske (Haarspitze)
        if with_eyes:
            y = [1.45, 1.699, 1.81]
            v = [300.0, 180.0, 100.0]     # Augen im Foto weiter oben als bei gerader Verbindung
        return {"y": np.array(y), "v": np.array(v), "u": np.full(len(y), 128.0), "sx": np.full(len(y), 500.0), "view": "vorn"}

    def test_eye_level_pins_photo_eyes_to_avatar_eyes(self):
        _, v = lfp.project(self.fm(True), np.array([[0.0, 1.699, 0.0]]))
        self.assertAlmostEqual(float(v[0]), 180.0)

    def test_without_eyes_the_row_is_interpolated(self):
        _, v = lfp.project(self.fm(False), np.array([[0.0, 1.699, 0.0]]))
        self.assertNotAlmostEqual(float(v[0]), 180.0, places=0)


if __name__ == "__main__":
    unittest.main()
