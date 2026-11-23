import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import identity_link as il
import jersey_identity

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

    def test_a_late_far_start_is_not_cheaper_than_a_start_right_after(self):
        a = piece("a", run(0, 50, (0, 0), speed=(0.0, 0.0)))
        near = il.link_cost(a, piece("b", run(51, 100, (1.2, 0), speed=(0.0, 0.0))), None, None, FPS)   # 1 Bild später, 1,2 m
        late = il.link_cost(a, piece("c", run(450, 500, (10, 0), speed=(0.0, 0.0))), None, None, FPS)   # 16 s später, 10 m
        self.assertLess(near, late)

    def test_occlusion_gap_is_linked_despite_a_late_far_start(self):
        a = piece("a", run(0, 50, (0, 0), speed=(0.0, 0.0)))
        near = piece("b", run(51, 100, (1.2, 0), speed=(0.0, 0.0)))
        late = piece("c", run(450, 500, (10, 0), speed=(0.0, 0.0)))
        self.assertIn(["a", "b"], groups(il.link([a, near, late], {}, {}, FPS)))


COLOURS = {"own": 0, "opponent": 1, "referee": 2}


def path(a, b, p0, p1, colour):
    """Gerade von p0 (Bild a) nach p1 (Bild b-1), Zeilen (x, y, Farbe)."""
    n = b - a - 1
    return {f: (p0[0] + (p1[0] - p0[0]) * (f - a) / n, p0[1] + (p1[1] - p0[1]) * (f - a) / n, colour) for f in range(a, b)}


def reading(track, frame, number):
    probs = np.full(jersey_identity.CLASSES, 0.05 / (jersey_identity.CLASSES - 1))
    probs[number] = 0.95
    return jersey_identity.Reading(track, frame, probs, 1.0)


class ContactTest(unittest.TestCase):
    def test_close_approach_of_same_team(self):
        a = piece("a", path(0, 100, (0, 0), (10, 0), 0))
        b = piece("b", path(0, 100, (10, 1), (0, 1), 0))
        got = il.contacts([a, b], FPS)
        self.assertEqual(len(got), 1)
        self.assertEqual({got[0].a, got[0].b}, {"a", "b"})
        self.assertAlmostEqual(got[0].frame, 50, delta=1)

    def test_no_contact_across_teams(self):
        a = piece("a", path(0, 100, (0, 0), (10, 0), 0))
        b = piece("b", path(0, 100, (10, 1), (0, 1), 1), team="opponent")
        self.assertEqual(il.contacts([a, b], FPS), [])


class SplitTest(unittest.TestCase):
    def test_swap_across_teams_is_split_and_relinked_crosswise(self):
        # A (wir) läuft von (0,0) nach (10,10), B (Gegner) von (0,10) nach (10,0); in der Mitte tauschen die Spuren.
        a = piece("a", {**path(0, 63, (0, 0), (5, 5), 0), **path(63, 125, (5.08, 4.92), (10, 0), 1)})
        b = piece("b", {**path(0, 63, (0, 10), (5, 5), 1), **path(63, 125, (5.08, 5.08), (10, 10), 0)}, team="opponent")
        pieces = il.split_by_colour([a, b], COLOURS, FPS)
        self.assertEqual(sorted((p.id, p.team) for p in pieces),
                         [("a/0", "own"), ("a/1", "opponent"), ("b/0", "opponent"), ("b/1", "own")])
        self.assertEqual(groups(il.link(pieces, {}, {}, FPS)), [["a/0", "b/1"], ["a/1", "b/0"]])

    def test_passing_without_swap_stays_whole(self):
        a = piece("a", path(0, 100, (0, 0), (10, 0), 0))
        b = piece("b", path(0, 100, (10, 0.8), (0, 0.8), 1), team="opponent")
        pieces = il.split_by_colour([a, b], COLOURS, FPS)
        self.assertEqual(sorted(p.id for p in pieces), ["a", "b"])

    def test_short_foreign_colour_is_ignored(self):
        frames = path(0, 100, (0, 0), (10, 0), 0)
        for f in range(40, 55):      # 0,6 s fremde Farbe (Verdeckung)
            frames[f] = (*frames[f][:2], 1)
        self.assertEqual([p.id for p in il.split_by_colour([piece("a", frames)], COLOURS, FPS)], ["a"])

    def test_foreign_colour_without_anyone_near_is_not_a_swap(self):
        frames = path(0, 100, (0, 0), (10, 0), 0)
        for f in range(30, 80):      # 1,6 s lang „fremde“ Farbe, aber kein Mensch weit und breit
            frames[f] = (*frames[f][:2], 1)
        far = piece("c", path(0, 100, (0, 30), (10, 30), 1), team="opponent")
        self.assertEqual(sorted(p.id for p in il.split_by_colour([piece("a", frames), far], COLOURS, FPS)), ["a", "c"])

    def test_foreign_stretch_on_a_tracked_player_is_dropped(self):
        a = piece("a", {**path(0, 50, (0, 0), (5, 0), 0), **path(50, 100, (5.1, 0), (10, 0), 1)})
        c = piece("c", path(0, 100, (0, 3), (10, 0), 1), team="opponent")   # der Gegner hat schon seine Spur
        pieces = il.split_by_colour([a, c], COLOURS, FPS)
        self.assertEqual(sorted(p.id for p in pieces), ["a/0", "c"])

    def test_different_sure_numbers_split_at_the_contact(self):
        a = piece("a", path(0, 200, (0, 0), (20, 0), 0))
        c = piece("c", path(80, 120, (10, 1), (10, 0.5), 0))      # steht bei Bild 100 neben a
        readings = [reading("a", f, 7) for f in range(0, 90, 2)] + [reading("a", f, 9) for f in range(110, 200, 2)]
        contacts = il.contacts([a, c], FPS)
        pieces = il.split_by_numbers([a, c], contacts, readings, FPS)
        self.assertEqual(sorted(p.id for p in pieces), ["a/0", "a/1", "c"])
        cut = next(p for p in pieces if p.id == "a/1").start
        self.assertTrue(80 <= cut <= 120)

    def test_same_number_on_both_sides_stays_whole(self):
        a = piece("a", path(0, 200, (0, 0), (20, 0), 0))
        c = piece("c", path(80, 120, (10, 1), (10, 0.5), 0))
        readings = [reading("a", f, 7) for f in list(range(0, 90, 2)) + list(range(110, 200, 2))]
        pieces = il.split_by_numbers([a, c], il.contacts([a, c], FPS), readings, FPS)
        self.assertEqual(sorted(p.id for p in pieces), ["a", "c"])


if __name__ == "__main__":
    unittest.main()
