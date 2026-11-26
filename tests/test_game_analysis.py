import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import game_analysis as ga


def scene(positions, contacts=(), teams=None):
    """positions: Name -> (x, y) für ein einziges Bild; Name 'ball' ist der Ball. Mannschaft aus dem Präfix (own-, opponent-)."""
    names = list(positions)
    ents = [{"id": n, "kind": "ball" if n == "ball" else "player", "team": None if n == "ball" else n.split("-")[0]} for n in names]
    xy = np.array([[positions[n] for n in names]], float)
    meta = {"entities": ents, "fps": 25, "pitch": {"length": 90.0, "width": 55.0}, "ballContacts": list(contacts), "frames": 1}
    return ga.Scene(meta, xy)


class OffsideTest(unittest.TestCase):
    def base(self, runner_x):
        return scene({"own-1": (10, 0), "own-2": (runner_x, 5), "opponent-1": (20, 0), "opponent-2": (30, -3), "opponent-3": (40, 3), "ball": (10, 0)})

    def test_attacker_beyond_second_last_defender_is_offside(self):
        o = ga.offside_positions(self.base(36), 0, 0, +1)           # vorletzter Gegner bei x=30
        runner = next(p for p in o["players"] if p["id"] == "own-2")
        self.assertTrue(runner["offside"])
        self.assertAlmostEqual(runner["margin"], 6.0)

    def test_level_with_second_last_defender_is_onside(self):
        o = ga.offside_positions(self.base(29), 0, 0, +1)
        self.assertFalse(next(p for p in o["players"] if p["id"] == "own-2")["offside"])

    def test_close_call_is_marked(self):
        o = ga.offside_positions(self.base(30.2), 0, 0, +1)
        p = next(p for p in o["players"] if p["id"] == "own-2")
        self.assertTrue(p["offside"] and p["close"])

    def test_attack_direction_flips_the_line(self):
        s = scene({"own-1": (-10, 0), "own-2": (-36, 5), "opponent-1": (-20, 0), "opponent-2": (-30, -3), "opponent-3": (-40, 3), "ball": (-10, 0)})
        o = ga.offside_positions(s, 0, 0, -1)
        self.assertTrue(next(p for p in o["players"] if p["id"] == "own-2")["offside"])

    def test_own_half_is_never_offside(self):
        s = scene({"own-1": (-30, 0), "own-2": (-20, 5), "opponent-1": (-10, 0), "opponent-2": (-5, -3), "ball": (-30, 0)})
        o = ga.offside_positions(s, 0, 0, +1)
        self.assertFalse(next(p for p in o["players"] if p["id"] == "own-2")["offside"])

    def test_ball_ahead_of_everyone_sets_the_line(self):
        s = scene({"own-1": (10, 0), "own-2": (35, 5), "opponent-1": (20, 0), "opponent-2": (30, -3), "ball": (38, 0)})
        o = ga.offside_positions(s, 0, 0, +1)
        self.assertFalse(next(p for p in o["players"] if p["id"] == "own-2")["offside"])

    def test_fewer_than_two_defenders_gives_no_verdict(self):
        s = scene({"own-1": (10, 0), "own-2": (36, 5), "opponent-1": (20, 0), "ball": (10, 0)})
        self.assertIsNone(ga.offside_positions(s, 0, 0, +1))


class LaneTest(unittest.TestCase):
    def test_open_goal_is_fully_free(self):
        s = scene({"own-1": (30, 0), "opponent-1": (10, 10), "ball": (30, 0)})
        lane = ga.free_lane(s, 0, 0, +1)
        self.assertAlmostEqual(lane["free"], 1.0)
        self.assertAlmostEqual(lane["gapWidth"], 7.32, places=1)

    def test_defender_in_front_blocks_part_of_the_goal(self):
        s = scene({"own-1": (30, 0), "opponent-1": (33, 0), "ball": (30, 0)})   # Gegner 3 m vor dem Ball
        lane = ga.free_lane(s, 0, 0, +1)
        self.assertLess(lane["free"], 0.7)
        self.assertGreater(lane["free"], 0.2)

    def test_defender_behind_the_ball_blocks_nothing(self):
        s = scene({"own-1": (30, 0), "opponent-1": (20, 0), "ball": (30, 0)})
        self.assertAlmostEqual(ga.free_lane(s, 0, 0, +1)["free"], 1.0)

    def test_keeper_in_the_zone_is_seen(self):
        s = scene({"own-1": (30, 0), "opponent-1": (44, 1), "ball": (30, 0)})
        self.assertTrue(ga.free_lane(s, 0, 0, +1)["keeperSeen"])
        s = scene({"own-1": (30, 0), "opponent-1": (10, 1), "ball": (30, 0)})
        self.assertFalse(ga.free_lane(s, 0, 0, +1)["keeperSeen"])

    def test_far_from_goal_is_not_rated(self):
        s = scene({"own-1": (0, 0), "ball": (0, 0)})
        self.assertIsNone(ga.free_lane(s, 0, 0, +1))

    def test_gaps(self):
        free, best = ga._gaps(0.0, 1.0, [(0.2, 0.4), (0.3, 0.5)])
        self.assertAlmostEqual(free, 0.7)
        self.assertEqual(best, (0.5, 1.0))


