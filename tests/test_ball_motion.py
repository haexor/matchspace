import tempfile
import unittest
from pathlib import Path

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import ball_motion as bm
import ball_physics as bp
import own_scene


class SampleTest(unittest.TestCase):
    def test_interpolates_between_valid_neighbours(self):
        v = np.array([[0.0, 0.0], [10.0, 0.0], [20.0, 0.0]])
        out = bm.sample(v, 3, 0.5)
        np.testing.assert_allclose(out[:, 0], [0.0, 5.0, 10.0])

    def test_nan_is_not_smeared(self):
        v = np.array([[0.0, 0.0], [np.nan, np.nan], [20.0, 0.0], [30.0, 0.0]])
        out = bm.sample(v, 4, 1.0)
        self.assertTrue(np.isnan(out[1]).all())
        self.assertEqual(out[2, 0], 20.0)

    def test_takes_valid_neighbour_at_a_gap_edge(self):
        v = np.array([[0.0], [10.0], [np.nan]])
        self.assertEqual(bm.sample(v, 2, 1.2)[1, 0], 10.0)
        self.assertTrue(np.isnan(bm.sample(v, 2, 1.5)[1, 0]))

    def test_one_dimension(self):
        out = bm.sample(np.array([0.0, 4.0, 8.0]), 5, 0.5)
        np.testing.assert_allclose(out, [0, 2, 4, 6, 8])


class OutputTrackTest(unittest.TestCase):
    def write(self, xyz, kind, inferred, contacts):
        d = tempfile.mkdtemp()
        path = Path(d) / "x.ball3d.npz"
        np.savez(path, xyz=xyz, kind=kind, inferred=inferred, z_sigma=np.zeros(len(kind)), fps=30.0,
                 contacts=np.array(contacts, float).reshape(-1, 5))
        return path

    def test_height_is_measured_at_the_ball_bottom(self):
        xyz = np.tile([1.0, 2.0, bp.RADIUS + 1.0], (10, 1))
        path = self.write(xyz, np.full(10, bm.FLIGHT), np.zeros(10, bool), [])
        t = bm.output_track(path, 8, 1.2)
        np.testing.assert_allclose(t.z, 1.0)
        self.assertTrue(t.flight.all())

    def test_ground_ball_has_height_zero(self):
        xyz = np.tile([1.0, 2.0, bp.RADIUS], (10, 1))
        t = bm.output_track(self.write(xyz, np.full(10, bm.GROUND), np.zeros(10, bool), []), 8, 1.2)
        np.testing.assert_allclose(t.z, 0.0)

    def test_contacts_are_mapped_to_output_frames(self):
        xyz = np.tile([1.0, 2.0, bp.RADIUS], (60, 1))
        path = self.write(xyz, np.ones(60, np.uint8), np.zeros(60, bool), [[30, 0, 5, 5, 1.0]])
        t = bm.output_track(path, 50, 30 / 25)
        self.assertEqual(list(t.contacts), [25])

    def test_unknown_stretch_has_no_position(self):
        xyz = np.full((10, 3), np.nan)
        t = bm.output_track(self.write(xyz, np.zeros(10, np.uint8), np.zeros(10, bool), []), 8, 1.2)
        self.assertTrue(np.isnan(t.xy).all())
        self.assertTrue((t.z == 0).all())


def piece(kind, rms, frames, at):
    fit = bp.Fit(kind, np.array(at, float), np.zeros(3), np.zeros(3), 0.0, rms, 0.0)
    seg = bp.Segment(int(frames[0]), int(frames[-1]) + 1, kind, fit, rms, 0.0)
    return {"seg": seg, "frames": np.asarray(frames)}


class ContinuityTest(unittest.TestCase):
    def test_matching_pieces_stay(self):
        pieces = [piece("ground", 0.05, range(0, 10), [1, 1, 0.1]), piece("flight", 0.02, range(11, 30), [1.2, 1, 0.1])]
        self.assertEqual(bm.drop_discontinuous(pieces, 30.0), 0)
        self.assertEqual(len(pieces), 2)

    def test_ground_yields_to_flight_at_a_jump(self):
        pieces = [piece("ground", 0.05, range(0, 10), [-38, -22, 0.1]), piece("flight", 0.02, range(11, 30), [-24, -26, 2.4])]
        self.assertEqual(bm.drop_discontinuous(pieces, 30.0), 1)
        self.assertEqual(pieces[0]["seg"].kind, "flight")

    def test_same_kind_larger_residual_goes(self):
        pieces = [piece("ground", 0.30, range(0, 10), [0, 0, 0.1]), piece("ground", 0.05, range(11, 30), [20, 0, 0.1])]
        bm.drop_discontinuous(pieces, 30.0)
        self.assertEqual([p["seg"].rms for p in pieces], [0.05])

    def test_distant_pieces_are_not_compared(self):
        pieces = [piece("ground", 0.05, range(0, 10), [0, 0, 0.1]), piece("ground", 0.05, range(100, 130), [50, 0, 0.1])]
        self.assertEqual(bm.drop_discontinuous(pieces, 30.0), 0)


