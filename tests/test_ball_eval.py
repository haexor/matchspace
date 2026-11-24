import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import ball_eval as ev
import ball_events as be
import ball_reference as br


def contact(frame, kind="pass", confidence=1.0):
    return be.Contact(frame, frame / 30, (0, 0), 0.0, 10.0, 10.0, kind, 2, confidence)


def ref(*pairs, unseen=()):
    r = br.new("s", 30.0)
    for f, kind in pairs:
        br.add_contact(r, f, kind)
    r["unseen"] = [list(u) for u in unseen]
    return r


class MatchTest(unittest.TestCase):
    def test_nearest_first_and_one_to_one(self):
        self.assertEqual(sorted(ev.match([10, 12], [11])), [(0, 0)])

    def test_outside_tolerance_does_not_pair(self):
        self.assertEqual(ev.match([10], [30]), [])


class EvaluateTest(unittest.TestCase):
    def test_perfect_detection(self):
        r = ev.evaluate([contact(10), contact(50)], ref((10, "pass"), (50, "pass")), 30.0)
        self.assertEqual((r["gefunden"], r["erfunden"]), (2, 0))
        self.assertEqual(r["zeitfehlerMittelBilder"], 0.0)
        self.assertEqual(r["artRichtigAnteil"], 1.0)
        self.assertTrue(all(ev.meets_targets(r).values()))

    def test_time_error_and_sign(self):
        r = ev.evaluate([contact(12), contact(52)], ref((10, "pass"), (50, "pass")), 30.0)
        self.assertEqual(r["zeitfehlerMittelBilder"], 2.0)
        self.assertEqual(r["zeitfehlerVorzeichenBilder"], 2.0)

    def test_invented_and_missed(self):
        r = ev.evaluate([contact(10), contact(200)], ref((10, "pass"), (80, "shot")), 30.0)
        self.assertEqual(r["erfunden"], 1)
        self.assertEqual(r["verpasst"], [80])
        self.assertEqual(r["gefundenAnteil"], 0.5)
        self.assertFalse(ev.meets_targets(r)["gefunden>=80%"])

    def test_unseen_stretch_counts_neither_way(self):
        r = ev.evaluate([contact(100)], ref((10, "pass"), (100, "pass"), unseen=[(90, 110)]), 30.0)
        self.assertEqual(r["referenz"], 1)
        self.assertEqual(r["erkannt"], 0)
        self.assertEqual(r["erfunden"], 0)

    def test_kind_mismatch_is_counted(self):
        r = ev.evaluate([contact(10, "shot")], ref((10, "pass")), 30.0)
        self.assertEqual(r["artRichtigAnteil"], 0.0)

    def test_empty_reference_gives_none_not_a_crash(self):
        r = ev.evaluate([contact(10)], ref(), 30.0)
        self.assertIsNone(r["gefundenAnteil"])
        self.assertEqual(r["erfunden"], 1)

    def test_sure_invented_share(self):
        r = ev.evaluate([contact(10, confidence=0.9), contact(100, confidence=0.9), contact(200, confidence=0.2)],
                        ref((10, "pass")), 30.0)
        self.assertEqual(r["erfundenSicherAnteil"], 0.5)


class HeightTest(unittest.TestCase):
    def test_signed_error(self):
        self.assertAlmostEqual(ev.height_error(np.array([0.5, 3.4, 1.0]), 3.0), 0.4)


if __name__ == "__main__":
    unittest.main()
