import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import ball_look as bl


def patch(colour, ball=None):
    img = np.zeros((60, 60, 3), np.uint8)
    img[:] = (30, 70, 30)                          # Rasen (BGR)
    if ball:
        img[ball[0]:ball[1], ball[0]:ball[1]] = colour
    return img


class WhiteShareTest(unittest.TestCase):
    def test_white_ball_scores_high(self):
        self.assertGreater(bl.white_share(patch((235, 235, 235), (26, 36)), 31, 31), bl.MIN_WHITE * 3)

    def test_orange_marker_scores_zero(self):
        self.assertLess(bl.white_share(patch((0, 120, 255), (26, 36)), 31, 31), bl.MIN_WHITE)

    def test_bare_grass_scores_zero(self):
        self.assertEqual(bl.white_share(patch((0, 0, 0)), 30, 30), 0.0)

    def test_edge_of_image_does_not_fail(self):
        self.assertEqual(bl.white_share(patch((0, 0, 0)), 0, 0), 0.0)
        self.assertEqual(bl.white_share(patch((0, 0, 0)), 500, 500), 0.0)


if __name__ == "__main__":
    unittest.main()
