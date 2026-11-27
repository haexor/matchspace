"""Kit-Blatt der Bild-KI (tools/kit_sheet.py): Prompt aus den Fakten der Mannschaft und der Rückennummer."""
import unittest

import cv2
import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import kit_sheet

TEAM = {"shirt": "green", "shorts": "white", "socks": "white", "backText": [], "extra": "black long undershirt sleeves"}


class PromptTest(unittest.TestCase):
    def test_colours_and_layout_are_in_the_prompt(self):
        p = kit_sheet.prompt_for(TEAM, "7")
        self.assertIn("green shirt, white shorts, white socks", p)
        self.assertIn("separately", p)
        self.assertIn("separate from the boots", p)

    def test_back_number_only_when_known(self):
        self.assertIn('the player number "7"', kit_sheet.prompt_for(TEAM, "7"))
        plain = kit_sheet.prompt_for(TEAM, "?")
        self.assertIn("plain, without any print", plain)
        self.assertNotIn("player number", plain)

    def test_back_text_comes_from_the_team_only(self):
        p = kit_sheet.prompt_for({**TEAM, "backText": ["SV Eichen"]}, "7")
        self.assertIn('"SV Eichen"', p)
        self.assertNotIn("SV Eichen", kit_sheet.prompt_for(TEAM, "7"))

    def test_undershirt_is_a_separate_layer(self):
        self.assertIn("separate long-sleeved base layer", kit_sheet.prompt_for(TEAM, "7"))
        self.assertNotIn("base layer", kit_sheet.prompt_for({**TEAM, "extra": ""}, "7"))


def sheet_with_items():
    """Blatt (1024 × 1024, hellgrauer Grund) mit zehn Stücken: je Zeile zwei, links und rechts."""
    img = np.full((1024, 1024, 3), 217, np.uint8)
    rows = [(20, 250), (300, 200), (530, 160), (714, 180), (928, 70)]
    for y, h in rows:
        cv2.rectangle(img, (180, y), (480, y + h), (40, 160, 40), -1)
        cv2.rectangle(img, (540, y), (840, y + h), (40, 40, 160), -1)
    return img


class BoxesTest(unittest.TestCase):
    def test_ten_items_are_found_in_order(self):
        b = kit_sheet.boxes_of(sheet_with_items())
        self.assertEqual(len(b), 10)
        self.assertLess(b["shirtFront"][0], b["shirtBack"][0])           # vorn links, hinten rechts
        self.assertLess(b["shirtFront"][1], b["underFront"][1])           # Trikot über dem Unterhemd
        self.assertLess(b["shortsFront"][1], b["sockL"][1])
        self.assertLess(b["sockL"][1], b["bootL"][1])

    def test_a_sheet_with_another_item_count_gives_none(self):
        img = sheet_with_items()
        cv2.rectangle(img, (10, 600), (60, 650), (0, 0, 0), -1)         # elftes Stück
        self.assertIsNone(kit_sheet.boxes_of(img))

    def test_extended_edges_leave_no_background_grey_next_to_items(self):
        out = kit_sheet.extend_edges(sheet_with_items())
        self.assertTrue((np.abs(out[150, 150].astype(int) - np.array((217, 217, 217))) > 20).any())      # 30 px neben dem Stück: Stofffarbe, nicht Grund


if __name__ == "__main__":
    unittest.main()
