import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import scene_quality as sq




class QualityTest(unittest.TestCase):
    def test_ball_jumps_counts_impossible_steps(self):
        xy = np.zeros((6, 2, 2))
        xy[:, 1] = [[0, 0], [0.4, 0], [0.8, 0], [30.0, 0], [30.4, 0], [30.8, 0]]    # 29 m in einem Bild bei 25 Hz
        self.assertEqual(sq.ball_jumps(xy, 1, 25.0), 1)

    def test_missing_ball_is_not_a_jump(self):
        xy = np.zeros((4, 2, 2))
        xy[:, 1] = [[0, 0], [np.nan, np.nan], [50.0, 0], [50.1, 0]]
        self.assertEqual(sq.ball_jumps(xy, 1, 25.0), 0)

    def test_near_needs_height_and_no_jumps(self):
        class Cam:
            pass
        meta = {"entities": [{"kind": "player"}, {"kind": "ball"}], "fps": 25}
        xy = np.zeros((10, 2, 2))
        orig = sq.pixel_height
        try:
            sq.pixel_height = lambda cam, p: 120.0
            self.assertTrue(sq.quality(meta, xy, Cam())["ok"])
            sq.pixel_height = lambda cam, p: 50.0
            q = sq.quality(meta, xy, Cam())
            self.assertFalse(q["near"])
            self.assertFalse(q["ok"])
            sq.pixel_height = lambda cam, p: 120.0
            xy[5:, 1] = [60.0, 0]
            q = sq.quality(meta, xy, Cam())
            self.assertTrue(q["near"])
            self.assertFalse(q["ok"])
        finally:
            sq.pixel_height = orig

    def test_player_far_from_ball_is_not_measured(self):
        meta = {"entities": [{"kind": "player"}, {"kind": "ball"}], "fps": 25}
        xy = np.zeros((5, 2, 2))
        xy[:, 0] = [20.0, 0]
        orig = sq.pixel_height
        try:
            sq.pixel_height = lambda cam, p: 120.0
            self.assertIsNone(sq.quality(meta, xy, None)["leadHeightPx"])
        finally:
            sq.pixel_height = orig

    def test_no_ball_gives_no_ok(self):
        meta = {"entities": [{"kind": "player"}], "fps": 25}
        self.assertFalse(sq.quality(meta, np.zeros((3, 1, 2)), None)["ok"])


if __name__ == "__main__":
    unittest.main()
