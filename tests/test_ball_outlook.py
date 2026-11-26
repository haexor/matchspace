import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import ball_outlook as bo
import ball_physics as bp

FPS = 30.0


def shot(p0, v, seconds):
    t = np.arange(int(seconds * FPS)) / FPS
    return np.array(p0) + t[:, None] * np.array(v) - 0.5 * bp.G * (t ** 2)[:, None] * np.array([0.0, 0.0, 1.0]), t


def track(pts):
    """Ballspur: Ruhe, Flug über pts, danach unbekannt."""
    xyz = np.full((len(pts) + 20, 3), np.nan)
    xyz[10:10 + len(pts)] = pts
    kind = np.zeros(len(xyz), np.uint8)
    kind[10:10 + len(pts)] = 2
    return xyz, kind


class ParabolaTest(unittest.TestCase):
    def test_fit_recovers_launch_and_speed(self):
        pts, t = shot([1.0, 2.0, 1.0], [10.0, -3.0, 6.0], 0.8)
        p0, v, err = bo.fit_parabola(t, pts)
        np.testing.assert_allclose(p0, [1.0, 2.0, 1.0], atol=1e-6)
        np.testing.assert_allclose(v, [10.0, -3.0, 6.0], atol=1e-6)
        self.assertLess(err, 1e-6)

    def test_goal_verdict(self):
        self.assertEqual(bo.goal_verdict(1.0, 1.0), "goal")
        self.assertEqual(bo.goal_verdict(1.0, 3.0), "high")
        self.assertEqual(bo.goal_verdict(5.0, 1.0), "wide")


class OutlookTest(unittest.TestCase):
    def test_shot_stopped_by_contact_would_have_scored(self):
        pts, _ = shot([30.0, 0.0, 1.0], [20.0, 2.0, 4.0], 0.3)     # nach 0,3 s abgefangen; ungestört wäre er bei x=45 nach 0,75 s im Tor
        xyz, kind = track(pts)
        (f,) = bo.outlook(xyz, kind, FPS)
        self.assertTrue(f["ended_in_air"])
        goal = f["continuation"]["goal_line"]
        self.assertEqual(goal["side"], 1)
        self.assertEqual(goal["verdict"], "goal")
        self.assertAlmostEqual(goal["y"], 1.5, delta=0.05)
        self.assertAlmostEqual(goal["z"], 1.24, delta=0.05)

    def test_shot_over_the_bar_and_wide(self):
        for v, verdict in (([20.0, 2.0, 8.0], "high"), ([20.0, 9.0, 4.0], "wide")):
            pts, _ = shot([30.0, 0.0, 1.0], v, 0.3)
            xyz, kind = track(pts)
            (f,) = bo.outlook(xyz, kind, FPS)
            self.assertEqual(f["continuation"]["goal_line"]["verdict"], verdict, v)

    def test_landed_flight_is_not_extended(self):
        pts, _ = shot([0.0, 0.0, 1.0], [5.0, 0.0, 3.0], 0.85)    # fällt wieder auf den Boden
        pts[-1, 2] = 0.11
        xyz, kind = track(pts)
        (f,) = bo.outlook(xyz, kind, FPS)
        self.assertFalse(f["ended_in_air"])
        self.assertIsNone(f["continuation"])

    def test_flight_away_from_goal_line_has_none(self):
        pts, _ = shot([0.0, 0.0, 1.0], [5.0, 0.0, 6.0], 0.3)
        xyz, kind = track(pts)
        (f,) = bo.outlook(xyz, kind, FPS)
        self.assertIsNone(f["continuation"]["goal_line"])
        self.assertIsNotNone(f["continuation"]["landing"])


class SpeedTest(unittest.TestCase):
    def test_flight_speed_is_three_dimensional(self):
        pts, _ = shot([0.0, 0.0, 1.0], [6.0, 0.0, 0.0], 0.5)       # waagerecht abgeworfen: 6 m/s, dazu kommt der Fall
        xyz, _ = track(pts)
        v = bo.speed_near(xyz, 10, FPS, after=True)
        self.assertGreater(v, 6.0)
        self.assertLess(v, 8.0)

    def test_too_few_positions_give_none(self):
        xyz = np.full((30, 3), np.nan)
        xyz[12] = [0, 0, 0]
        self.assertIsNone(bo.speed_near(xyz, 10, FPS, after=True))

    def test_before_and_after_use_their_own_side(self):
        xyz = np.full((40, 3), np.nan)
        t = np.arange(40) / FPS
        xyz[:20, 0] = 2.0 * t[:20]         # vor Bild 20: 2 m/s
        xyz[21:, 0] = 2.0 * t[20] + 10.0 * (t[21:] - t[20])   # danach: 10 m/s
        xyz[:, 1:] = np.where(np.isnan(xyz[:, :1]), np.nan, 0.0)
        self.assertAlmostEqual(bo.speed_near(xyz, 20, FPS, after=False), 2.0, places=1)
        self.assertAlmostEqual(bo.speed_near(xyz, 20, FPS, after=True), 10.0, places=1)


class ReliabilityTest(unittest.TestCase):
    def test_impossible_speed_gets_no_continuation(self):
        pts, _ = shot([0.0, 0.0, 1.0], [40.0, 0.0, 6.0], 0.2)
        xyz, kind = track(pts)
        (f,) = bo.outlook(xyz, kind, FPS)
        self.assertFalse(f["reliable"])
        self.assertIsNone(f["continuation"])

    def test_flight_far_outside_the_pitch_gets_no_continuation(self):
        pts, _ = shot([0.0, -40.0, 1.0], [3.0, 0.0, 6.0], 0.3)
        xyz, kind = track(pts)
        (f,) = bo.outlook(xyz, kind, FPS)
        self.assertFalse(f["reliable"])
        self.assertEqual(bo.throw_ins([f], kind), [])


class ThrowInTest(unittest.TestCase):
    def test_throw_from_the_touchline_in_hand_height(self):
        pts, _ = shot([10.0, -27.5, 1.9], [5.0, 4.0, 4.0], 0.7)
        xyz, kind = track(pts)
        events = bo.throw_ins(bo.outlook(xyz, kind, FPS), kind)
        self.assertEqual([e["kind"] for e in events], ["throw-in"])

    def test_kick_after_rolling_is_not_a_throw_in(self):
        pts, _ = shot([10.0, -27.5, 1.9], [5.0, 4.0, 4.0], 0.7)
        xyz, kind = track(pts)
        kind[7:10] = 1
        self.assertEqual(bo.throw_ins(bo.outlook(xyz, kind, FPS), kind), [])

    def test_flight_in_the_middle_is_not_a_throw_in(self):
        pts, _ = shot([0.0, 0.0, 1.9], [5.0, 4.0, 4.0], 0.7)
        xyz, kind = track(pts)
        self.assertEqual(bo.throw_ins(bo.outlook(xyz, kind, FPS), kind), [])


if __name__ == "__main__":
    unittest.main()
