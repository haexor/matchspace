import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import ball_gapfill as g

NAN = np.nan


def track(n, known, start=(0, 100.0, 200.0), step=(4.0, 0.0)):
    """Spur, die sich pro Bild um step bewegt; nur die Bilder in known sind gesetzt."""
    pix = np.full((n, 3), NAN)
    for f in known:
        pix[f] = (start[0], start[1] + step[0] * f, start[2] + step[1] * f)
    return pix


class ExpectedTest(unittest.TestCase):
    def test_midpoint_between_two_finds(self):
        pix = track(20, [2, 10])
        known = ~np.isnan(pix[:, 0])
        lens, u, v, radius = g.expected(pix, known, 6)
        self.assertEqual(lens, 0)
        self.assertAlmostEqual(u, 100.0 + 4.0 * 6)
        self.assertAlmostEqual(v, 200.0)
        self.assertGreater(radius, g.BASE_RADIUS)

    def test_extrapolates_with_last_velocity_at_the_end(self):
        pix = track(20, [4, 5, 6])
        known = ~np.isnan(pix[:, 0])
        lens, u, v, _ = g.expected(pix, known, 8)
        self.assertAlmostEqual(u, 100.0 + 4.0 * 8)

    def test_too_far_from_any_find_is_skipped(self):
        pix = track(60, [0])
        known = ~np.isnan(pix[:, 0])
        self.assertIsNone(g.expected(pix, known, 40))

    def test_radius_grows_with_distance_and_is_capped(self):
        pix = track(60, [0])
        known = ~np.isnan(pix[:, 0])
        r1 = g.expected(pix, known, 1)[3]
        r5 = g.expected(pix, known, 5)[3]
        self.assertLess(r1, r5)
        self.assertLessEqual(r5, g.MAX_RADIUS)

    def test_different_lenses_do_not_interpolate(self):
        pix = track(20, [2])
        pix[10] = (1, 300.0, 300.0)
        known = ~np.isnan(pix[:, 0])
        lens, u, _, _ = g.expected(pix, known, 4)   # näher am linken Fund: von dort aus, nicht Mitte
        self.assertEqual(lens, 0)


class PickTest(unittest.TestCase):
    def test_nearest_within_radius(self):
        self.assertEqual(g.pick([(100, 100, 0.5), (110, 100, 0.9)], 108, 100, 30), (110, 100, 0.9))

    def test_none_outside_radius(self):
        self.assertIsNone(g.pick([(300, 300, 0.9)], 100, 100, 30))

    def test_empty(self):
        self.assertIsNone(g.pick([], 100, 100, 30))


class CropBoxTest(unittest.TestCase):
    def test_pushed_into_the_image(self):
        self.assertEqual(g.crop_box(5, 5, 2048, 1024), (0, 0))
        x0, y0 = g.crop_box(2040, 1020, 2048, 1024)
        self.assertEqual((x0 + 2 * g.CROP, y0 + 2 * g.CROP), (2048, 1024))

    def test_centred_inside(self):
        self.assertEqual(g.crop_box(500, 500, 2048, 1024), (500 - g.CROP, 500 - g.CROP))


class FillTest(unittest.TestCase):
    def run_fill(self, pix, truth, miss=()):
        """Detektor, der den Ball an der wahren Stelle des Bildes findet (außer in miss)."""
        def cut(todo):
            return [t[0] for t in todo]   # statt Bild: nur die Bildnummer durchreichen

        def detect(crops):
            out = []
            for f, (x0, y0) in zip(crops, self.boxes):
                out.append([] if f in miss else [(truth[f][0] - x0, truth[f][1] - y0, 0.4)])
            return out

        def cut_and_remember(todo):
            self.boxes = [(t[5], t[6]) for t in todo]
            return cut(todo)
        return g.fill(cut_and_remember, detect, pix)

    def test_gap_between_two_finds_is_filled_exactly(self):
        full = track(30, range(30))
        pix = track(30, [3, 12])
        added = self.run_fill(pix, {f: full[f, 1:] for f in range(30)})
        self.assertTrue(added[4:12].all())
        np.testing.assert_allclose(pix[4:12], full[4:12])

    def test_gap_grows_in_rounds_from_both_sides(self):
        full = track(60, range(60))
        pix = track(60, [5, 45])   # Lücke länger als REACH: braucht mehrere Runden
        added = self.run_fill(pix, {f: full[f, 1:] for f in range(60)})
        self.assertGreater(added.sum(), 30)

    def test_nothing_found_means_nothing_invented(self):
        full = track(30, range(30))
        pix = track(30, [3, 12])
        added = self.run_fill(pix, {f: full[f, 1:] for f in range(30)}, miss=set(range(30)))
        self.assertFalse(added.any())
        self.assertTrue(np.isnan(pix[6, 0]))

    def test_far_off_hit_is_rejected(self):
        full = track(30, range(30))
        pix = track(30, [3, 12])
        wrong = {f: (full[f, 1] + 200, full[f, 2] + 200) for f in range(30)}
        added = self.run_fill(pix, wrong)
        self.assertFalse(added.any())

    def test_existing_finds_are_not_touched(self):
        full = track(30, range(30))
        pix = track(30, [3, 12])
        before = pix[[3, 12]].copy()
        self.run_fill(pix, {f: full[f, 1:] for f in range(30)})
        np.testing.assert_array_equal(pix[[3, 12]], before)


if __name__ == "__main__":
    unittest.main()
