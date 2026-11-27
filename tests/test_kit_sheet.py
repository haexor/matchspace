"""Kit-Blatt der Bild-KI (tools/kit_sheet.py): Prompt aus den Fakten der Mannschaft und der Rückennummer."""
import unittest

import cv2
import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import kit_sheet

TEAM = {"shirt": "green", "shorts": "white", "socks": "white", "backText": [], "extra": "black long undershirt sleeves"}


class PromptTest(unittest.TestCase):
    def test_colours_and_layout_are_in_the_prompt(self):
        p = kit_sheet.prompt_for(TEAM)
        self.assertIn("green shirt, white shorts, white socks", p)
        self.assertIn("separately", p)
        self.assertIn("no boots", p)

    def test_the_back_number_is_never_on_the_sheet(self):
        p = kit_sheet.prompt_for(TEAM)
        self.assertIn("no number", p)
        self.assertNotIn("player number", p)

    def test_back_text_comes_from_the_team_only(self):
        self.assertIn('"SV Eichen"', kit_sheet.prompt_for({**TEAM, "backText": ["SV Eichen"]}))
        self.assertNotIn("SV Eichen", kit_sheet.prompt_for(TEAM))

    def test_no_undershirt_gloves_or_boots_on_the_team_sheet(self):
        self.assertIn("Do not draw any undershirt, gloves or boots", kit_sheet.prompt_for(TEAM))


def sheet_with_items():
    """Blatt (1024 × 1024, hellgrauer Grund) mit sechs Stücken: je Zeile zwei, links und rechts."""
    img = np.full((1024, 1024, 3), 217, np.uint8)
    rows = [(20, 250), (330, 200), (680, 250)]
    for y, h in rows:
        cv2.rectangle(img, (180, y), (480, y + h), (40, 160, 40), -1)
        cv2.rectangle(img, (540, y), (840, y + h), (40, 40, 160), -1)
    return img


class BoxesTest(unittest.TestCase):
    def test_six_items_are_found_in_order(self):
        b = kit_sheet.boxes_of(sheet_with_items())
        self.assertEqual(len(b), 6)
        self.assertLess(b["shirtFront"][0], b["shirtBack"][0])           # vorn links, hinten rechts
        self.assertLess(b["shirtFront"][1], b["shortsFront"][1])          # Trikot über der Hose
        self.assertLess(b["shortsFront"][1], b["sockL"][1])

    def test_a_sheet_with_another_item_count_gives_none(self):
        img = sheet_with_items()
        cv2.rectangle(img, (10, 600), (60, 650), (0, 0, 0), -1)         # siebtes Stück
        self.assertIsNone(kit_sheet.boxes_of(img))

    def test_extended_edges_leave_no_background_grey_next_to_items(self):
        out = kit_sheet.extend_edges(sheet_with_items())
        self.assertTrue((np.abs(out[150, 150].astype(int) - np.array((217, 217, 217))) > 20).any())      # 30 px neben dem Stück: Stofffarbe, nicht Grund


def shirt_mask():
    """Trikot-Silhouette 300 × 280: Rumpf Spalten 70 bis 230, ab Zeile 12; Ärmel schräg nach unten außen bis Spalte 5."""
    m = np.zeros((280, 300), np.uint8)
    m[12:260, 70:230] = 1
    cv2.fillPoly(m, [np.array([[70, 12], [70, 90], [5, 115], [5, 75]], np.int32)], 1)         # linker Ärmel
    cv2.fillPoly(m, [np.array([[230, 12], [230, 90], [295, 115], [295, 75]], np.int32)], 1)   # rechter Ärmel
    return m.astype(bool)


