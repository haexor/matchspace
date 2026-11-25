import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import jersey_identity as ji

FPS = 25.0


def probs(**weights):
    """Wahrscheinlichkeiten über 100 Klassen: probs(n15=0.9) setzt Nummer 15, Rest gleich verteilt, keine = n0."""
    p = np.zeros(ji.CLASSES)
    for key, value in weights.items():
        p[int(key[1:])] = value
    rest = 1.0 - p.sum()
    p[p == 0] = rest / max(int((p == 0).sum()), 1)
    return p


def readings(track, frames, **weights):
    return [ji.Reading(track, f, probs(**weights), 1.0) for f in frames]


SPREAD = [0, 30, 60, 90, 120, 150]   # sechs Fenster über 6 s


class VoteTest(unittest.TestCase):
    def test_clear_readings_give_the_number(self):
        r = readings("own-1001", SPREAD, n15=0.9)
        result = ji.vote(r, {"own-1001": "own"}, FPS)
        self.assertEqual(result["own-1001"].number, 15)
        self.assertGreaterEqual(result["own-1001"].confidence, ji.MIN_CONFIDENCE)

    def test_six_or_nine_stays_unknown(self):
        r = readings("own-1001", SPREAD, n6=0.45, n9=0.45)
        self.assertIsNone(ji.vote(r, {"own-1001": "own"}, FPS)["own-1001"].number)

    def test_conflicting_readings_stay_unknown(self):
        r = readings("own-1001", SPREAD[:3], n6=0.9) + readings("own-1001", SPREAD[3:], n9=0.9)
        self.assertIsNone(ji.vote(r, {"own-1001": "own"}, FPS)["own-1001"].number)

    def test_one_window_is_not_enough(self):
        r = readings("own-1001", range(0, 8), n15=0.95)        # alle in einem 0,4-s-Fenster
        self.assertIsNone(ji.vote(r, {"own-1001": "own"}, FPS)["own-1001"].number)

    def test_windows_close_together_are_not_enough(self):
        r = readings("own-1001", [0, 10, 20], n15=0.95)        # drei Fenster, aber nur 0,8 s
        result = ji.vote(r, {"own-1001": "own"}, FPS)["own-1001"]
        self.assertEqual(result.windows, 3)
        self.assertIsNone(result.number)

    def test_no_number_readings_do_not_count(self):
        r = readings("own-1001", SPREAD, n0=0.6, n15=0.4)
        self.assertIsNone(ji.vote(r, {"own-1001": "own"}, FPS)["own-1001"].number)

    def test_many_sure_readings_count_even_when_unsure_windows_lean_the_other_way(self):
        # sechs Fenster mit 15 sicher, danach sechs Fenster, in denen 75 knapp vor 15 liegt (halb verdeckter Rücken)
        r = readings("opponent-1005", SPREAD, n15=0.9) + readings("opponent-1005", [180, 210, 240, 270, 300, 330], n75=0.45, n15=0.38)
        result = ji.vote(r, {"opponent-1005": "opponent"}, FPS)["opponent-1005"]
        self.assertLess(result.agreement, ji.MIN_AGREEMENT)       # nach der Mehrheit der Fenster allein bliebe sie unbekannt
        self.assertEqual(result.number, 15)

    def test_sure_readings_of_another_number_block_the_evidence_path(self):
        r = readings("own-1001", SPREAD, n15=0.9) + readings("own-1001", [180, 210, 240, 270, 300, 330], n7=0.9)
        self.assertIsNone(ji.vote(r, {"own-1001": "own"}, FPS)["own-1001"].number)

    def test_four_sure_windows_are_not_enough_evidence(self):
        r = readings("own-1001", SPREAD[:4], n15=0.9) + readings("own-1001", [180, 210, 240, 270, 300, 330], n75=0.45, n15=0.38)
        self.assertIsNone(ji.vote(r, {"own-1001": "own"}, FPS)["own-1001"].number)

    def test_squad_excludes_other_numbers(self):
        r = readings("own-1001", SPREAD, n15=0.8, n16=0.15)
        result = ji.vote(r, {"own-1001": "own"}, FPS, squad={"own": frozenset({16, 7})})
        self.assertNotEqual(result["own-1001"].number, 15)
        for number, _ in result["own-1001"].ranked:
            self.assertIn(number, {16, 7})

    def test_squad_of_other_team_does_not_apply(self):
        r = readings("opponent-1001", SPREAD, n15=0.9)
        result = ji.vote(r, {"opponent-1001": "opponent"}, FPS, squad={"own": frozenset({16})})
        self.assertEqual(result["opponent-1001"].number, 15)

    def test_referee_gets_no_number(self):
        r = readings("referee-1001", SPREAD, n15=0.95)
        result = ji.vote(r, {"referee-1001": "referee"}, FPS)
        self.assertNotIn("referee-1001", result)


