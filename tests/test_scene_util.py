import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import scene_util as su


class RunningMedianTest(unittest.TestCase):
    def test_removes_a_single_outlier(self):
        out = su.running_median(np.array([1.0, 1.0, 50.0, 1.0, 1.0]), 3)
        self.assertEqual(out.tolist(), [1.0, 1.0, 1.0, 1.0, 1.0])

    def test_ignores_gaps_inside_the_window(self):
        out = su.running_median(np.array([2.0, np.nan, 4.0]), 3)
        self.assertEqual(out[1], 3.0)

    def test_all_nan_stays_nan(self):
        self.assertTrue(np.isnan(su.running_median(np.full(4, np.nan), 3)).all())


class SegmentsTest(unittest.TestCase):
    def test_runs_of_true_with_minimum_length(self):
        mask = [0, 1, 1, 1, 0, 1, 0, 0, 1, 1]
        self.assertEqual(list(su.segments(mask, 1)), [(1, 4), (5, 6), (8, 10)])
        self.assertEqual(list(su.segments(mask, 2)), [(1, 4), (8, 10)])

    def test_run_at_the_end_is_closed(self):
        self.assertEqual(list(su.segments([False, True, True], 2)), [(1, 3)])

    def test_nothing_to_find(self):
        self.assertEqual(list(su.segments([False, False], 1)), [])
        self.assertEqual(list(su.segments([], 1)), [])


class HoldTest(unittest.TestCase):
    def test_fills_gaps_up_to_the_limit_with_the_nearest_valid_frame(self):
        out = su.hold(np.array([1.0, np.nan, np.nan, np.nan, np.nan, 9.0]), 2)
        self.assertEqual(out.tolist(), [1.0, 1.0, 1.0, 9.0, 9.0, 9.0])

    def test_a_gap_wider_than_twice_the_limit_stays_open_in_the_middle(self):
        out = su.hold(np.array([1.0, np.nan, np.nan, np.nan, 5.0]), 1)
        self.assertEqual((out[1], out[3]), (1.0, 5.0))
        self.assertTrue(np.isnan(out[2]))

    def test_without_any_valid_frame_nothing_changes(self):
        v = np.full((3, 2), np.nan)
        self.assertTrue(np.isnan(su.hold(v, 5)).all())

    def test_works_on_multi_dimensional_values(self):
        v = np.full((4, 3, 2), np.nan)
        v[0] = 7.0
        out = su.hold(v, 2)
        self.assertTrue((out[:3] == 7.0).all())
        self.assertTrue(np.isnan(out[3]).all())


class ResampleTest(unittest.TestCase):
    def test_interpolates_between_frames(self):
        out = su.resample(np.array([0.0, 10.0, 20.0]), 4, 0.5)
        self.assertEqual(out.tolist(), [0.0, 5.0, 10.0, 15.0])

    def test_a_missing_neighbour_makes_the_result_missing(self):
        out = su.resample(np.array([0.0, np.nan, 4.0]), 3, 1.0)
        self.assertTrue(np.isnan(out[0]) and np.isnan(out[1]))      # NaN bleibt NaN, auch am Rand eines Lochs
        self.assertEqual(out[2], 4.0)

    def test_clamps_at_the_end(self):
        self.assertEqual(su.resample(np.array([0.0, 10.0]), 4, 1.0).tolist(), [0.0, 10.0, 10.0, 10.0])

    def test_vectors_keep_their_shape(self):
        self.assertEqual(su.resample(np.zeros((5, 2)), 7, 0.5).shape, (7, 2))


class ResampleKeypointsTest(unittest.TestCase):
    def points(self, *xs):
        kp = np.zeros((len(xs), 17, 3))
        kp[:, :, 0] = np.array(xs)[:, None]
        kp[:, :, 2] = 1.0
        return kp

    def test_same_lens_is_averaged(self):
        kp, lens = su.resample_keypoints(self.points(0.0, 10.0), np.array([0.0, 0.0]), 3, 0.5)
        self.assertEqual(kp[1, 0, 0], 5.0)
        self.assertEqual(lens.tolist(), [0.0, 0.0, 0.0])

    def test_different_lenses_are_not_mixed(self):
        kp, lens = su.resample_keypoints(self.points(0.0, 10.0), np.array([0.0, 1.0]), 3, 0.5)
        self.assertIn(kp[1, 0, 0], (0.0, 10.0))
        self.assertIn(lens[1], (0.0, 1.0))

    def test_missing_frames_stay_missing(self):
        kp = self.points(0.0, 10.0)
        kp[:] = np.nan
        out, lens = su.resample_keypoints(kp, np.array([np.nan, np.nan]), 2, 1.0)
        self.assertTrue(np.isnan(out).all() and np.isnan(lens).all())


if __name__ == "__main__":
    unittest.main()
