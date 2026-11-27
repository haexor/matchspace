"""Augenhöhe als Abbildungsebene beim Übertragen der Fotos (looks_from_photo.py): Augen und Ohren des Fotos landen auf denen des Avatarnetzes."""
import unittest

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