class AttachActiveTest(unittest.TestCase):
    def test_only_active_frames_are_pulled(self):
        T = 40
        feet = np.zeros((T, 1, 2))
        ball = np.tile([0.5, 0.0], (T, 1))
        active = np.zeros(T, bool)
        active[18:23] = True
        out = own_scene.attach_ball(ball, feet, 25, active)
        self.assertLess(np.linalg.norm(out[20]), 0.5)
        np.testing.assert_allclose(out[5], ball[5])
        np.testing.assert_allclose(out[35], ball[35])

    def test_none_means_everywhere(self):
        T = 40
        feet = np.zeros((T, 1, 2))
        ball = np.tile([0.5, 0.0], (T, 1))
        np.testing.assert_allclose(own_scene.attach_ball(ball, feet, 25, None), own_scene.attach_ball(ball, feet, 25))


class AttachLimitTest(unittest.TestCase):
    EYE = np.array([0.0, -30.0])

    def scene(self, ball, toe):
        T = 12
        feet = np.full((T, 1, 2), np.nan)
        feet[:] = toe
        return np.tile(ball, (T, 1)), feet

    def test_lateral_pull_is_small(self):
        ball, feet = self.scene([0.0, 0.0], [0.6, 0.0])         # Fuß 0,6 m quer zur Blickrichtung (y)
        out = own_scene.attach_ball(ball, feet, 25, None, eye=self.EYE)
        self.assertLessEqual(abs(out[6, 0] - ball[6, 0]), own_scene.MAX_LATERAL + 1e-6)

    def test_radial_pull_may_be_larger(self):
        ball, feet = self.scene([0.0, 0.0], [0.0, 0.5])         # Fuß 0,5 m weiter hinten in Blickrichtung
        free = own_scene.attach_ball(ball, feet, 25, None)
        out = own_scene.attach_ball(ball, feet, 25, None, eye=self.EYE)
        self.assertGreater(out[6, 1], 0.1)
        self.assertLessEqual(out[6, 1], free[6, 1] + 1e-6)

    def test_without_eye_nothing_changes(self):
        ball, feet = self.scene([0.0, 0.0], [0.6, 0.0])
        a = own_scene.attach_ball(ball, feet, 25, None)
        self.assertGreater(abs(a[6, 0]), own_scene.MAX_LATERAL)


class FillRawTest(unittest.TestCase):
    FPS = 30.0

    def arrays(self, n, found_at):
        origin = np.tile([0.0, -30.0, 8.0], (n, 1))
        direction = np.tile([0.0, 1.0, 0.0], (n, 1))
        rng = np.zeros(n)
        found = np.zeros(n, bool)
        for f, y in found_at.items():                # Erkennung am Boden bei (0, y): Punkt = Ursprung + Richtung * Entfernung
            rng[f] = y + 30.0
            found[f] = True
        return origin, direction, rng, found

    def run_fill(self, kind0, found_at, n=30):
        origin, direction, rng, found = self.arrays(n, found_at)
        xyz, kind = np.full((n, 3), np.nan), np.zeros(n, np.uint8)
        inferred, zs = np.zeros(n, bool), np.zeros(n)
        for f, k in kind0.items():
            kind[f], xyz[f] = k, [0.0, 0.0, 0.11]
        got = bm.fill_raw(xyz, kind, inferred, zs, origin, direction, rng, found, self.FPS)
        return got, xyz, kind

    def test_detection_near_the_last_known_place_is_taken(self):
        got, xyz, kind = self.run_fill({5: bm.GROUND}, {8: 0.3, 10: 0.5})
        self.assertEqual(got, 2)
        self.assertEqual(kind[8], bm.GROUND)

    def test_jump_is_not_taken_and_does_not_move_the_anchor(self):
        got, _, kind = self.run_fill({5: bm.GROUND}, {8: 9.0, 9: 0.2})   # 9 m in 0,1 s: nein; danach wieder nah am Anker
        self.assertEqual(kind[8], 0)
        self.assertEqual(kind[9], bm.GROUND)

    def test_nothing_without_an_anchor(self):
        got, _, _ = self.run_fill({}, {8: 0.3})
        self.assertEqual(got, 0)

    def test_too_old_anchor_is_not_used(self):
        got, _, _ = self.run_fill({0: bm.GROUND}, {25: 0.3})        # 0,83 s
        self.assertEqual(got, 0)


