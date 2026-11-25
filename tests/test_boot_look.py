import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import boot_look as bl

GRASS = (30, 120, 40)       # BGR
SOCK = (60, 60, 200)
ORANGE = (30, 120, 250)


def mosaic(fraction_boot=0.5):
    tile = np.zeros((16, 16, 3), np.uint8)
    tile[:] = GRASS
    tile[:, :4] = SOCK
    tile[4:, 4:4 + int(16 * fraction_boot)] = ORANGE
    return tile


class BootColourTest(unittest.TestCase):
    def test_finds_boot_among_grass_and_sock(self):
        colour, n = bl.boot_colour(mosaic(), SOCK)
        self.assertGreater(n, bl.MIN_BOOT)
        np.testing.assert_allclose(colour, ORANGE, atol=2)

    def test_no_boot_gives_none(self):
        tile = np.zeros((16, 16, 3), np.uint8)
        tile[:] = GRASS
        colour, _ = bl.boot_colour(tile, SOCK)
        self.assertIsNone(colour)


class SharedColourTest(unittest.TestCase):
    def test_takes_the_colour_of_the_better_seen_foot(self):
        good, poor = mosaic(0.7), mosaic(0.1)
        colour = bl.shared_colour(poor, good, SOCK)
        np.testing.assert_allclose(colour, ORANGE, atol=2)

    def test_takes_the_more_distinct_colour(self):
        muddy = np.zeros((16, 16, 3), np.uint8)
        muddy[:] = GRASS
        muddy[2:, 4:] = (90, 100, 110)                    # blasse Mischfarbe, aber mehr Texel
        vivid = mosaic(0.4)
        colour = bl.shared_colour(muddy, vivid, SOCK)
        np.testing.assert_allclose(colour, ORANGE, atol=2)

    def test_none_when_no_boot_anywhere(self):
        grass = np.zeros((16, 16, 3), np.uint8)
        grass[:] = GRASS
        self.assertIsNone(bl.shared_colour(grass, grass, SOCK))

    def test_given_colour_is_used(self):
        out = bl.clean_foot(mosaic(0.1), SOCK, colour=np.array(ORANGE, np.float32))
        self.assertGreater(float(out[..., 2].mean()), 150)


class CleanFootTest(unittest.TestCase):
    def test_grass_pixels_become_boot_colour(self):
        out = bl.clean_foot(mosaic(), SOCK)
        self.assertEqual(out.shape, (16, 16, 3))
        # kein Rasengrün mehr: Rot überwiegt, Grün ragt nirgends über Rot hinaus
        g, r = out[..., 1].astype(int), out[..., 2].astype(int)
        self.assertLess(float((g > r + 40).mean()), 0.01)
        self.assertGreater(float(r.mean()), 150)

    def test_without_boot_the_tile_is_kept(self):
        tile = np.zeros((16, 16, 3), np.uint8)
        tile[:] = GRASS
        np.testing.assert_array_equal(bl.clean_foot(tile, SOCK), tile)


if __name__ == "__main__":
    unittest.main()
