import unittest

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import reference as ref

BOX = [10, 10, 20, 40]


def identity(**players):
    """players: Name -> (Mannschaft, [Bilder], Boxnummer); eine Linse (0)."""
    return {"fps": 10, "players": {name: {"team": team, "keeper": False, "number": None,
                                          "detections": [[f, 0, box] for f in frames]}
                                   for name, (team, frames, box) in players.items()}}


def part(player, letter, f, box):
    return ref.Participant(player, letter, [f, 0, box, *BOX], {})


def spot(sid, frame, before, after, kinds=("occlusion",)):
    proposal = {p.letter: (p.letter if any(b.letter == p.letter for b in before) else None) for p in after}
    return ref.Spot(sid, list(kinds), frame, frame - 15, frame + 15, 0, [0, 0, 100, 100], before, after, proposal, 1.0)


def answer(sid, choice, mapping=None, numbers=None, repeat=False):
    return ref.Answer(sid, choice, mapping or {}, numbers or {}, {}, "2026-11-23T12:00:00", repeat)


def swap_scene():
    """a und b laufen 0–99; bei Bild 50 kreuzen sie sich."""
    ident = identity(a=("own", range(100), 0), b=("own", range(100), 1))
    s = spot("s1", 50, [part("a", "A", 49, 0), part("b", "B", 49, 1)], [part("a", "A", 50, 0), part("b", "B", 50, 1)])
    return ident, s


class PersonsTest(unittest.TestCase):
    def test_proposed_keeps_each_player(self):
        ident, s = swap_scene()
        p = ref.persons(ident, [s], [answer("s1", "proposed")])
        self.assertEqual(p.of[(10, 0, 0)], p.of[(80, 0, 0)])
        self.assertNotEqual(p.of[(10, 0, 0)], p.of[(80, 0, 1)])

    def test_swapped_crosses_over(self):
        ident, s = swap_scene()
        p = ref.persons(ident, [s], [answer("s1", "swapped")])
        self.assertEqual(p.of[(10, 0, 0)], p.of[(80, 0, 1)])
        self.assertEqual(p.of[(10, 0, 1)], p.of[(80, 0, 0)])

    def test_other_person_is_new(self):
        ident, s = swap_scene()
        p = ref.persons(ident, [s], [answer("s1", "mapped", {"A": "other", "B": "B"})])
        persons = {p.of[(10, 0, 0)], p.of[(10, 0, 1)]}
        self.assertNotIn(p.of[(80, 0, 0)], persons)
        self.assertEqual(p.of[(80, 0, 1)], p.of[(10, 0, 1)])

    def test_unclear_and_open_are_excluded(self):
        ident, s = swap_scene()
        p = ref.persons(ident, [s], [answer("s1", "mapped", {"A": "unclear", "B": "B"})])
        self.assertIsNone(p.of.get((80, 0, 0)))
        self.assertIsNotNone(p.of.get((80, 0, 1)))
        open_ = ref.persons(ident, [s], [])
        self.assertIsNone(open_.of.get((80, 0, 0)))
        self.assertIsNotNone(open_.of.get((10, 0, 0)))

    def test_start_mapped_to_ending_track(self):
        ident = identity(a=("own", range(0, 50), 0), c=("own", range(55, 100), 2))
        s = spot("s1", 52, [part("a", "A", 49, 0)], [part("c", "C", 55, 2)], kinds=("end",))
        p = ref.persons(ident, [s], [answer("s1", "mapped", {"C": "A"})])
        self.assertEqual(p.of[(10, 0, 0)], p.of[(90, 0, 2)])

    def test_unanswered_quiet_stretches_stay_their_own_person(self):
        ident = identity(a=("own", range(0, 50), 0), c=("own", range(55, 100), 2))
        p = ref.persons(ident, [], [])
        self.assertNotEqual(p.of[(10, 0, 0)], p.of[(90, 0, 2)])

    def test_last_answer_counts_and_repeats_do_not(self):
        ident, s = swap_scene()
        p = ref.persons(ident, [s], [answer("s1", "swapped"), answer("s1", "proposed"), answer("s1", "swapped", repeat=True)])
        self.assertEqual(p.of[(10, 0, 0)], p.of[(80, 0, 0)])

    def test_number_belongs_to_the_whole_person(self):
        ident, s = swap_scene()
        p = ref.persons(ident, [s], [answer("s1", "proposed", numbers={"A": 7})])
        self.assertEqual(p.number[p.of[(10, 0, 0)]], 7)

    def test_number_spot_does_not_cut(self):
        ident = identity(a=("own", range(100), 0))
        s = spot("n1", 50, [part("a", "A", 49, 0)], [part("a", "A", 50, 0)], kinds=("number",))
        p = ref.persons(ident, [s], [])          # offen: schneidet nicht, schließt nichts aus
        self.assertEqual(p.of[(10, 0, 0)], p.of[(80, 0, 0)])