class AnalyseTest(unittest.TestCase):
    def test_involved_offside_player_gives_a_verdict(self):
        s = scene({"own-1": (10, 0), "own-2": (36, 5), "opponent-1": (20, 0), "opponent-2": (30, -3), "ball": (10, 0)},
                  contacts=[{"frame": 0, "kind": "pass", "player": "own-1"}, {"frame": 0, "kind": "touch", "player": "own-2"}])
        s.meta["ballContacts"][1]["frame"] = 0
        out = ga.analyse(s, {"own": 1, "opponent": -1})
        self.assertEqual(out["rows"][0]["offside"]["verdict"], "offside")

    def test_not_involved_means_onside_verdict(self):
        s = scene({"own-1": (10, 0), "own-2": (36, 5), "opponent-1": (20, 0), "opponent-2": (30, -3), "ball": (10, 0)},
                  contacts=[{"frame": 0, "kind": "pass", "player": "own-1"}])
        self.assertEqual(ga.analyse(s, {"own": 1})["rows"][0]["offside"]["verdict"], "onside")

    def test_offside_player_can_be_involved_after_another_teammate(self):
        s = scene({"own-1": (10, 0), "own-2": (36, 5), "own-3": (15, 4),
                   "opponent-1": (20, 0), "opponent-2": (30, -3), "ball": (10, 0)},
                  contacts=[{"frame": 0, "kind": "pass", "player": "own-1"},
                            {"frame": 1, "kind": "touch", "player": "own-3"},
                            {"frame": 2, "kind": "touch", "player": "own-2"}])
        result = ga.analyse(s, {"own": 1})["rows"][0]["offside"]
        runner = next(p for p in result["players"] if p["id"] == "own-2")
        self.assertTrue(runner["involved"])
        self.assertEqual(result["verdict"], "offside")

    def test_throw_in_contact_is_not_rated(self):
        s = scene({"own-1": (10, 0), "opponent-1": (20, 0), "opponent-2": (30, 0), "ball": (10, 0)},
                  contacts=[{"frame": 0, "kind": "pass", "player": "own-1"}])
        s.meta["events"] = [{"kind": "throw-in", "frame": 1}]
        self.assertEqual(ga.analyse(s, {"own": 1})["rows"], [])

    def test_lane_is_unused_only_with_keeper_seen(self):
        pos = {"own-1": (30, 0), "opponent-1": (44, 0), "opponent-2": (20, 0), "ball": (30, 0)}
        c = [{"frame": 0, "kind": "pass", "player": "own-1"}]
        self.assertTrue(ga.analyse(scene(pos, c), {"own": 1})["rows"][0]["shotLane"]["unused"])   # Torwart gesehen, Bahn größtenteils frei, kein Schuss
        pos["opponent-1"] = (10, 0)
        self.assertFalse(ga.analyse(scene(pos, c), {"own": 1})["rows"][0]["shotLane"]["unused"])

    def test_unknown_direction_skips_the_team(self):
        s = scene({"own-1": (10, 0), "opponent-1": (20, 0), "opponent-2": (30, 0), "ball": (10, 0)},
                  contacts=[{"frame": 0, "kind": "pass", "player": "own-1"}])
        self.assertEqual(ga.analyse(s, {"opponent": -1})["rows"], [])

    def test_load_reads_tracks(self):
        with tempfile.TemporaryDirectory() as tmp:
            meta = {"entities": [{"id": "own-1", "kind": "player", "team": "own"}], "fps": 25, "frames": 2, "pitch": {"length": 90, "width": 55},
                    "tracks": {"file": "tracks.bin", "scale": 0.01, "missing": -32768}}
            Path(tmp, "meta.json").write_text(json.dumps(meta))
            np.array([[[1000, -250, 0]], [[-32768, -32768, 0]]], dtype="<i2").tofile(Path(tmp, "tracks.bin"))
            s = ga.load(tmp)
            np.testing.assert_allclose(s.xy[0, 0], [10.0, -2.5])
            self.assertTrue(np.isnan(s.xy[1, 0]).all())


if __name__ == "__main__":
    unittest.main()
