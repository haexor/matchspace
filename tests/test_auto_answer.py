import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import auto_answer as aa
import reference as ref


def unit(*v):
    v = np.array(v, np.float32)
    return v / np.linalg.norm(v)


RED, BLUE, GREEN = unit(1, 0, 0), unit(0, 1, 0), unit(0, 0, 1)


def spot(kinds=("occlusion",), before=("a", "b"), after=("a", "b"), sid="s1"):
    mk = lambda names, letters: [ref.Participant(n, l, [0, 0, 0, 0, 0, 1, 1], {}) for n, l in zip(names, letters)]   # noqa: E731
    return ref.Spot(sid, list(kinds), 100, 50, 150, 0, [0, 0, 400, 250], mk(before, "ABC"), mk(after, "ABC"),
                    {l: l for l in "ABC"[:len(after)]}, 1.0)


def field(a_before, a_after, b_before, b_after, n=6):
    """Merkmalsfeld und Zeilen: je Spieler n Erkennungen vor Bild 100 und n danach."""
    emb, rows = [], {"a": {}, "b": {}}
    for name, (before, after) in (("a", (a_before, a_after)), ("b", (b_before, b_after))):
        for k in range(n):
            rows[name][60 + k] = len(emb); emb.append(before)
        for k in range(n):
            rows[name][110 + k] = len(emb); emb.append(after)
    return rows, np.array(emb)


class DecideTest(unittest.TestCase):
    def test_clear_continuation_is_answered_as_same(self):
        rows, emb = field(RED, RED, BLUE, BLUE)
        self.assertEqual(aa.decide(spot(), rows, emb), {"A": "A", "B": "B"})

    def test_clear_swap_is_answered_as_swapped(self):
        rows, emb = field(RED, BLUE, BLUE, RED)           # a sieht nachher aus wie b vorher und umgekehrt
        self.assertEqual(aa.decide(spot(), rows, emb), {"A": "B", "B": "A"})

    def test_similar_looks_stay_open(self):
        close = unit(1, 0.1, 0)
        rows, emb = field(RED, RED, close, close)
        self.assertIsNone(aa.decide(spot(), rows, emb))

    def test_one_person_before_control_and_number_spots_are_never_automatic(self):
        rows, emb = field(RED, RED, BLUE, BLUE)
        self.assertIsNone(aa.decide(spot(before=("a",), after=("a",)), rows, emb))
        self.assertIsNone(aa.decide(spot(kinds=("control",)), rows, emb))
        self.assertIsNone(aa.decide(spot(kinds=("number",)), rows, emb))

    def test_too_few_images_stay_open(self):
        rows, emb = field(RED, RED, BLUE, BLUE, n=1)
        self.assertIsNone(aa.decide(spot(), rows, emb))

    def test_two_boxes_on_the_same_person_stay_open(self):
        rows, emb = field(RED, BLUE, BLUE, BLUE)          # beide nachher sehen aus wie b vorher
        self.assertIsNone(aa.decide(spot(), rows, emb))


class AnswersTest(unittest.TestCase):
    def test_answers_carry_the_source_and_skip_decided_spots(self):
        rows, emb = field(RED, RED, BLUE, BLUE)
        out = aa.answers([spot(sid="s1"), spot(sid="s2")], rows, emb, decided={"s2"})
        self.assertEqual([(a.spot, a.source, a.choice) for a in out], [("s1", "auto", "mapped")])

    def test_source_survives_the_reference_file(self):
        rows, emb = field(RED, RED, BLUE, BLUE)
        a = aa.answers([spot()], rows, emb)[0]
        s = spot()
        data = ref.to_json("x", "stamp", [s], [a], 1)
        self.assertEqual(ref.from_json(data)[1][0].source, "auto")
        old = dict(data["answers"][0]); del old["source"]               # Dateien aus der Zeit davor
        self.assertEqual(ref.from_json({**data, "answers": [old]})[1][0].source, "hand")


if __name__ == "__main__":
    unittest.main()
