import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import jersey_eval
import jersey_reader
import track_players

FPS = 25


def frames(ref, a, b):
    return {f: ref for f in range(a, b)}


class EvaluateTest(unittest.TestCase):
    def test_counts_correct_wrong_unknown(self):
        matched = {"own-7": frames(("own", 7), 0, 100), "own-9": frames(("own", 8), 0, 100),
                   "own-1001": frames(("own", 5), 0, 100), "opponent-3": frames(("opponent", 3), 0, 100)}
        numbers = {"own-7": 7, "own-9": 9, "own-1001": None, "opponent-3": 3}
        teams = {k: k.split("-")[0] for k in numbers}
        visible = {("own", 7), ("own", 8), ("own", 5), ("opponent", 3)}
        r = jersey_eval.evaluate(numbers, teams, matched, visible, FPS)
        self.assertEqual(r["teams"]["own"], {"visible": 3, "correct": 1, "wrong": 1, "unknown": 1})
        self.assertEqual(r["teams"]["opponent"], {"visible": 1, "correct": 1, "wrong": 0, "unknown": 0})
        self.assertEqual([m["player"] for m in r["wrongPlayers"]], ["own-9"])

    def test_only_visible_backs_count(self):
        matched = {"own-7": frames(("own", 7), 0, 100)}
        r = jersey_eval.evaluate({"own-7": 7}, {"own-7": "own"}, matched, set(), FPS)
        self.assertEqual(r["teams"]["own"]["visible"], 0)

    def test_identities_need_one_second(self):
        matched = {"own-1001": frames(("own", 7), 0, 100), "own-1002": frames(("own", 7), 100, 110),
                   "own-1003": frames(("own", 7), 200, 300)}
        numbers = dict.fromkeys(matched)
        teams = dict.fromkeys(matched, "own")
        r = jersey_eval.evaluate(numbers, teams, matched, set(), FPS)
        self.assertEqual(r["identitiesPerPlayer"], 2.0)   # own-1002 nur 0,4 s


class DuplicateTest(unittest.TestCase):
    def test_same_number_same_time_is_counted(self):
        present = {"a": set(range(0, 10)), "b": set(range(5, 20)), "c": set(range(0, 20))}
        numbers = {"a": 7, "b": 7, "c": 7}
        teams = {"a": "own", "b": "own", "c": "opponent"}
        self.assertEqual(jersey_eval.duplicate_frames(present, numbers, teams), 5)

    def test_unknown_numbers_never_duplicate(self):
        present = {"a": {1, 2}, "b": {1, 2}}
        self.assertEqual(jersey_eval.duplicate_frames(present, {"a": None, "b": None}, {"a": "own", "b": "own"}), 0)


class MatchReferenceTest(unittest.TestCase):
    def test_nearest_within_gate(self):
        truth = [{("own", 7): np.array([0.0, 0.0]), ("own", 8): np.array([5.0, 0.0])}]
        got = track_players.match_reference({"t": {0: (0.5, 0.0)}, "u": {0: (2.6, 0.0)}}, truth)
        self.assertEqual(got, {"t": {0: ("own", 7)}, "u": {0: None}})


class ReportFolderTest(unittest.TestCase):
    def test_report_outside_data_work_is_refused(self):
        with self.assertRaises(ValueError):
            jersey_reader.check_private_dir("web/data/bericht.json")


if __name__ == "__main__":
    unittest.main()
