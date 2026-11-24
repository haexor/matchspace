import unittest
from unittest import mock

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import scene_finder as sf


def clip(height, share, n=60):
    """Szene mit Ballführer der Höhe height; Ball in der Zone, in share der Bilder gefunden."""
    box = [900.0, 400.0, 940.0, 400.0 + height, 0.9, 0]
    frames = [{"left": [list(box)], "right": []} for _ in range(n)]
    pos = np.full((n, 2), np.nan)
    pix = np.full((n, 3), np.nan)
    found = np.arange(n) < int(n * share)
    pos[found] = (-12.0, -18.0)
    pix[found] = (0, 920.0, 400.0 + height)
    return {"frames": frames}, {"pos": pos, "pixel": pix, "fps": 30.0}


def on_ground(x=-12.0, y=-18.0):
    return mock.patch.object(sf.veo_camera, "to_ground", lambda cam, lens, px, h: (np.array([[x, y]]), None))


class ZoneTest(unittest.TestCase):
    def test_inside_and_outside(self):
        self.assertTrue(sf.in_zone([[10, -20]]).all())
        self.assertTrue(sf.in_zone([[-15, -12]]).all())
        self.assertFalse(sf.in_zone([[2, -20]]).any())      # an der Naht der Linsenbilder
        self.assertFalse(sf.in_zone([[10, 5]]).any())       # auf der fernen Platzhälfte
        self.assertFalse(sf.in_zone([[30, -20]]).any())     # zu weit seitlich
        self.assertFalse(sf.in_zone([[np.nan, np.nan]]).any())


class MergeTest(unittest.TestCase):
    def test_keeps_best_per_event(self):
        kept = sf.merge([(0.9, 100.0), (0.8, 105.0), (0.7, 160.0), (0.6, 162.0)], 20.0)
        self.assertEqual([r[1] for r in kept], [100.0, 160.0])

    def test_sorts_by_points(self):
        self.assertEqual(sf.merge([(0.2, 0.0), (0.9, 50.0)], 10.0)[0][0], 0.9)


class KicksTest(unittest.TestCase):
    def test_counts_each_event_once(self):
        fps = 30.0
        t = np.arange(150) / fps
        x = np.where(t < 2.0, 2.0 * t, 4.0 + 20.0 * (t - 2.0))   # Schuss bei 2 s: Tempo springt von 2 auf 20 m/s
        self.assertEqual(sf.kicks(np.column_stack([x, np.zeros_like(x)]), fps), 1)

    def test_none_for_a_steady_roll(self):
        self.assertEqual(sf.kicks(np.column_stack([np.arange(100) * 5.0 / 30.0, np.zeros(100)]), 30.0), 0)

    def test_gaps_do_not_count(self):
        pos = np.column_stack([np.arange(60) * 0.1, np.zeros(60)])
        pos[20:40] = np.nan
        self.assertEqual(sf.kicks(pos, 30.0), 0)


class ScoreTest(unittest.TestCase):
    def test_grows_with_size_and_ball_share(self):
        with on_ground():
            near = sf.score_clip(*clip(120, 0.9), {})
            far = sf.score_clip(*clip(50, 0.9), {})
            blind = sf.score_clip(*clip(120, 0.2), {})
        self.assertGreater(near["punkte"], far["punkte"])
        self.assertGreater(near["punkte"], blind["punkte"])
        self.assertEqual(near["ballfuehrerHoehePx"], 120.0)
        self.assertEqual(near["ballanteil"], 0.9)
        self.assertEqual(near["zone"], 1.0)

    def test_the_seam_costs_points(self):
        det, ball = clip(120, 0.9)
        with on_ground():
            clean = sf.score_clip(det, ball, {})
            for f in det["frames"]:
                f["left"][0][0], f["left"][0][2] = 2000.0, 2046.0   # Box reicht bis an den Rand des Linsenbilds
            ball["pixel"][:, 1] = 2023.0
            cut = sf.score_clip(det, ball, {})
        self.assertEqual(cut["nahtanteil"], 1.0)
        self.assertLess(cut["punkte"], clean["punkte"])

    def test_no_ball_no_points(self):
        det, ball = clip(120, 0.0)
        with on_ground(0.0, 0.0):
            self.assertEqual(sf.score_clip(det, ball, {})["punkte"], 0.0)


if __name__ == "__main__":
    unittest.main()
