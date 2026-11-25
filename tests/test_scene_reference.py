import unittest

import numpy as np

from tests import helpers  # noqa: F401
import scene_reference as ref


class FakeCam:
    pass


class RegionTest(unittest.TestCase):
    def setUp(self):
        # Kamera ersetzt: Weltpunkt (x, y, z) -> linke Linse, Pixel (100 * x + 1000, 500 - 100 * z - 10 * y)
        self._project = ref.veo_camera.project
        ref.veo_camera.project = lambda cam, lens, pts: np.array(
            [[100 * p[0] + 1000, 500 - 100 * p[2] - 10 * p[1]] if lens == "left" else [np.nan, np.nan] for p in pts])

    def tearDown(self):
        ref.veo_camera.project = self._project

    def test_covers_all_points_with_16_by_9(self):
        tracks = np.full((20, 2, 3), np.nan)
        tracks[:, 0] = (-3.0, 0.0, 0.0)
        tracks[:, 1] = (3.0, 0.0, 0.0)
        lens, x0, y0, w, h = ref.region({}, tracks, None, 50)
        self.assertEqual(lens, 0)
        self.assertAlmostEqual(w / h, 16 / 9, delta=0.02)
        self.assertLessEqual(x0, 700 - 50)
        self.assertGreaterEqual(x0 + w, 1300 + 50)
        self.assertLessEqual(y0, 300)
        self.assertGreaterEqual(y0 + h, 500)

    def test_stays_inside_lens(self):
        tracks = np.full((5, 1, 3), np.nan)
        tracks[:, 0] = (-9.5, 0.0, 0.0)
        lens, x0, y0, w, h = ref.region({}, tracks, None, 400)
        self.assertGreaterEqual(x0, 0)
        self.assertGreaterEqual(y0, 0)
        self.assertLessEqual(x0 + w, ref.LENS_W)
        self.assertLessEqual(y0 + h, ref.LENS_H)


if __name__ == "__main__":
    unittest.main()
