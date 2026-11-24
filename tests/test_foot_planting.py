import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import foot_planting as fp
import pose_limits

FPS = 25


class ContactsTest(unittest.TestCase):
    def test_a_low_slow_ankle_is_a_standing_foot(self):
        n = 40
        ankle = np.zeros((n, 3))
        ankle[:, 0] = np.linspace(0, 8, n)                       # der Körper läuft mit 5 m/s ...
        ankle[:, 2] = 0.05                                       # ... der Fuß liegt tief
        body = ankle[:, :2].copy()
        ankle[:, 0] = 0.0                                        # ... und bleibt an derselben Stelle
        self.assertTrue(fp.contacts(ankle, body, FPS).all())

    def test_a_high_ankle_is_not_standing(self):
        n = 30
        ankle = np.zeros((n, 3))
        ankle[:, 2] = 0.4
        self.assertFalse(fp.contacts(ankle, np.zeros((n, 2)), FPS).any())

    def test_short_gaps_in_the_middle_of_standing_are_closed(self):
        n = 30
        ankle = np.zeros((n, 3))
        ankle[:, 2] = 0.05
        ankle[14, 2] = 0.12                                      # ein Bild leicht angehoben: über CONTACT_ON, unter CONTACT_OFF
        self.assertTrue(fp.contacts(ankle, np.zeros((n, 2)), FPS).all())


class BodyPaceTest(unittest.TestCase):
    def test_standing_is_slow_and_running_converges_to_the_speed(self):
        self.assertLess(fp.body_pace(np.zeros((60, 2)), FPS).max(), 0.01)
        x = np.arange(100) * 4.0 / FPS                           # 4 m/s
        pace = fp.body_pace(np.column_stack([x, np.zeros(100)]), FPS)
        self.assertAlmostEqual(pace[-1], 4.0, delta=0.3)

    def test_speed_is_capped_at_twelve_metres_per_second(self):
        x = np.arange(60) * 30.0 / FPS
        self.assertLessEqual(fp.body_pace(np.column_stack([x, np.zeros(60)]), FPS).max(), 12.0)


class StepPlanTest(unittest.TestCase):
    def test_feet_stay_put_while_the_body_stays_put(self):
        n = 50
        natural = {s: np.tile(np.array([[0.0, 0.1 if s == "l" else -0.1]]), (n, 1)) for s in "lr"}
        out = fp.step_plan(natural, FPS, np.ones(n, bool))
        for s in "lr":
            self.assertTrue(np.allclose(out[s][0], natural[s]))
            self.assertEqual(out[s][1].max(), 0.0)

    def test_a_body_that_drifts_away_makes_a_step_with_one_foot_at_a_time(self):
        n = 80
        drift = np.linspace(0, 0.6, n)[:, None] * np.array([[1.0, 0.0]])
        natural = {s: np.array([[0.0, 0.1 if s == "l" else -0.1]]) + drift for s in "lr"}
        out = fp.step_plan(natural, FPS, np.ones(n, bool))
        lifted = (out["l"][1] > 0).astype(int) + (out["r"][1] > 0).astype(int)
        self.assertGreater(lifted.max(), 0)                      # es wird gestiegen
        self.assertEqual(lifted.max(), 1)                        # nie mit beiden Füßen zugleich
        self.assertLessEqual(out["l"][1].max(), fp.STEP_LIFT + 1e-9)

    def test_frames_with_a_gait_are_left_alone(self):
        n = 30
        natural = {s: np.random.default_rng(0).normal(size=(n, 2)) for s in "lr"}
        out = fp.step_plan(natural, FPS, np.zeros(n, bool))
        for s in "lr":
            self.assertTrue(np.array_equal(out[s][0], natural[s]))


class LockIntervalsTest(unittest.TestCase):
    def test_a_steady_foot_needs_one_interval(self):
        out = []
        fp._lock_intervals(np.zeros((20, 2)), 0, 20, out)
        self.assertEqual(out, [(0, 20, 10)])

    def test_a_foot_that_creeps_is_split_so_that_each_part_stays_within_the_slip(self):
        xy = np.column_stack([np.linspace(0, 2.0, 40), np.zeros(40)])
        out = []
        fp._lock_intervals(xy, 0, 40, out)
        self.assertGreater(len(out), 1)
        for a, b, mid in out:
            self.assertLessEqual(np.linalg.norm(xy[a:b] - xy[mid], axis=1).max(), fp.MAX_SLIP + 1e-9)

    def test_too_short_stretches_are_dropped(self):
        out = []
        fp._lock_intervals(np.zeros((10, 2)), 0, fp.MIN_CONTACT - 1, out)
        self.assertEqual(out, [])


class RunsTest(unittest.TestCase):
    def test_runs_of_true_with_minimum_length(self):
        mask = np.array([0, 1, 1, 0, 1, 0, 0, 1, 1, 1], bool)
        self.assertEqual(pose_limits.runs(mask), [(1, 3), (4, 5), (7, 10)])
        self.assertEqual(pose_limits.runs(mask, 2), [(1, 3), (7, 10)])


if __name__ == "__main__":
    unittest.main()