class BridgeTest(unittest.TestCase):
    FPS = 25.0

    def track(self, n, known):
        xy = np.full((n, 2), np.nan)
        z = np.zeros(n)
        for f, p in known.items():
            xy[f] = p
        return xy, z

    def test_plausible_gap_is_a_straight_roll(self):
        xy, z = self.track(30, {4: (0.0, 0.0), 25: (8.4, 0.0)})     # 21 Bilder = 0,84 s: 10 m/s
        out, oz = bm.bridge(xy, z, self.FPS)
        self.assertFalse(np.isnan(out[10:25, 0]).any())
        self.assertTrue((np.diff(out[4:26, 0]) > 0).all())
        self.assertGreater(oz[14], 0.0)                                # schnell und kurz: Flug mit Bogen

    def test_slow_gap_stays_on_the_ground(self):
        xy, z = self.track(80, {4: (0.0, 0.0), 70: (10.0, 0.0)})      # 2,6 s: 3,8 m/s
        out, oz = bm.bridge(xy, z, self.FPS)
        self.assertTrue((oz[5:70] == 0).all())
        self.assertFalse(np.isnan(out[5:70, 0]).any())

    def test_impossible_speed_leaves_the_gap_empty(self):
        xy, z = self.track(30, {4: (0.0, 0.0), 14: (20.0, 0.0)})    # 20 m in 0,4 s: 50 m/s
        out, _ = bm.bridge(xy, z, self.FPS)
        self.assertTrue(np.isnan(out[5:14, 0]).all())
        np.testing.assert_allclose(out[4], [0.0, 0.0])
        np.testing.assert_allclose(out[14], [20.0, 0.0])

    def test_long_gap_is_not_bridged(self):
        xy, z = self.track(200, {4: (0.0, 0.0), 180: (5.0, 0.0)})   # 7 s
        out, _ = bm.bridge(xy, z, self.FPS)
        self.assertTrue(np.isnan(out[10:170, 0]).all())

    def test_start_and_end_hold_only_briefly(self):
        xy, z = self.track(100, {30: (1.0, 2.0), 60: (1.0, 2.0)})
        out, _ = bm.bridge(xy, z, self.FPS)
        self.assertTrue(np.isnan(out[:5, 0]).all())
        np.testing.assert_allclose(out[10], [1.0, 2.0])               # 1 s vor der ersten Lage gehalten
        self.assertTrue(np.isnan(out[95, 0]))
        np.testing.assert_allclose(out[70], [1.0, 2.0])

    def test_no_position_stays_empty(self):
        xy, z = self.track(10, {})
        out, _ = bm.bridge(xy, z, self.FPS)
        self.assertTrue(np.isnan(out).all())


class FlightContactsTest(unittest.TestCase):
    """Ein Wurf, vom Rand aus gesehen: Kontakte mitten im Flug sind keine, ein Knick der Bahn ist einer; der Flug reicht bis zum Abwurf."""
    FPS = 30.0
    CAM = np.array([0.0, -40.0, 8.0])

    def rays(self, pts):
        v = pts - self.CAM
        rng = np.linalg.norm(v, axis=1)
        return np.tile(self.CAM, (len(pts), 1)), v / rng[:, None], rng

    def flight(self, n=42, kick_at=None):
        t = np.arange(n) / self.FPS
        v = np.array([8.0, 1.0, 7.0])
        pts = np.array([0.0, 0.0, 1.0]) + t[:, None] * v - 0.5 * bp.G * (t ** 2)[:, None] * np.array([0.0, 0.0, 1.0])
        if kick_at is not None:           # nach dem Kontakt eine andere Richtung (Tempo und Richtung ändern sich schlagartig)
            u = t[kick_at:] - t[kick_at]
            v2 = np.array([-5.0, 3.0, 4.0])
            pts[kick_at:] = pts[kick_at] + u[:, None] * v2 - 0.5 * bp.G * (u ** 2)[:, None] * np.array([0.0, 0.0, 1.0])
        return pts

    def contact(self, frame, confidence=0.5):
        return type("C", (), {"frame": frame, "confidence": confidence})()

    def test_contact_inside_a_smooth_flight_is_dropped(self):
        o, d, r = self.rays(self.flight())
        kept = bm.prune_flight_contacts(o, d, r, np.ones(len(r), bool), [self.contact(20)], self.FPS)
        self.assertEqual(kept, [])

    def test_kick_in_flight_stays(self):
        o, d, r = self.rays(self.flight(kick_at=20))
        kept = bm.prune_flight_contacts(o, d, r, np.ones(len(r), bool), [self.contact(20)], self.FPS)
        self.assertEqual([c.frame for c in kept], [20])

    def test_flight_reaches_back_to_the_release(self):
        pts = self.flight()
        pts[:10] = pts[10]                # vorher liegt der Ball in der Hand
        o, d, r = self.rays(pts)
        found = np.ones(len(r), bool)
        kind, fit = bp.choose(o[14:], d[14:], np.arange(14, len(r)) / self.FPS, r[14:])
        self.assertEqual(kind, "flight")
        self.assertEqual(bm.reach(fit, o, d, found, 14, -1, self.FPS), 10)

    def test_reach_stops_at_the_limit(self):
        o, d, r = self.rays(self.flight())
        kind, fit = bp.choose(o[14:], d[14:], np.arange(14, len(r)) / self.FPS, r[14:])
        self.assertEqual(bm.reach(fit, o, d, np.ones(len(r), bool), 14, 8, self.FPS), 9)


if __name__ == "__main__":
    unittest.main()
