import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import jersey_reader


def person(dx=-8.0, height=30.0, conf=0.9, x=100.0, y=50.0):
    """COCO-17-Gelenkpunkte eines aufrechten Spielers; dx = linke minus rechte Schulter in x (negativ: Rücken)."""
    kp = np.zeros((17, 3), np.float32)
    kp[:, 2] = conf
    kp[5] = (x + dx / 2, y, conf)
    kp[6] = (x - dx / 2, y, conf)
    kp[11] = (x + dx / 3, y + height, conf)
    kp[12] = (x - dx / 3, y + height, conf)
    return kp


class BackViewTest(unittest.TestCase):
    def test_back_to_camera(self):
        self.assertTrue(jersey_reader.is_back_view(person(dx=-8)))

    def test_front_to_camera(self):
        self.assertFalse(jersey_reader.is_back_view(person(dx=8)))

    def test_sideways_is_not_read(self):
        self.assertFalse(jersey_reader.is_back_view(person(dx=-1)))

    def test_unsure_hips_are_not_read(self):
        kp = person(dx=-8)
        kp[11, 2] = 0.1
        self.assertFalse(jersey_reader.is_back_view(kp))


class GeometryTest(unittest.TestCase):
    def test_height_is_shoulder_to_hip(self):
        self.assertAlmostEqual(jersey_reader.back_height(person(height=30)), 30.0, places=4)

    def test_quad_spans_the_back(self):
        kp = person(dx=-10, height=30, x=100, y=50)
        quad = jersey_reader.back_quad(kp)
        self.assertEqual(quad.shape, (4, 2))
        top, bottom = quad[:2, 1].mean(), quad[2:, 1].mean()
        self.assertLess(top, 50)            # über der Schulterlinie
        self.assertGreater(bottom, 50 + 30 * 0.95)   # bis an die Hüfte
        width = np.linalg.norm(quad[1] - quad[0])
        self.assertGreaterEqual(width, 10)  # mindestens so breit wie die Schultern

    def test_too_small_gives_no_crop(self):
        image = np.full((200, 200, 3), 90, np.uint8)
        small = person(height=jersey_reader.MIN_HEIGHT - 1)
        self.assertIsNone(jersey_reader.back_crop(image, small))
        big = person(height=jersey_reader.FULL_HEIGHT)
        crop = jersey_reader.back_crop(image, big)
        self.assertEqual(crop.shape, (jersey_reader.CROP_H, jersey_reader.CROP_W))

    def test_weight_grows_with_height(self):
        w = jersey_reader.reading_weight
        self.assertAlmostEqual(w(jersey_reader.MIN_HEIGHT), jersey_reader.MIN_WEIGHT)
        self.assertAlmostEqual(w(jersey_reader.FULL_HEIGHT), 1.0)
        self.assertAlmostEqual(w(jersey_reader.FULL_HEIGHT + 20), 1.0)
        mid = (jersey_reader.MIN_HEIGHT + jersey_reader.FULL_HEIGHT) / 2
        self.assertAlmostEqual(w(mid), (jersey_reader.MIN_WEIGHT + 1.0) / 2)


class CropFolderTest(unittest.TestCase):
    def test_crops_only_below_data_work(self):
        with self.assertRaises(ValueError):
            jersey_reader.check_private_dir("web/data/szene")
        jersey_reader.check_private_dir("data/work/veo/crops")


if __name__ == "__main__":
    unittest.main()
