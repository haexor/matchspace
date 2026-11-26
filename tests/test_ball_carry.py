import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import ball_carry as bc

CAM = np.array([0.0, -30.0, 8.0])


def ray_to(point):
    d = np.asarray(point, float) - CAM
    return CAM, d / np.linalg.norm(d)


def hands_at(pos, T):
    """Ein Spieler, beide Handgelenke bei pos (±0,2 m), in T Bildern."""
    h = np.zeros((1, T, 2, 3))
    h[0, :, 0] = np.asarray(pos) + [-0.2, 0, 0]
    h[0, :, 1] = np.asarray(pos) + [0.2, 0, 0]
    return h


class RayTest(unittest.TestCase):
    def test_point_on_the_ray_has_zero_distance(self):
        o, d = ray_to([5, 0, 2])
        self.assertAlmostEqual(bc.ray_distance(o, d, [5, 0, 2]), 0.0)

    def test_point_behind_is_infinite(self):
        o, d = ray_to([5, 0, 2])
        self.assertEqual(bc.ray_distance(o, d, [-5, -60, 8]), float("inf"))

    def test_hand_on_the_ray_holds_the_ball(self):
        o, d = ray_to([5, 0, 2])
        who, dist = bc.held_by(o, d, hands_at([5, 0, 2], 1)[:, 0])
        self.assertEqual(who, 0)
        self.assertLess(dist, 0.3)

    def test_low_hands_do_not_hold_it(self):
        o, d = ray_to([5, 0, 0.3])
        self.assertEqual(bc.held_by(o, d, hands_at([5, 0, 0.3], 1)[:, 0])[0], -1)

    def test_ball_at_the_foot_is_not_in_the_hands(self):
        o, d = ray_to([5, 0, 0.11])            # Ball am Boden, Hände ein Meter darüber
        self.assertEqual(bc.held_by(o, d, hands_at([5, 0, 1.4], 1)[:, 0])[0], -1)


class RunsTest(unittest.TestCase):
    def test_short_hits_are_ignored(self):
        owner = np.full(30, -2)
        owner[5:8] = 0
        self.assertEqual(bc.runs(owner), [])

    def test_gaps_inside_a_run_are_bridged(self):
        owner = np.full(40, -2)
        owner[5:10] = 0
        owner[10:14] = -2                        # kein Strahl
        owner[14:18] = 0
        self.assertEqual(bc.runs(owner), [(5, 18, 0)])

    def test_another_player_ends_the_run(self):
        owner = np.full(40, -2)
        owner[5:12] = 0
        owner[12:20] = 1
        self.assertEqual([(a, b, p) for a, b, p in bc.runs(owner)], [(5, 12, 0), (12, 20, 1)])

    def test_extend_into_unknown_frames_only(self):
        unknown = np.zeros(60, bool)
        unknown[0:12] = True
        unknown[30:34] = True
        unknown[40:60] = True
        self.assertEqual(bc.extend([(12, 30, 0)], unknown, reach=12), [(0, 34, 0)])
        self.assertEqual(bc.extend([(34, 40, 0)], unknown, reach=12), [(30, 52, 0)])      # davor die unbekannten 30-33, nach vorn höchstens EXTEND Bilder


class CarryTest(unittest.TestCase):
    def test_throw_in_overhead_is_found_and_follows_the_hands(self):
        T = 40
        hands = hands_at([5, 0, 2.2], T)
        hands[0, :, :, 1] += np.linspace(0, 0.8, T)[:, None]        # die Hände wandern
        origins, directions = np.zeros((T, 3)), np.zeros((T, 3))
        for f in range(T):
            origins[f], directions[f] = ray_to(hands[0, f].mean(axis=0))
        observed = np.ones(T, bool)
        observed[20:24] = False                                       # Ball kurz nicht erkannt
        found, xyz = bc.carry(origins, directions, observed, hands, np.zeros(T, bool))
        self.assertEqual(found, [(0, 40, 0)])
        np.testing.assert_allclose(xyz[22, :2], hands[0, 22].mean(axis=0)[:2], atol=0.05)
        self.assertAlmostEqual(float(xyz[0, 2]), 2.2, delta=0.06)

    def test_a_passing_hand_of_another_player_does_not_end_the_run(self):
        T = 40
        mine = hands_at([5, 0, 2.2], T)
        other = hands_at([5.2, 0, 2.0], T)                   # steht fast auf demselben Strahl, aber seine Hand ist nie die nächste
        other[0, ::2] += [0.0, 0.0, 0.0]
        hands = np.concatenate([mine, other])
        origins, directions = np.zeros((T, 3)), np.zeros((T, 3))
        for f in range(T):
            origins[f], directions[f] = ray_to(mine[0, f].mean(axis=0))
        hands[1, 10:14] += [0.0, 0.0, 0.25]                   # kurz näher am Strahl als die eigenen Hände? nein: bleibt darüber
        found, _ = bc.carry(origins, directions, np.ones(T, bool), hands, np.zeros(T, bool))
        self.assertEqual([p for _, _, p in found], [0])

    def test_track_far_from_the_hands_is_overridden_and_runs_merge(self):
        T = 60
        hands = hands_at([5, 0, 2.0], T)
        origins, directions = np.zeros((T, 3)), np.zeros((T, 3))
        observed = np.zeros(T, bool)
        for f in list(range(0, 10)) + list(range(40, 50)):      # nur in zwei Stücken erkannt
            origins[f], directions[f] = ray_to(hands[0, f].mean(axis=0))
            observed[f] = True
        track = np.tile([20.0, 5.0], (T, 1))                   # Spur zeigt einen Ball weit weg am Boden
        found, xyz = bc.carry(origins, directions, observed, hands, np.zeros(T, bool), track)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0][2], 0)
        self.assertFalse(np.isnan(xyz[:60 if found[0][1] >= 60 else found[0][1], 0]).any())

    def test_position_follows_the_ray_where_the_hands_are_off(self):
        T = 30
        hands = hands_at([5, 0, 2.0], T)
        origins, directions = np.zeros((T, 3)), np.zeros((T, 3))
        truth = np.array([5.0, 0.0, 2.35])                     # der Ball ist 0,35 m höher als die Handgelenke des Modells
        for f in range(T):
            origins[f], directions[f] = ray_to(truth)
        found, xyz = bc.carry(origins, directions, np.ones(T, bool), hands, np.zeros(T, bool))
        self.assertEqual(len(found), 1)
        # auf dem Strahl durch den echten Ball, in der Tiefe der Hände: die Höhe stimmt besser als die der Handgelenke
        self.assertGreater(xyz[10, 2], 2.2)
        self.assertLess(np.linalg.norm(xyz[10] - truth), 0.15)

    def test_ground_ball_gives_no_run(self):
        T = 30
        hands = hands_at([5, 0, 1.4], T)
        origins, directions = np.zeros((T, 3)), np.zeros((T, 3))
        for f in range(T):
            origins[f], directions[f] = ray_to([5, 0, 0.11])
        found, xyz = bc.carry(origins, directions, np.ones(T, bool), hands, np.zeros(T, bool))
        self.assertEqual(found, [])
        self.assertTrue(np.isnan(xyz).all())


if __name__ == "__main__":
    unittest.main()