class ShirtShapeTest(unittest.TestCase):
    def test_body_edges_and_top_in_fractions(self):
        s = kit_sheet.shirt_shape(shirt_mask())
        self.assertAlmostEqual(s["body"][0], 70 / 300, delta=0.01)
        self.assertAlmostEqual(s["body"][1], 229 / 300, delta=0.01)
        self.assertAlmostEqual(s["body"][2], 12 / 280, delta=0.01)

    def test_sleeve_seam_and_cuff(self):
        s = kit_sheet.shirt_shape(shirt_mask())
        self.assertAlmostEqual(s["sleeveS"][0], 70 / 300, delta=0.01)
        self.assertAlmostEqual(s["sleeveS"][1], 51 / 280, delta=0.06)       # Mitte des Ärmels an der Rumpfkante (Zeilen 12 bis 90)
        self.assertLess(s["sleeveC"][0], 0.07)                              # Bündchen ganz außen
        self.assertGreater(s["sleeveC"][1], s["sleeveS"][1])                # der Ärmel hängt nach unten

    def test_sleeve_height_is_taken_from_the_connected_run_not_from_outliers(self):
        m = shirt_mask()
        m[270:275, 60:75] = True                                      # Ausreißer (Fleck) weit unter dem Ärmel am Rand des Rumpfs
        s = kit_sheet.shirt_shape(m)
        self.assertAlmostEqual(s["sleeveW"][0], 80 / 280, delta=0.05)  # Ärmelhöhe am Ansatz: Zeilen 12 bis 90
        self.assertLess(s["sleeveW"][1], s["sleeveW"][0])              # am Bündchen kürzer als am Ansatz
        self.assertAlmostEqual(s["sleeveS"][1], 51 / 280, delta=0.06)

    def test_a_shirt_without_sleeves_gives_none(self):
        m = np.zeros((280, 300), bool)
        m[12:260, 70:230] = True
        self.assertIsNone(kit_sheet.shirt_shape(m))


def shorts_mask():
    """Hose 200 × 160: oben 100 breit (Spalten 50 bis 150), unten 190 breit (Spalten 5 bis 195)."""
    m = np.zeros((160, 200), np.uint8)
    cv2.fillPoly(m, [np.array([[50, 0], [150, 0], [195, 159], [5, 159]], np.int32)], 1)
    return m.astype(bool)


class ShortsShapeTest(unittest.TestCase):
    def test_the_waist_is_narrower_than_the_hem(self):
        rows = kit_sheet.shorts_shape(shorts_mask())
        self.assertEqual(len(rows), kit_sheet.SHORTS_ROWS)
        self.assertGreater(rows[0][0], rows[-1][0] + 0.1)             # Bund: linker Rand weiter innen
        self.assertLess(rows[0][1], rows[-1][1] - 0.1)
        self.assertTrue(all(0 <= lo < hi <= 1 for lo, hi in rows))

    def test_an_empty_row_gives_none(self):
        m = shorts_mask()
        m[40:80] = False
        self.assertIsNone(kit_sheet.shorts_shape(m))


class SpeckTest(unittest.TestCase):
    def sheet(self):
        img = np.full((1024, 1024, 3), 217, np.uint8)
        for (x, y, w, h) in [(106, 22, 400, 380), (519, 22, 400, 380), (156, 428, 300, 250), (564, 428, 300, 250), (315, 694, 140, 300), (565, 694, 140, 300)]:
            cv2.rectangle(img, (x, y), (x + w, y + h), (40, 40, 160), -1)
        return img

    def boxes(self, img):
        return kit_sheet.boxes_of(img)

    def test_a_small_white_label_on_the_shorts_is_removed(self):
        img = self.sheet()
        cv2.rectangle(img, (400, 600), (420, 608), (255, 255, 255), -1)
        out = kit_sheet.remove_specks(img, self.boxes(img))
        self.assertLess(int(out[604, 410].astype(int).sum()), 3 * 120)      # wieder Stoff statt Weiß

    def test_a_small_dark_label_on_light_shorts_is_removed(self):
        img = self.sheet()
        cv2.rectangle(img, (156, 428), (456, 678), (235, 235, 235), -1)       # weiße Hose
        cv2.rectangle(img, (400, 600), (420, 608), (10, 10, 10), -1)
        out = kit_sheet.remove_specks(img, self.boxes(img))
        self.assertGreater(int(out[604, 410].astype(int).sum()), 3 * 150)

    def test_a_long_stripe_stays(self):
        img = self.sheet()
        cv2.rectangle(img, (106, 100), (506, 112), (255, 255, 255), -1)       # Streifen über das ganze Trikot
        out = kit_sheet.remove_specks(img, self.boxes(img))
        self.assertGreater(int(out[106, 300].astype(int).sum()), 3 * 240)


if __name__ == "__main__":
    unittest.main()
