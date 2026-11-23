import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import jersey_eval
import jersey_reader
import reference as ref
import track_players

FPS = 25


def frames(ref, a, b):
    return {f: ref for f in range(a, b)}


class WrongTimeTest(unittest.TestCase):
    def test_share_of_frames_not_on_main_person(self):
        matched = {"own-1001": {**frames(("own", 7), 0, 80), **frames(("own", 8), 80, 100)}}
        self.assertAlmostEqual(jersey_eval.wrong_time_share(matched), 0.2)

    def test_unmatched_frames_do_not_count(self):
        matched = {"a": {**frames(("own", 7), 0, 50), **frames(None, 50, 100)}, "b": frames(None, 0, 10)}
        self.assertEqual(jersey_eval.wrong_time_share(matched), 0.0)

    def test_over_all_players(self):
        matched = {"a": {**frames(("own", 7), 0, 90), **frames(("own", 8), 90, 100)}, "b": frames(("own", 9), 0, 100)}
        self.assertAlmostEqual(jersey_eval.wrong_time_share(matched), 0.05)


class SwitchesTest(unittest.TestCase):
    def test_lasting_change_counts(self):
        matched = {"a": {**frames(("own", 7), 0, 50), **frames(("own", 8), 50, 100)}}
        self.assertEqual(jersey_eval.switches(matched, FPS), 1)

    def test_short_change_does_not_count(self):
        matched = {"a": {**frames(("own", 7), 0, 50), **frames(("own", 8), 50, 60), **frames(("own", 7), 60, 100)}}
        self.assertEqual(jersey_eval.switches(matched, FPS), 0)

    def test_there_and_back_counts_twice(self):
        matched = {"a": {**frames(("own", 7), 0, 50), **frames(("own", 8), 50, 100), **frames(("own", 7), 100, 150)}}
        self.assertEqual(jersey_eval.switches(matched, FPS), 2)


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


BOX = [10, 10, 20, 40]


def identity(numbers=None):
    """a und b (wir) laufen 0–99, c (Gegner) 0–99; bei Bild 50 kreuzen sich a und b."""
    numbers = numbers or {}
    return {"fps": FPS, "stamp": "x", "players": {
        name: {"team": team, "keeper": False, "number": numbers.get(name),
               "detections": [[f, 0, box] for f in range(100)]}
        for name, team, box in (("a", "own", 0), ("b", "own", 1), ("c", "opponent", 2))}}


def swap_spot():
    part = lambda player, letter, f, box: ref.Participant(player, letter, [f, 0, box, *BOX], {})  # noqa: E731
    return ref.Spot("s1", ["occlusion"], 50, 35, 65, 0, [0, 0, 64, 64],
                    [part("a", "A", 49, 0), part("b", "B", 49, 1)], [part("a", "A", 50, 0), part("b", "B", 50, 1)],
                    {"A": "A", "B": "B"}, 2.0)


def answer(spot, choice, numbers=None, mapping=None, repeat=False):
    return ref.Answer(spot, choice, mapping or {}, numbers or {}, {}, "t", repeat)


class ReferenceMetricsTest(unittest.TestCase):
    def test_swap_confirmed_by_the_user_counts_as_wrong_time(self):
        ident, spot = identity(), swap_spot()
        persons = ref.persons(ident, [spot], [answer("s1", "swapped")])
        m = jersey_eval.identity_metrics(jersey_eval.own_matched(ident, persons), FPS)
        self.assertEqual(m["identitiesPerPerson"], 1.67)       # zwei Personen auf je zwei Spielern, c auf einem
        self.assertAlmostEqual(m["wrongTimeShare"], 100 / 300, places=4)
        self.assertEqual(m["switches"], 2)

    def test_proposal_confirmed_is_clean(self):
        ident, spot = identity(), swap_spot()
        persons = ref.persons(ident, [spot], [answer("s1", "proposed")])
        m = jersey_eval.identity_metrics(jersey_eval.own_matched(ident, persons), FPS)
        self.assertEqual((m["identitiesPerPerson"], m["wrongTimeShare"], m["switches"]), (1.0, 0.0, 0))

    def test_open_spot_excludes_the_frames_after(self):
        ident, spot = identity(), swap_spot()
        matched = jersey_eval.own_matched(ident, ref.persons(ident, [spot], []))
        self.assertIsNone(matched["a"][60])
        self.assertIsNotNone(matched["a"][40])

    def test_numbers_against_user_numbers(self):
        ident, spot = identity({"a": 7, "b": 9}), swap_spot()
        persons = ref.persons(ident, [spot], [answer("s1", "proposed", {"A": 7, "B": 8})])
        r = jersey_eval.number_report(ident, jersey_eval.own_matched(ident, persons), persons, FPS)
        self.assertEqual(r["teams"]["own"], {"persons": 2, "correct": 1, "wrong": 1, "unknown": 0})
        self.assertEqual(r["teams"]["opponent"]["persons"], 1)
        self.assertEqual([w["player"] for w in r["wrongPlayers"]], ["b"])


