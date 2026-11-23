import subprocess
import unittest
from unittest import mock

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import jersey_synth


class MakeSampleTest(unittest.TestCase):
    def test_shape_and_type(self):
        img = jersey_synth.make_sample(15, np.random.default_rng(1))
        self.assertEqual(img.shape, (jersey_synth.CROP_H, jersey_synth.CROP_W))
        self.assertEqual(img.dtype, np.uint8)

    def test_same_seed_same_pixels(self):
        a = jersey_synth.make_sample(66, np.random.default_rng(7))
        b = jersey_synth.make_sample(66, np.random.default_rng(7))
        np.testing.assert_array_equal(a, b)

    def test_no_number_class_renders(self):
        img = jersey_synth.make_sample(jersey_synth.NO_NUMBER, np.random.default_rng(3))
        self.assertEqual(img.shape, (jersey_synth.CROP_H, jersey_synth.CROP_W))

    def test_contrast_is_normalised(self):
        img = jersey_synth.make_sample(7, np.random.default_rng(5))
        self.assertGreater(int(img.max()) - int(img.min()), 100)

    def test_rejects_out_of_range_number(self):
        with self.assertRaises(ValueError):
            jersey_synth.make_sample(100, np.random.default_rng(0))


class BatchTest(unittest.TestCase):
    def test_labels_match_classes(self):
        x, y = jersey_synth.batch(64, np.random.default_rng(2))
        self.assertEqual(x.shape, (64, jersey_synth.CROP_H, jersey_synth.CROP_W))
        self.assertTrue(((y >= 0) & (y < jersey_synth.CLASSES)).all())
        self.assertIn(jersey_synth.NO_NUMBER, set(y.tolist()))


class FindFontsTest(unittest.TestCase):
    def test_missing_fonts_raise(self):
        fake = subprocess.CompletedProcess([], 0, stdout="Some Other Font|/nowhere/x.ttf", stderr="")
        with mock.patch("jersey_synth.subprocess.run", return_value=fake):
            jersey_synth.find_fonts.cache_clear()
            with self.assertRaises(jersey_synth.FontNotFound):
                jersey_synth.find_fonts()
        jersey_synth.find_fonts.cache_clear()

    def test_missing_fc_match_raises(self):
        with mock.patch("jersey_synth.subprocess.run", side_effect=FileNotFoundError("fc-match")):
            jersey_synth.find_fonts.cache_clear()
            with self.assertRaises(jersey_synth.FontNotFound):
                jersey_synth.find_fonts()
        jersey_synth.find_fonts.cache_clear()


if __name__ == "__main__":
    unittest.main()
