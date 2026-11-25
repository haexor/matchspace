import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import body_contact as bc


def pair(distance, frames=20):
    xy = np.zeros((frames, 2, 2))
    xy[:, 1, 0] = distance
    return xy


class KeepApartTest(unittest.TestCase):
    def test_far_apart_players_are_untouched(self):
        xy = pair(1.0)
        before = xy.copy()
        frames, biggest = bc.keep_apart(xy, [0, 1])
        np.testing.assert_array_equal(xy, before)
        self.assertEqual((frames, biggest), (0, 0.0))

    def test_close_pair_is_pushed_apart_symmetrically_to_the_minimum(self):
        xy = pair(0.1)
        bc.keep_apart(xy, [0, 1], sigma=0.01)
        d = np.linalg.norm(xy[:, 1] - xy[:, 0], axis=1)
        self.assertGreaterEqual(float(d.min()), bc.MIN_DISTANCE - 1e-6)
        self.assertAlmostEqual(float(xy[5, 0, 0]), -0.1, places=6)           # beide geben gleich viel nach
        self.assertAlmostEqual(float(xy[5, 1, 0]), 0.2, places=6)

    def test_players_at_exactly_the_same_spot_are_separated(self):
        xy = pair(0.0)
        bc.keep_apart(xy, [0, 1], sigma=0.01)
        self.assertGreaterEqual(float(np.linalg.norm(xy[:, 1] - xy[:, 0], axis=1).min()), bc.MIN_DISTANCE - 1e-6)

    def test_only_the_close_frames_change_and_the_correction_is_smooth(self):
        xy = pair(1.0, frames=60)
        xy[:, 1, 0] = np.interp(np.arange(60), [0, 20, 30, 40, 59], [1.0, 0.1, 0.1, 0.1, 1.0])   # Annäherung, Kontakt, Trennung
        before = xy.copy()
        bc.keep_apart(xy, [0, 1])
        correction = xy[:, 1, 0] - before[:, 1, 0]
        self.assertLess(float(np.abs(correction[:5]).max()), 1e-3)            # weit weg: praktisch unberührt
        self.assertLess(float(np.abs(np.diff(correction)).max()), 0.1)         # die Korrektur springt nicht
        self.assertGreaterEqual(float(np.linalg.norm(xy[25:35, 1] - xy[25:35, 0], axis=1).min()), bc.MIN_DISTANCE - 1e-6)

    def test_missing_players_are_ignored(self):
        xy = pair(0.1)
        xy[:, 1] = np.nan
        frames, _ = bc.keep_apart(xy, [0, 1])
        self.assertEqual(frames, 0)
        self.assertTrue(np.isnan(xy[:, 1]).all())

    def test_three_in_a_row_all_end_up_apart(self):
        xy = np.zeros((10, 3, 2))
        xy[:, 1, 0], xy[:, 2, 0] = 0.1, 0.2
        bc.keep_apart(xy, [0, 1, 2], sigma=0.01)
        for a, b in ((0, 1), (1, 2), (0, 2)):
            self.assertGreaterEqual(float(np.linalg.norm(xy[:, b] - xy[:, a], axis=1).min()), bc.MIN_DISTANCE - 0.02)


if __name__ == "__main__":
    unittest.main()
