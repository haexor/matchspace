import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import scene_boxes as sb


def box(x, y=100.0, w=20.0, h=60.0, colour=0):
    return [x, y, x + w, y + h, 0.9, colour]


def frames(rows):
    """rows: je Bild eine Liste von Boxen der linken Linse."""
    return [{"left": r, "right": []} for r in rows]


class PostureTest(unittest.TestCase):
    def test_standing_crouching_and_lying(self):
        height = np.array([1.8, 1.2, 0.5])
        down, low = sb.posture(height, np.array([20.0, 20.0, 20.0]), np.array([60.0, 60.0, 60.0]), 1.75)
        self.assertEqual(down.tolist(), [False, False, True])
        self.assertEqual(low.tolist(), [False, True, True])         # liegend heißt auch tief

    def test_a_wide_box_of_medium_height_counts_as_lying(self):
        down, _ = sb.posture(np.array([0.9]), np.array([90.0]), np.array([60.0]), 1.75)
        self.assertTrue(down[0])
        down, _ = sb.posture(np.array([0.9]), np.array([30.0]), np.array([60.0]), 1.75)
        self.assertFalse(down[0])

    def test_missing_measurements_are_not_lying(self):
        down, low = sb.posture(np.array([np.nan]), np.array([np.nan]), np.array([np.nan]), 1.75)
        self.assertFalse(down[0] or low[0])


class LinkTrackletsTest(unittest.TestCase):
    def test_two_people_keep_their_numbers(self):
        rows = [[box(100 + i), box(300)] for i in range(20)]
        ids = sb.link_tracklets(frames(rows), "left")
        self.assertEqual(len({int(i[0]) for i in ids}), 1)
        self.assertEqual(len({int(i[1]) for i in ids}), 1)
        self.assertNotEqual(ids[0][0], ids[0][1])

    def test_a_short_gap_keeps_the_number_a_long_one_starts_a_new_one(self):
        short = [[box(100)] for _ in range(5)] + [[] for _ in range(sb.MAX_MISS - 2)] + [[box(100)] for _ in range(3)]
        ids = sb.link_tracklets(frames(short), "left")
        self.assertEqual(len({int(i[0]) for i in ids if len(i)}), 1)
        long = [[box(100)] for _ in range(5)] + [[] for _ in range(sb.MAX_MISS + 5)] + [[box(100)] for _ in range(3)]
        ids = sb.link_tracklets(frames(long), "left")
        self.assertEqual(len({int(i[0]) for i in ids if len(i)}), 2)

    def test_a_jump_of_more_than_the_link_distance_is_a_new_person(self):
        rows = [[box(100)], [box(100 + 60 * sb.LINK * 1.5)]]
        ids = sb.link_tracklets(frames(rows), "left")
        self.assertNotEqual(ids[0][0], ids[1][0])

    def test_empty_frames_give_empty_results(self):
        self.assertEqual([len(i) for i in sb.link_tracklets(frames([[], []]), "left")], [0, 0])


if __name__ == "__main__":
    unittest.main()
