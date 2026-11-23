import json
import tempfile
import unittest
from pathlib import Path

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import own_match

GOOD = {"name": "U15, 2026-11-01",
        "teams": {"own": {"name": "Wir", "color": "#d7263d"}, "opponent": {"name": "Gegner", "color": "#1f9d55"},
                  "referee": {"name": "Schiedsrichter", "color": "#f2c200"}},
        "periods": [{"id": 1, "videoStartS": 126, "clockStartS": 0}, {"id": 2, "videoStartS": 3434, "clockStartS": 2400}]}


def write(tmp, data):
    path = Path(tmp) / "spiel.json"
    path.write_text(json.dumps(data))
    return path


class DescriptionTest(unittest.TestCase):
    def test_meta_without_movement_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            desc = own_match.load_description(write(tmp, GOOD))
            meta = own_match.build_meta(desc, {"length": 90.0, "width": 55.0})
        self.assertEqual(meta["frames"], 0)
        self.assertEqual(meta["entities"], [{"id": "ball", "kind": "ball"}])
        self.assertEqual((meta["pitch"]["length"], meta["pitch"]["width"]), (90.0, 55.0))
        self.assertEqual(meta["periods"][1]["videoStartS"], 3434)
        self.assertEqual(meta["teams"]["own"]["name"], "Wir")
        self.assertEqual(meta["source"]["name"], "U15, 2026-11-01")
        self.assertNotIn("file", json.dumps(meta["tracks"]).replace('"file": "tracks.bin"', ""))

    def test_invalid_descriptions_are_refused(self):
        bad = [dict(GOOD, teams={**GOOD["teams"], "own": {"name": "Wir", "color": "rot"}}),
               dict(GOOD, periods=list(reversed(GOOD["periods"]))),
               dict(GOOD, players=["Max Mustermann"]),
               {k: v for k, v in GOOD.items() if k != "periods"}]
        with tempfile.TemporaryDirectory() as tmp:
            for data in bad:
                with self.assertRaises(own_match.DescriptionError):
                    own_match.load_description(write(tmp, data))


class ClockTest(unittest.TestCase):
    def test_clock_of_a_scene(self):
        period, clock = own_match.period_at(GOOD["periods"], 705)
        self.assertEqual((period["id"], clock), (1, 0 + 705 - 126))
        period, clock = own_match.period_at(GOOD["periods"], 3500)
        self.assertEqual((period["id"], clock), (2, 2400 + 3500 - 3434))

    def test_before_kickoff_is_refused(self):
        with self.assertRaises(own_match.DescriptionError):
            own_match.period_at(GOOD["periods"], 60)


if __name__ == "__main__":
    unittest.main()
