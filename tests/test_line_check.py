import unittest

import numpy as np
from scipy.spatial.transform import Rotation

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import line_check as lc
import veo_camera


def camera(height=8.0, back=40.0, tilt=12.0):
    """Lochkamera ohne Verzeichnung hinter der Seitenlinie (y = -back), Blick quer über den Platz, leicht nach unten."""
    a = np.radians(tilt)
    x_c = np.array([1.0, 0, 0])
    z_c = np.array([0, np.cos(a), -np.sin(a)])
    y_c = np.cross(z_c, x_c)
    to_camera = np.array([x_c, y_c, z_c])
    lens = {"R": np.eye(3).tolist(), "t": [0, 0, 0], "K": [1000, 1000, 1024, 512], "dist": [0] * 6,
            "map": [0, 1, 0, 1, 1e9, 1]}
    return veo_camera._prepare({"position": [0, -back, height], "rotation": Rotation.from_matrix(to_camera).as_rotvec().tolist(),
                                "pitch": {"length": 90.0, "width": 55.0}, "lenses": {"left": dict(lens), "right": dict(lens)}})


class LineTest(unittest.TestCase):
    def setUp(self):
        self.cam = camera()
        self.index = lc.line_index(self.cam, 90.0, 55.0)

    def test_ankle_on_projected_line_is_a_line_spot(self):
        truth = np.array([5.0, 27.5])              # ferne Seitenlinie
        uv = veo_camera.project(self.cam, "left", [[*truth, lc.ANKLE_HEIGHT]])[0]
        name, world, dist = lc.on_line(self.index, 0, uv)
        self.assertEqual(name, "touch+")
        self.assertLess(dist, lc.NEAR_PX)
        self.assertLess(np.linalg.norm(world - truth), 0.1)

    def test_ankle_beside_the_line_is_not(self):
        uv = veo_camera.project(self.cam, "left", [[5.0, 24.0, lc.ANKLE_HEIGHT]])[0]
        self.assertGreater(lc.on_line(self.index, 0, uv)[2], lc.NEAR_PX)

    def test_depth_and_across(self):
        eye = self.cam["position"][:2]
        truth = np.array([0.0, 27.5])
        depth, across = lc.depth_across(truth + [0, 0.8], truth, eye)
        self.assertAlmostEqual(depth, 0.8, places=6)
        self.assertAlmostEqual(across, 0.0, places=6)
        depth, across = lc.depth_across(truth + [0.3, 0], truth, eye)
        self.assertAlmostEqual(depth, 0.0, places=6)
        self.assertAlmostEqual(abs(across), 0.3, places=6)


class FilterTest(unittest.TestCase):
    def test_moving_foot_does_not_count(self):
        self.assertTrue(lc.still([100, 200], [100.5, 200.4], [101, 200]))
        self.assertFalse(lc.still([100, 200], [103, 200], [106, 200]))
        self.assertFalse(lc.still(None, [100, 200], [100, 200]))

    def test_line_must_be_bright_in_the_background(self):
        image = np.full((100, 100), 40.0)
        image[50, :] = 200.0                       # helle waagrechte Linie
        self.assertTrue(lc.visible(image, [30, 50]))
        self.assertFalse(lc.visible(image, [30, 20]))

    def test_at_most_three_spots_per_player_and_second(self):
        spots = [lc.LineSpot(f, 0, 0, "p", "touch+", np.zeros(2)) for f in range(30)]
        self.assertEqual(len(lc.thin(spots, fps=30)), 3)


class SummaryTest(unittest.TestCase):
    def test_median_and_spread_per_source(self):
        errs = [{"scene": (0.9 + d, 0.0), "box": (d, 0.1)} for d in (-0.2, 0.0, 0.2)]
        s = lc.summary(errs)
        self.assertAlmostEqual(s["scene"]["depthMedian"], 0.9)
        self.assertAlmostEqual(s["box"]["depthMedian"], 0.0)
        self.assertAlmostEqual(s["box"]["acrossMedian"], 0.1)
        self.assertEqual(s["scene"]["spots"], 3)


if __name__ == "__main__":
    unittest.main()
