import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import looks_clean as lc


def red_torso_with_blob():
    """64 × 64 Rumpfkachel, rotes Trikot, heller Fleck über der Naht (der Rücken liegt am Rand)."""
    t = np.zeros((64, 64, 3), np.uint8)
    t[:] = (20, 20, 170)
    rolled = np.roll(t, 32, axis=1)
    rolled[26:44, 24:40] = (210, 210, 215)
    rolled[46:49, 22:42] = (120, 120, 190)      # Schmierstreifen darunter
    return np.roll(rolled, -32, axis=1)


class PrintMaskTest(unittest.TestCase):
    def test_finds_blob_and_smear_across_the_seam(self):
        mask = lc.print_mask(red_torso_with_blob())
        self.assertTrue(mask[30, 30] and mask[35, 24])        # in der gerollten Kachel
        self.assertFalse(mask[5, 5])

    def test_plain_shirt_gives_none(self):
        t = np.zeros((64, 64, 3), np.uint8)
        t[:] = (20, 20, 170)
        self.assertIsNone(lc.print_mask(t))

    def test_dark_print_on_light_shirt(self):
        t = np.zeros((64, 64, 3), np.uint8)
        t[:] = (230, 230, 230)
        rolled = np.roll(t, 32, axis=1)
        rolled[26:44, 24:40] = (30, 30, 30)
        self.assertIsNotNone(lc.print_mask(np.roll(rolled, -32, axis=1)))


class EraseTest(unittest.TestCase):
    def test_blob_is_covered_with_the_shirt_colour(self):
        hi = np.zeros((128, 128, 3))
        hi[:] = (20, 20, 170)
        hi[52:88, 48:80] = (210, 210, 215)
        mask = np.zeros((64, 64), bool)
        mask[26:44, 24:40] = True
        out = lc.erase(hi, mask, 2)
        np.testing.assert_allclose(out[70, 64], (20, 20, 170), atol=3)
        np.testing.assert_allclose(out[5, 5], (20, 20, 170), atol=1e-6)

    def test_empty_ring_changes_nothing(self):
        hi = np.full((8, 8, 3), 100.0)
        np.testing.assert_array_equal(lc.erase(hi, np.ones((4, 4), bool), 2), hi)


class CleanBackTest(unittest.TestCase):
    def test_blob_disappears_in_the_big_tile(self):
        lo = red_torso_with_blob()
        hi = np.kron(lo, np.ones((2, 2, 1), np.uint8))
        out, found = lc.clean_back(hi, lo, 2)
        self.assertTrue(found)
        rolled = np.roll(out, 64, axis=1)
        self.assertLess(float(np.abs(rolled[70, 64].astype(int) - (20, 20, 170)).max()), 6)

    def test_nothing_found_keeps_the_tile(self):
        lo = np.zeros((64, 64, 3), np.uint8)
        lo[:] = (20, 20, 170)
        hi = np.kron(lo, np.ones((2, 2, 1), np.uint8))
        out, found = lc.clean_back(hi, lo, 2)
        self.assertFalse(found)
        np.testing.assert_array_equal(out, hi)


class UpscaleTest(unittest.TestCase):
    def test_rects_scale_and_seam_has_no_edge(self):
        segments = [{"name": "torso", "rect": [0, 0, 8, 4]}]
        atlas = np.zeros((8, 16, 3), np.uint8)
        atlas[:4, :8] = np.arange(8, dtype=np.uint8)[None, :, None] * 30
        big = lc.upscale_atlas(atlas, 8, 2, segments, 4)
        self.assertEqual(big.shape, (32, 64, 3))
        self.assertTrue((big[:16, 32:] == 0).all())
        self.assertGreater(int(big[8, 0, 0]), 0)


if __name__ == "__main__":
    unittest.main()