class SquadTest(unittest.TestCase):
    def write(self, content):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        tmp.write(content if isinstance(content, str) else json.dumps(content))
        tmp.close()
        self.addCleanup(Path(tmp.name).unlink)
        return tmp.name

    def test_valid_list(self):
        squad = ji.load_squad(self.write({"own": [1, 7, 15], "opponent": []}))
        self.assertEqual(squad, {"own": frozenset({1, 7, 15})})

    def test_out_of_range(self):
        with self.assertRaises(ji.SquadError):
            ji.load_squad(self.write({"own": [100]}))

    def test_duplicates(self):
        with self.assertRaises(ji.SquadError):
            ji.load_squad(self.write({"own": [7, 7]}))

    def test_names_are_refused(self):
        with self.assertRaises(ji.SquadError):
            ji.load_squad(self.write({"own": [{"number": 7, "name": "Max"}]}))

    def test_unknown_key(self):
        with self.assertRaises(ji.SquadError):
            ji.load_squad(self.write({"own": [7], "names": ["Max"]}))

    def test_broken_json(self):
        with self.assertRaises(ji.SquadError):
            ji.load_squad(self.write("{own: [7"))


def tn(track, team, number, confidence=0.95):
    """Fertiges Abstimmungsergebnis mit gestützter Nummer."""
    return ji.TrackNumber(track, team, [(number, confidence), (number % 99 + 1, 1 - confidence)], 5, 3.0, 1.0)


def span(a, b):
    return set(range(a, b + 1))


def walk(spans, ends):
    """Lage je Bild: gerade von der ersten zur letzten Lage."""
    out = {}
    for t, frames in spans.items():
        fs = sorted(frames)
        a, b = ends[t]
        out[t] = {f: a + (b - a) * (i / max(len(fs) - 1, 1)) for i, f in enumerate(fs)}
    return out


def point(x, y=0.0):
    return np.array([float(x), float(y)])


class AssignTest(unittest.TestCase):
    def test_overlapping_tracks_do_not_share_a_number(self):
        votes = {"a": tn("a", "own", 7, 0.97), "b": tn("b", "own", 7, 0.92)}
        spans = {"a": span(0, 100), "b": span(50, 150)}
        self.assertEqual(ji.assign(votes, spans, FPS), {"a": 7, "b": None})

    def test_both_teams_may_wear_the_same_number(self):
        votes = {"a": tn("a", "own", 7), "b": tn("b", "opponent", 7)}
        spans = {"a": span(0, 100), "b": span(0, 100)}
        self.assertEqual(ji.assign(votes, spans, FPS), {"a": 7, "b": 7})

    def test_tracks_without_vote_stay_unknown(self):
        self.assertEqual(ji.assign({}, {"ref": span(0, 10)}, FPS), {"ref": None})

    def test_random_scenes_never_duplicate(self):
        rng = np.random.default_rng(11)
        for _ in range(50):
            votes, spans = {}, {}
            for k in range(20):
                track = f"t{k}"
                a = int(rng.integers(0, 600))
                spans[track] = span(a, a + int(rng.integers(10, 300)))
                votes[track] = tn(track, str(rng.choice(["own", "opponent"])), int(rng.integers(1, 6)),
                                  float(rng.uniform(0.9, 1.0)))
            numbers = ji.assign(votes, spans, FPS)
            for x in spans:
                for y in spans:
                    if x < y and numbers[x] is not None and numbers[x] == numbers[y] \
                            and votes[x].team == votes[y].team:
                        self.assertFalse(ji._overlap(spans[x], spans[y], FPS))


class InterleavedTest(unittest.TestCase):
    def test_interleaved_pieces_close_together_merge(self):
        votes = {"a": tn("a", "own", 9), "b": tn("b", "own", 9)}
        a = {f: point(0.05 * f) for f in list(range(0, 50)) + list(range(100, 150))}
        b = {f: point(0.05 * f + 0.3) for f in range(55, 95)}       # liegt in der Lücke von a
        players = ji.merge_by_number({"a": 9, "b": 9}, votes, {"a": a, "b": b}, {"a": "own", "b": "own"}, FPS)
        self.assertEqual(len(players), 1)


class HandOverTest(unittest.TestCase):
    def test_short_overlap_is_a_hand_over(self):
        votes = {"a": tn("a", "own", 7), "b": tn("b", "own", 7)}
        spans = {"a": span(0, 100), "b": span(95, 200)}            # 6 Bilder gleichzeitig: Übergabe
        self.assertEqual(ji.assign(votes, spans, FPS), {"a": 7, "b": 7})