class CoverageTest(unittest.TestCase):
    def test_counts_controls_and_repeats(self):
        part = lambda player, letter, f: ref.Participant(player, letter, [f, 0, 2, *BOX], {})  # noqa: E731
        control = ref.Spot("k1", ["control"], 70, 55, 85, 0, [0, 0, 1, 1], [part("c", "A", 69)], [part("c", "A", 70)], {"A": "A"}, 0.5)
        spots = [swap_spot(), control]
        answers = [answer("s1", "unclear"), answer("k1", "mapped", mapping={"A": "other"}),
                   answer("k1", "mapped", mapping={"A": "other"}, repeat=True), answer("gone", "proposed")]
        c = jersey_eval.coverage(spots, answers, ref.persons(identity(), spots, answers))
        self.assertEqual((c["spots"], c["decided"], c["unclear"], c["open"], c["orphaned"]), (2, 1, 1, 0, 1))
        self.assertEqual(c["control"], {"spots": 1, "answered": 1, "errorsFound": 1, "missedRateEstimate": 1.0})
        self.assertEqual(c["repeat"], {"spots": 1, "agree": 1})
        self.assertEqual((c["auto"], c["byHand"]), (0, 2))

    def test_automatic_answers_are_counted_apart(self):
        spots = [swap_spot()]
        auto = ref.Answer("s1", "proposed", {}, {}, {}, "t", False, "auto")
        c = jersey_eval.coverage(spots, [auto], ref.persons(identity(), spots, [auto]))
        self.assertEqual((c["decided"], c["auto"], c["byHand"], c["open"]), (1, 1, 0, 0))


class DisagreementTest(unittest.TestCase):
    def test_switch_only_seen_by_veo_is_listed(self):
        own = {"a": frames("P1", 0, 100)}
        veo = {"a": {**frames(("own", 7), 0, 50), **frames(("own", 8), 50, 100)}}
        d = jersey_eval.disagreements(own, veo, FPS)
        self.assertEqual([(x["player"], x["seenBy"], x["frame"]) for x in d], [("a", "veo", 50)])

    def test_same_switch_is_no_disagreement(self):
        own = {"a": {**frames("P1", 0, 50), **frames("P2", 52, 100)}}
        veo = {"a": {**frames(("own", 7), 0, 50), **frames(("own", 8), 50, 100)}}
        self.assertEqual(jersey_eval.disagreements(own, veo, FPS), [])


class WithoutVeoTest(unittest.TestCase):
    def test_veo_code_is_not_loaded(self):
        import json
        import subprocess
        import sys
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            det = Path(tmp) / "scene.det.json"
            det.write_text("{}")
            Path(f"{det}.identity.json").write_text(json.dumps(identity()))
            Path(f"{det}.reference.json").write_text(json.dumps(ref.to_json("scene", "x", [swap_spot()], [answer("s1", "proposed")], 1)))
            code = ("import sys; sys.path.insert(0, %r); import jersey_eval; jersey_eval.main([%r, 'cam.json']); "
                    "print('veo_tracks' in sys.modules, 'track_players' in sys.modules)") % (str(helpers.TOOLS), str(det))
            out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
        self.assertTrue(out.strip().endswith("False False"), out)


if __name__ == "__main__":
    unittest.main()