class RefindTest(unittest.TestCase):
    def test_answer_follows_new_names(self):
        _, old = swap_scene()
        new = spot("t9", 50, [part("own-1", "A", 49, 1), part("own-2", "B", 49, 0)],
                   [part("own-1", "A", 50, 1), part("own-2", "B", 50, 0)])
        old.after[0].anchor = [50, 0, 0, *BOX]
        old.after[1].anchor = [50, 0, 1, 30, 10, 40, 40]
        new.after[0].anchor = [50, 0, 1, 30, 10, 40, 40]
        new.after[1].anchor = [50, 0, 0, *BOX]
        old.before[1].anchor = [49, 0, 1, 30, 10, 40, 40]
        new.before[0].anchor = [49, 0, 1, 30, 10, 40, 40]
        a = answer("s1", "mapped", {"A": "B", "B": "A"})
        kept, orphaned = ref.refind([old], [a], [new])
        self.assertEqual(orphaned, [])
        self.assertEqual(kept[0].spot, "t9")
        self.assertEqual(kept[0].mapping, {"B": "A", "A": "B"})

    def test_answer_without_matching_boxes_is_orphaned(self):
        _, old = swap_scene()
        moved = spot("t9", 50, [part("x", "A", 49, 5)], [part("x", "A", 50, 5)])
        for p in moved.before + moved.after:
            p.anchor = [p.anchor[0], 0, 5, 300, 300, 310, 330]
        kept, orphaned = ref.refind([old], [answer("s1", "proposed")], [moved])
        self.assertEqual((kept, [a.spot for a in orphaned]), ([], ["s1"]))


class ConflictTest(unittest.TestCase):
    def test_same_person_twice_at_once(self):
        ident, s = swap_scene()
        p = ref.persons(ident, [s], [answer("s1", "mapped", {"A": "A", "B": "A"})])
        self.assertTrue(any("zwei Orten" in w for w in ref.conflicts(ident, p)))

    def test_same_number_for_two_persons_of_a_team(self):
        ident, s = swap_scene()
        p = ref.persons(ident, [s], [answer("s1", "proposed", numbers={"A": 7, "B": 7})])
        self.assertTrue(any("Nummer 7" in w for w in ref.conflicts(ident, p)))

    def test_person_in_two_teams(self):
        ident = identity(a=("own", range(100), 0), b=("opponent", range(100), 1))
        s = spot("s1", 50, [part("a", "A", 49, 0), part("b", "B", 49, 1)], [part("a", "A", 50, 0), part("b", "B", 50, 1)])
        p = ref.persons(ident, [s], [answer("s1", "swapped")])
        self.assertTrue(any("Mannschaften" in w for w in ref.conflicts(ident, p)))


class JsonTest(unittest.TestCase):
    def test_round_trip(self):
        _, s = swap_scene()
        a = answer("s1", "proposed", numbers={"A": 7})
        data = ref.to_json("scene_705", "abc", [s], [a], 3)
        spots, answers, seed = ref.from_json(data)
        self.assertEqual((spots[0].id, answers[0].numbers, seed), ("s1", {"A": 7}, 3))
        self.assertEqual(set(data), {"scene", "identityStamp", "spots", "answers", "seed"})


if __name__ == "__main__":
    unittest.main()
