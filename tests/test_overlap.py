import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import overlap as ov


def row(lens, box):
    return [lens, *box, 0, 0, 1.7, 0]


class CoveredShareTest(unittest.TestCase):
    def test_disjoint_is_zero(self):
        self.assertEqual(ov.covered_share(np.array([0, 0, 10, 10.0]), np.array([20, 0, 30, 10.0])), 0.0)

    def test_inside_is_one(self):
        self.assertEqual(ov.covered_share(np.array([0, 0, 100, 100.0]), np.array([10, 10, 20, 20.0])), 1.0)

    def test_half_overlap(self):
        self.assertAlmostEqual(ov.covered_share(np.array([0, 0, 10, 10.0]), np.array([5, 0, 15, 10.0])), 0.5)


class WeightFactorTest(unittest.TestCase):
    def obs(self, other_box, other_lens=0):
        a = np.array([row(0, [0, 0, 100, 200])] * 3, float)
        b = np.array([row(other_lens, other_box)] * 3, float)
        return {"a": a, "b": b}

    def test_alone_has_full_weight(self):
        self.assertTrue((ov.weight_factor({"a": np.array([row(0, [0, 0, 10, 10])] * 3, float)}, "a") == 1).all())

    def test_no_overlap_has_full_weight(self):
        self.assertTrue((ov.weight_factor(self.obs([300, 0, 400, 200]), "a") == 1).all())

    def test_heavy_overlap_lowers_weight_but_not_to_zero(self):
        f = ov.weight_factor(self.obs([20, 0, 120, 200]), "a")
        self.assertTrue((f < 1).all())
        self.assertTrue((f >= ov.FLOOR).all())

    def test_full_cover_hits_the_floor(self):
        self.assertTrue((ov.weight_factor(self.obs([0, 0, 100, 200]), "a") == ov.FLOOR).all())

    def test_other_lens_does_not_count(self):
        self.assertTrue((ov.weight_factor(self.obs([0, 0, 100, 200], other_lens=1), "a") == 1).all())

    def test_missing_detection_is_skipped(self):
        o = self.obs([0, 0, 100, 200])
        o["b"][1] = np.nan
        f = ov.weight_factor(o, "a")
        self.assertEqual(f[1], 1.0)
        self.assertEqual(f[0], ov.FLOOR)


if __name__ == "__main__":
    unittest.main()
