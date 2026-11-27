"""Kit-Blatt der Bild-KI (tools/kit_sheet.py): Prompt aus den Fakten der Mannschaft und der Rückennummer."""
import unittest

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


if __name__ == "__main__":
    unittest.main()