class MergeTest(unittest.TestCase):
    def setUp(self):
        self.teams = {"a": "own", "b": "own", "c": "own"}

    def test_same_number_reachable_gap_becomes_one_player(self):
        votes = {"a": tn("a", "own", 15), "b": tn("b", "own", 15)}
        spans = {"a": span(0, 100), "b": span(150, 300)}                 # 2 s Lücke
        ends = {"a": (point(0), point(10)), "b": (point(14), point(20))}   # 4 m in 2 s
        players = ji.merge_by_number({"a": 15, "b": 15}, votes, walk(spans, ends), self.teams, FPS)
        self.assertEqual(len(players), 1)
        self.assertEqual(players[0].tracks, ["a", "b"])
        self.assertEqual((players[0].id, players[0].number), ("a", 15))

    def test_too_fast_is_not_merged(self):
        votes = {"a": tn("a", "own", 15, 0.99), "b": tn("b", "own", 15, 0.93)}
        spans = {"a": span(0, 100), "b": span(125, 300)}                 # 1 s Lücke
        ends = {"a": (point(0), point(0)), "b": (point(30), point(30))}    # 30 m in 1 s
        players = {p.id: p for p in ji.merge_by_number({"a": 15, "b": 15}, votes, walk(spans, ends), self.teams, FPS)}
        self.assertEqual(players["a"].number, 15)
        self.assertIsNone(players["b"].number)

    def test_unknown_tracks_are_never_merged(self):
        spans = {"a": span(0, 100), "b": span(150, 300)}
        ends = {"a": (point(0), point(0)), "b": (point(1), point(1))}
        players = ji.merge_by_number({"a": None, "b": None}, {}, walk(spans, ends), self.teams, FPS)
        self.assertEqual(len(players), 2)
        self.assertTrue(all(p.number is None for p in players))

    def weak(self, track, number, confidence=0.95, windows=2, agreement=0.6):
        return ji.TrackNumber(track, "own", [(number, confidence), (number % 99 + 1, 1 - confidence)], windows, 0.4, agreement)

    def test_weak_fragment_joins_known_player(self):
        votes = {"a": tn("a", "own", 15), "c": self.weak("c", 15)}
        spans = {"a": span(0, 100), "c": span(150, 200)}
        ends = {"a": (point(0), point(5)), "c": (point(7), point(9))}
        numbers = ji.assign(votes, spans, FPS)
        self.assertEqual(numbers, {"a": 15, "c": None})              # allein reicht es nicht für eine Nummer
        players = ji.merge_by_number(numbers, votes, walk(spans, ends), self.teams, FPS)
        self.assertEqual([(p.tracks, p.number) for p in players], [(["a", "c"], 15)])

    def test_weak_fragment_without_known_player_stays_unknown(self):
        votes = {"c": self.weak("c", 15)}
        players = ji.merge_by_number({"c": None}, votes, walk({"c": span(0, 50)}, {"c": (point(0), point(1))}), self.teams, FPS)
        self.assertIsNone(players[0].number)

    def test_weak_fragment_overlapping_stays_apart(self):
        votes = {"a": tn("a", "own", 15), "c": self.weak("c", 15)}
        spans = {"a": span(0, 100), "c": span(80, 200)}   # 0,8 s gleichzeitig
        ends = {"a": (point(0), point(5)), "c": (point(5), point(9))}
        players = ji.merge_by_number({"a": 15, "c": None}, votes, walk(spans, ends), self.teams, FPS)
        self.assertEqual(len(players), 2)

    def test_unclear_fragment_stays_apart(self):
        votes = {"a": tn("a", "own", 15), "c": self.weak("c", 15, agreement=0.3)}
        spans = {"a": span(0, 100), "c": span(150, 200)}
        ends = {"a": (point(0), point(5)), "c": (point(7), point(9))}
        self.assertEqual(len(ji.merge_by_number({"a": 15, "c": None}, votes, walk(spans, ends), self.teams, FPS)), 2)


if __name__ == "__main__":
    unittest.main()


class PlayerVoteTest(unittest.TestCase):
    """Nummern je Spieler: Die Lesungen aller Stücke eines Spielers stimmen gemeinsam ab (Szenario P3/1)."""

    def setUp(self):
        import jersey_reader
        self.reader = jersey_reader
        self.pieces = {"a": range(0, 25), "b": range(50, 75), "c": range(100, 125)}
        frames, box = [], []
        for k, fs in enumerate(self.pieces.values()):
            for f in (fs[0], fs[-1]):        # je Stück zwei Fenster
                frames.append(f)
                box.append(k)
        n = len(frames)
        self.scene = jersey_reader.SceneReadings(np.array(frames), np.zeros(n, np.int8), np.array(box),
                                                 np.tile(probs(n15=0.9), (n, 1)), np.full(n, 40.0, np.float32))

    def rows(self, k, fs):
        return {f: np.array([0, 0, 0, 0, 0, 0, 1, 1, k], float) for f in fs}

    def test_each_piece_alone_stays_unknown(self):
        tracks = {name: self.rows(k, fs) for k, (name, fs) in enumerate(self.pieces.items())}
        votes = ji.vote(self.reader.readings_for_tracks(self.scene, tracks), dict.fromkeys(tracks, "own"), FPS)
        self.assertTrue(all(v.number is None for v in votes.values()))

    def test_player_of_three_pieces_gets_the_number(self):
        player = {}
        for k, fs in enumerate(self.pieces.values()):
            player.update(self.rows(k, fs))
        votes = ji.vote(self.reader.readings_for_tracks(self.scene, {"own-1001": player}), {"own-1001": "own"}, FPS)
        self.assertEqual(votes["own-1001"].number, 15)
