"""Was ein Spieler zusätzlich trägt (tools/kit_player.py): Unterhemd, Handschuhe, Schuhfarbe aus den Kacheln seiner Textur."""
import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import kit_player

SKIN = np.array([200.0, 140.0, 110.0], np.float32)        # RGB


def arm_tile(sleeve_rgb=None, hand_rgb=None):
    """Unterarmkachel (BGR, 128 Zeilen): oben Ärmel oder Haut, unten das Handende."""
    t = np.zeros((128, 64, 3), np.uint8)
    t[:] = (sleeve_rgb if sleeve_rgb is not None else SKIN)[::-1]
    t[int(0.75 * 128):] = (hand_rgb if hand_rgb is not None else SKIN)[::-1]
    return t


def foot_tile(rgb):
    t = np.full((64, 64, 3), 245, np.uint8)               # heller Rand der Schuhkachel
    t[10:54, 10:54] = np.asarray(rgb, np.uint8)[::-1]
    return t


FEET = [foot_tile((30, 30, 30)), foot_tile((30, 30, 30))]


class VariantTest(unittest.TestCase):
    def test_bare_arms_and_hands_have_no_extra_layers(self):
        v = kit_player.variant_of([arm_tile(), arm_tile()], FEET, SKIN)
        self.assertIsNone(v["baseLayer"])
        self.assertIsNone(v["gloves"])

    def test_dark_sleeve_is_a_base_layer_with_bare_hands(self):
        sleeve = np.array([20.0, 20.0, 24.0])
        v = kit_player.variant_of([arm_tile(sleeve), arm_tile(sleeve)], FEET, SKIN)
        self.assertEqual(v["baseLayer"], "#141414")
        self.assertIsNone(v["gloves"])

    def test_gloves_over_bare_arms(self):
        glove = np.array([240.0, 240.0, 240.0])
        v = kit_player.variant_of([arm_tile(None, glove)] * 2, FEET, SKIN, detect_gloves=True)
        self.assertIsNone(v["baseLayer"])
        self.assertEqual(v["gloves"], "#f0f0f0")

    def test_gloves_over_a_base_layer_differ_from_the_sleeve(self):
        sleeve, glove = np.array([20.0, 20.0, 24.0]), np.array([60.0, 200.0, 60.0])
        v = kit_player.variant_of([arm_tile(sleeve, glove)] * 2, FEET, SKIN, detect_gloves=True)
        self.assertEqual(v["baseLayer"], "#141414")
        self.assertEqual(v["gloves"], "#3cc83c")

    def test_the_sleeve_continuing_over_the_hand_end_is_no_glove(self):
        sleeve = np.array([20.0, 20.0, 24.0])
        v = kit_player.variant_of([arm_tile(sleeve, sleeve)] * 2, FEET, SKIN, detect_gloves=True)
        self.assertIsNone(v["gloves"])

    def test_gloves_are_off_by_default(self):
        v = kit_player.variant_of([arm_tile(None, np.array([240.0, 240.0, 240.0]))] * 2, FEET, SKIN)
        self.assertIsNone(v["gloves"])

    def test_a_bright_non_skin_sleeve_is_no_base_layer(self):
        v = kit_player.variant_of([arm_tile(np.array([60.0, 160.0, 60.0]))] * 2, FEET, SKIN)      # helles Grün: Rasenmischung oder Ärmel des Trikots, kein dunkles Unterhemd
        self.assertIsNone(v["baseLayer"])

    def test_without_skin_colour_nothing_is_decided(self):
        v = kit_player.variant_of([arm_tile(np.array([20.0, 20.0, 24.0]))] * 2, FEET, None)
        self.assertIsNone(v["baseLayer"])
        self.assertIsNone(v["gloves"])

    def test_boot_colour_ignores_the_light_border(self):
        v = kit_player.variant_of([arm_tile()] * 2, [foot_tile((200, 30, 30))] * 2, SKIN)
        self.assertEqual(v["boots"], "#c81e1e")


if __name__ == "__main__":
    unittest.main()
