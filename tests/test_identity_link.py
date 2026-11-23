import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import identity_link as il

FPS = 25


def run(a: int, b: int, start, speed=(2.0, 0.0)) -> dict[int, tuple[float, float]]:
    """Gerade Bahn von Bild a bis b-1, Start start (m), Tempo speed (m/s)."""
    return {f: (start[0] + speed[0] * (f - a) / FPS, start[1] + speed[1] * (f - a) / FPS) for f in range(a, b)}


def piece(name, frames, team="own", keeper=False):
    return il.Piece(name, team, keeper, frames)


def groups(result):
    return sorted(sorted(g) for g in result)


class LinkTest(unittest.TestCase):
    def test_single_reachable_candidate_is_linked(self):
        a = piece("a", run(0, 50, (0, 0)))                 # endet bei x = 4 m, 2 m/s
        b = piece("b", run(100, 150, (8.5, 0)))            # 2 s später, dort, wo a hinläuft
        self.assertEqual(groups(il.link([a, b], {}, {}, FPS)), [["a", "b"]])

    def test_unreachable_is_not_linked(self):
        a = piece("a", run(0, 50, (0, 0)))
        b = piece("b", run(75, 125, (44, 0)))              # 40 m in 1 s
        self.assertEqual(groups(il.link([a, b], {}, {}, FPS)), [["a"], ["b"]])

    def test_long_overlap_is_never_linked(self):
        a = piece("a", run(0, 50, (0, 0)))
        b = piece("b", run(30, 80, (2.4, 0)))              # 0,8 s gleichzeitig
        self.assertEqual(groups(il.link([a, b], {}, {}, FPS)), [["a"], ["b"]])

    def test_short_overlap_is_a_handover(self):
        a = piece("a", run(0, 50, (0, 0)))
        b = piece("b", run(45, 100, (3.6, 0)))             # 0,2 s gleichzeitig, an derselben Stelle
        self.assertEqual(groups(il.link([a, b], {}, {}, FPS)), [["a", "b"]])

    def test_piece_inside_a_hole_of_another_is_not_linked(self):
        a = piece("a", {**run(0, 50, (0, 0)), **run(150, 200, (8, 0))})   # Lücke von Bild 50 bis 150
        b = piece("b", run(60, 140, (4.4, 0)))
        self.assertEqual(groups(il.link([a, b], {}, {}, FPS)), [["a"], ["b"]])

    def test_two_similar_candidates_stay_apart(self):
        a = piece("a", run(0, 50, (0, 0)))
        b = piece("b", run(100, 150, (8.5, 0.6)))
        c = piece("c", run(100, 150, (8.5, -0.6)))
        self.assertEqual(groups(il.link([a, b, c], {}, {}, FPS)), [["a"], ["b"], ["c"]])

    def test_clearly_better_candidate_wins(self):
        a = piece("a", run(0, 50, (0, 0)))
        b = piece("b", run(100, 150, (8.5, 0)))
        c = piece("c", run(100, 150, (8.5, 9)))
        self.assertEqual(groups(il.link([a, b, c], {}, {}, FPS)), [["a", "b"], ["c"]])

    def test_appearance_decides_between_close_candidates(self):
        a = piece("a", run(0, 50, (0, 0)))
        b = piece("b", run(100, 150, (8.5, 0.6)))
        c = piece("c", run(100, 150, (8.5, -0.6)))
        red, blue = np.eye(4)[0], np.eye(4)[1]
        looks = {"a": il.Look(red, 50, 1.3), "b": il.Look(red, 50, 1.3), "c": il.Look(blue, 50, 1.3)}
        self.assertEqual(groups(il.link([a, b, c], looks, {}, FPS)), [["a", "b"], ["c"]])

    def test_uncertain_look_does_not_count(self):
        a = piece("a", run(0, 50, (0, 0)))
        b = piece("b", run(100, 150, (8.5, 0.6)))
        c = piece("c", run(100, 150, (8.5, -0.6)))
        red, blue = np.eye(4)[0], np.eye(4)[1]
        looks = {"a": il.Look(red, 3, 1.3), "b": il.Look(red, 3, 1.3), "c": il.Look(blue, 3, 1.3)}
        self.assertEqual(groups(il.link([a, b, c], looks, {}, FPS)), [["a"], ["b"], ["c"]])


class ForbiddenTest(unittest.TestCase):
    def setUp(self):
        self.a = run(0, 50, (0, 0))
        self.b = run(100, 150, (8.5, 0))

    def test_different_sure_numbers(self):
        got = il.link([piece("a", self.a), piece("b", self.b)], {}, {"a": 7, "b": 9}, FPS)
        self.assertEqual(groups(got), [["a"], ["b"]])

    def test_other_team(self):
        got = il.link([piece("a", self.a), piece("b", self.b, team="opponent")], {}, {}, FPS)
        self.assertEqual(groups(got), [["a"], ["b"]])

    def test_keeper_and_field_player(self):
        got = il.link([piece("a", self.a, keeper=True), piece("b", self.b)], {}, {}, FPS)
        self.assertEqual(groups(got), [["a"], ["b"]])

    def test_referees_are_never_linked(self):
        got = il.link([piece("a", self.a, team="referee"), piece("b", self.b, team="referee")], {}, {}, FPS)
        self.assertEqual(groups(got), [["a"], ["b"]])


class NumberTest(unittest.TestCase):
    def test_same_number_links_over_long_gap(self):
        a = piece("a", run(0, 50, (0, 0)))
        b = piece("b", run(300, 350, (60, 0)))             # 10 s, 56 m: erreichbar, aber weit weg vom erwarteten Ort
        self.assertEqual(groups(il.link([a, b], {}, {}, FPS)), [["a"], ["b"]])
        self.assertEqual(groups(il.link([a, b], {}, {"a": 7, "b": 7}, FPS)), [["a", "b"]])

    def test_same_number_beats_closer_unknown(self):
        a = piece("a", run(0, 50, (0, 0)))
        b = piece("b", run(150, 200, (14, 4)))
        c = piece("c", run(150, 200, (12, 0)))
        got = il.link([a, b, c], {}, {"a": 7, "b": 7}, FPS)
        self.assertEqual(groups(got), [["a", "b"], ["c"]])

    def test_chain_keeps_number_of_its_pieces(self):
        a = piece("a", run(0, 50, (0, 0)))
        b = piece("b", run(100, 150, (8.5, 0)))            # ohne Nummer, passt zu a
        c = piece("c", run(200, 250, (17.5, 0)))           # Nummer 9, passt zu b, aber a hat 7
        got = il.link([a, b, c], {}, {"a": 7, "c": 9}, FPS)
        self.assertEqual(groups(got), [["a", "b"], ["c"]])


class CostTest(unittest.TestCase):
    def test_prediction_follows_running_direction(self):
        a = piece("a", run(0, 50, (0, 0)))
        ahead = il.link_cost(a, piece("b", run(100, 150, (8.5, 0))), None, None, FPS)
        behind = il.link_cost(a, piece("c", run(100, 150, (0, 0))), None, None, FPS)
        self.assertLess(ahead, behind)


if __name__ == "__main__":
    unittest.main()
