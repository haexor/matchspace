import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import ball_physics as bp

CAM = np.array([0.0, -37.0, 5.5])
FPS = 30.0


def rays_to(points, noise=0.0, seed=0):
    """Sehstrahlen von der Kamera zu Punkten (n, 3) mit Richtungsrauschen in rad."""
    rng = np.random.default_rng(seed)
    d = points - CAM
    d = d / np.linalg.norm(d, axis=1, keepdims=True)
    d = d + rng.normal(0, noise, d.shape)
    d = d / np.linalg.norm(d, axis=1, keepdims=True)
    return np.tile(CAM, (len(points), 1)), d, np.linalg.norm(points - CAM, axis=1)


def flight(p0, v, n):
    t = np.arange(n) / FPS
    pts = np.array(p0) + np.outer(t, v) + 0.5 * np.outer(t ** 2, [0, 0, -bp.G])
    return t, pts


def roll(p0, v, decel, n):
    t = np.arange(n) / FPS
    d = np.array(v, float) / np.linalg.norm(v)
    s = np.linalg.norm(v) * t - 0.5 * decel * t ** 2
    pts = np.array(p0, float) + np.outer(s, d)
    pts[:, 2] = bp.RADIUS
    return t, pts


class FlightFitTest(unittest.TestCase):
    def test_recovers_height_of_a_lob(self):
        t, pts = flight([5, -15, 0.11], [8, 3, 8], 40)      # Scheitel rund 3,3 m
        o, d, r = rays_to(pts, noise=2e-4)
        f = bp.fit(o, d, t, r, "flight")
        np.testing.assert_allclose(f.at(t)[:, 2], pts[:, 2], atol=0.35)
        self.assertLess(f.z_sigma, bp.MAX_Z_SIGMA)

    def test_noise_free_is_exact(self):
        t, pts = flight([5, -15, 0.11], [8, 3, 8], 40)
        o, d, r = rays_to(pts)
        f = bp.fit(o, d, t, r, "flight")
        np.testing.assert_allclose(f.at(t), pts, atol=1e-6)

    def test_too_few_observations_gives_none(self):
        t, pts = flight([5, -15, 0.11], [8, 3, 8], bp.MIN_OBS - 1)
        o, d, r = rays_to(pts)
        self.assertIsNone(bp.fit(o, d, t, r, "flight"))

    def test_flight_straight_at_the_camera_is_uncertain(self):
        t, pts = flight([0, -15, 0.11], [0, -10, 8], 40)     # genau auf die Kamera zu
        o, d, r = rays_to(pts, noise=2e-4)
        side_t, side_pts = flight([0, -15, 0.11], [12, 0, 8], 40)
        so, sd, sr = rays_to(side_pts, noise=2e-4)
        self.assertGreater(bp.fit(o, d, t, r, "flight").z_sigma, bp.fit(so, sd, side_t, sr, "flight").z_sigma)


class ChooseTest(unittest.TestCase):
    def test_lob_is_flight(self):
        t, pts = flight([5, -15, 0.11], [8, 3, 8], 40)
        kind, f = bp.choose(*rays_to(pts, noise=2e-4)[:2], t, rays_to(pts)[2])
        self.assertEqual(kind, "flight")

    def test_rolling_ball_is_ground(self):
        t, pts = roll([5, -15, 0], [8, 3, 0], 1.2, 40)
        o, d, r = rays_to(pts, noise=2e-4)
        kind, f = bp.choose(o, d, t, r)
        self.assertEqual(kind, "ground")
        self.assertAlmostEqual(f.at(t[10])[2], bp.RADIUS, places=3)
        self.assertLess(f.a[0], 0)                              # bremst

    def test_ground_fit_recovers_deceleration(self):
        t, pts = roll([5, -15, 0], [8, 0, 0], 1.2, 40)
        f = bp.fit(*rays_to(pts)[:2], t, rays_to(pts)[2], "ground")
        self.assertAlmostEqual(f.a[0], -1.2, delta=0.1)

    def test_short_piece_is_unknown(self):
        t, pts = roll([5, -15, 0], [8, 3, 0], 1.2, 4)
        o, d, r = rays_to(pts)
        self.assertEqual(bp.choose(o, d, t, r)[0], "unknown")


class BounceTest(unittest.TestCase):
    def test_bounce_splits_the_track(self):
        # Fall aus 2 m: erst Flug, nach dem Aufprall zweiter Bogen mit halber Geschwindigkeit
        n1 = 12
        t1, p1 = flight([5, -15, 2.0], [6, 0, 0], n1)
        v_hit = np.sqrt(2 * bp.G * (2.0 - bp.RADIUS))
        t2, p2 = flight([p1[-1][0] + 6 / FPS, -15, bp.RADIUS], [6, 0, v_hit * 0.6], 18)
        pts = np.vstack([p1, p2])
        t = np.arange(len(pts)) / FPS
        o, d, r = rays_to(pts, noise=1e-4)
        segs = bp.segment_track(o, d, t, r, np.arange(len(pts)))
        self.assertGreaterEqual(len(segs), 2)
        self.assertTrue(all(s.kind in ("flight", "ground") for s in segs))

    def test_single_roll_is_one_segment(self):
        t, pts = roll([5, -15, 0], [8, 3, 0], 1.2, 40)
        o, d, r = rays_to(pts, noise=1e-4)
        segs = bp.segment_track(o, d, t, r, np.arange(40))
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0].kind, "ground")
        self.assertEqual((segs[0].start, segs[0].stop), (0, 40))


if __name__ == "__main__":
    unittest.main()
