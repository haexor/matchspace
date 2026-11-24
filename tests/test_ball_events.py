import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import ball_events as be

FPS = 30.0


def simulate(kicks, n, start=(0.0, 0.0), decel=1.0):
    """Ball mit Reibung; kicks: {Bild: neue Geschwindigkeit (vx, vy) in m/s}. Rückgabe Lagen (n, 2)."""
    pos = np.zeros((n, 2))
    p, v = np.array(start, float), np.zeros(2)
    for f in range(n):
        if f in kicks:
            v = np.array(kicks[f], float)
        pos[f] = p
        speed = np.linalg.norm(v)
        if speed > 0:
            v = v * max(0.0, speed - decel / FPS) / speed
        p = p + v / FPS
    return pos


class FitSideTest(unittest.TestCase):
    def test_recovers_velocity(self):
        t = np.arange(10) / FPS
        p = np.column_stack([2.0 + 3.0 * t, 1.0 - 1.0 * t])
        pos, vel, sigma = be.fit_side(t, p, t[5])
        np.testing.assert_allclose(vel, [3.0, -1.0], atol=1e-9)
        self.assertGreater(sigma, 0)

    def test_too_few_points(self):
        self.assertIsNone(be.fit_side(np.array([0.0, 0.1]), np.zeros((2, 2)), 0.0))


class ContactsTest(unittest.TestCase):
    def test_finds_kicks_at_their_frames(self):
        pos = simulate({10: (8.0, 0.0), 50: (0.0, 5.0), 90: (-9.0, 3.0)}, 140)
        got = be.find_contacts(pos, FPS)
        self.assertEqual([c.frame for c in got], [10, 50, 90][:len(got)])
        for c, f in zip(got, [10, 50, 90]):
            self.assertLessEqual(abs(c.frame - f), 1)
        self.assertEqual(len(got), 3)

    def test_smooth_roll_has_no_contacts(self):
        pos = simulate({5: (9.0, 2.0)}, 120)
        got = be.find_contacts(pos, FPS)
        self.assertEqual(len(got), 1)

    def test_resting_ball_has_no_contacts(self):
        self.assertEqual(be.find_contacts(np.zeros((90, 2)), FPS), [])

    def test_noise_does_not_create_contacts(self):
        rng = np.random.default_rng(0)
        pos = simulate({5: (8.0, 0.0)}, 120) + rng.normal(0, 0.03, (120, 2))
        got = be.find_contacts(pos, FPS)
        self.assertEqual(len(got), 1)

    def test_dm_noise_of_real_tracks_does_not_create_contacts(self):
        rng = np.random.default_rng(1)
        pos = simulate({5: (8.0, 0.0)}, 150) + rng.normal(0, 0.1, (150, 2))
        self.assertEqual(len(be.find_contacts(pos, FPS)), 1)

    def test_gap_without_ball_keeps_surrounding_contacts(self):
        pos = simulate({10: (8.0, 0.0), 60: (0.0, 6.0)}, 110)
        pos[25:40] = np.nan
        got = be.find_contacts(pos, FPS)
        self.assertEqual(len(got), 2)

    def test_one_sided_track_gives_no_contact(self):
        pos = simulate({10: (8.0, 0.0)}, 60)
        pos[:10] = np.nan                               # vor dem Kontakt nichts gesehen
        self.assertEqual(be.find_contacts(pos, FPS), [])

    def test_two_kicks_closer_than_gap_are_one_event(self):
        pos = simulate({20: (8.0, 0.0), 22: (8.0, 2.0)}, 80)
        self.assertLessEqual(len(be.find_contacts(pos, FPS)), 1)


class KindTest(unittest.TestCase):
    def test_kinds_by_speed(self):
        self.assertEqual(be.classify(3.0), "touch")
        self.assertEqual(be.classify(10.0), "pass")
        self.assertEqual(be.classify(20.0), "shot")

    def test_contact_carries_speeds(self):
        pos = simulate({10: (10.0, 0.0), 70: (0.0, 3.0)}, 120)
        c = be.find_contacts(pos, FPS)
        self.assertEqual(c[0].kind, "pass")
        self.assertAlmostEqual(c[0].speed_out, 10.0, delta=1.0)
        self.assertEqual(c[1].kind, "touch")
        self.assertEqual(c[1].sides, 2)


class AssignTest(unittest.TestCase):
    def test_nearest_foot_within_reach(self):
        pos = simulate({10: (8.0, 0.0)}, 40)
        c = be.find_contacts(pos, FPS)
        feet = np.full((40, 2, 2), np.nan)
        feet[:, 0] = (0.2, 0.0)      # nah am Ball bei Bild 10
        feet[:, 1] = (5.0, 5.0)
        got = be.assign(c, feet, ["a", "b"])
        self.assertEqual(got[0].player, "a")

    def test_no_foot_near_means_no_player(self):
        pos = simulate({10: (8.0, 0.0)}, 40)
        c = be.find_contacts(pos, FPS)
        feet = np.full((40, 1, 2), 20.0)
        self.assertIsNone(be.assign(c, feet, ["a"])[0].player)

    def test_all_nan_feet_are_skipped(self):
        pos = simulate({10: (8.0, 0.0)}, 40)
        c = be.find_contacts(pos, FPS)
        self.assertIsNone(be.assign(c, np.full((40, 1, 2), np.nan), ["a"])[0].player)


if __name__ == "__main__":
    unittest.main()
