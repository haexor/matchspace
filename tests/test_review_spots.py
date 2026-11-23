import unittest

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import review_spots as rs

FPS = 10
N = 300
PITCH = (90.0, 55.0)


def scene(**players):
    """players: Name -> (Mannschaft, Bilder, Linse, Box(f) -> [x1,y1,x2,y2], Lage(f) -> (x, y)).
    Rückgabe: Zuordnung, Boxen und Lagen wie aus review_spots.load_scene."""
    ident = {"fps": FPS, "players": {}, "events": [], "numbers": {}}
    boxes, ground = {}, {}
    for k, (name, (team, frames, lens, box, where)) in enumerate(players.items()):
        dets = [[f, lens, k] for f in frames]
        ident["players"][name] = {"team": team, "keeper": False, "number": None, "detections": dets}
        for f in frames:
            boxes[(f, lens, k)] = box(f)
            ground[(f, lens, k)] = where(f)
    return ident, boxes, ground


def fixed(x):
    return lambda f: [x, 100, x + 20, 160]


def at(x, y=0.0):
    return lambda f: (x, y)


class OcclusionTest(unittest.TestCase):
    def test_overlap_above_threshold_is_a_spot(self):
        moving = lambda f: [200 - f, 100, 220 - f, 160]        # noqa: E731  läuft bei Bild ~100 über a
        ident, boxes, ground = scene(a=("own", range(N), 0, fixed(100), at(0)), b=("opponent", range(N), 0, moving, at(0)))
        spots = rs.find_spots(ident, boxes, ground, PITCH, N)
        occ = [s for s in spots if "occlusion" in s.kinds]
        self.assertEqual(len(occ), 1)
        self.assertEqual({p.player for p in occ[0].before}, {"a", "b"})
        self.assertAlmostEqual(occ[0].frame, 100, delta=10)
        self.assertEqual((occ[0].start, occ[0].end), (occ[0].start, occ[0].end))
        self.assertLessEqual(occ[0].start, occ[0].frame - 15)

    def test_small_overlap_or_other_lens_is_no_spot(self):
        touch = lambda f: [117, 100, 137, 160]                  # noqa: E731  15 % der Box
        ident, boxes, ground = scene(a=("own", range(N), 0, fixed(100), at(0)), b=("own", range(N), 0, touch, at(5)))
        self.assertEqual([s for s in rs.find_spots(ident, boxes, ground, PITCH, N) if "occlusion" in s.kinds], [])
        ident, boxes, ground = scene(a=("own", range(N), 0, fixed(100), at(0)), b=("own", range(N), 1, fixed(100), at(5)))
        self.assertEqual([s for s in rs.find_spots(ident, boxes, ground, PITCH, N) if "occlusion" in s.kinds], [])


class EndTest(unittest.TestCase):
    def test_end_on_the_pitch_is_a_spot(self):
        ident, boxes, ground = scene(a=("own", range(0, 150), 0, fixed(100), at(0)),
                                     c=("own", range(160, N), 0, fixed(110), at(1)))
        spots = rs.find_spots(ident, boxes, ground, PITCH, N)
        ends = [s for s in spots if {"end", "start"} & set(s.kinds)]
        self.assertEqual(len(ends), 1)                          # Ende von a und Beginn von c: eine Stelle
        self.assertEqual([p.player for p in ends[0].before], ["a"])
        self.assertEqual([p.player for p in ends[0].after], ["c"])
        self.assertEqual(ends[0].proposal, {ends[0].after[0].letter: None})

    def test_end_without_anyone_taking_over_is_no_spot(self):
        ident, boxes, ground = scene(a=("own", range(0, 150), 0, fixed(100), at(0)),
                                     b=("own", range(0, N), 0, fixed(400), at(2)))      # läuft einfach weiter
        self.assertEqual(rs.find_spots(ident, boxes, ground, PITCH, N), [])

    def test_end_at_the_touchline_or_scene_edge_is_no_spot(self):
        ident, boxes, ground = scene(a=("own", range(0, 150), 0, fixed(100), at(0, 27.3)),
                                     b=("own", range(0, N), 0, fixed(400), at(10)))
        self.assertEqual(rs.find_spots(ident, boxes, ground, PITCH, N), [])


class EventTest(unittest.TestCase):
    def test_split_link_and_numbers(self):
        ident, boxes, ground = scene(a=("own", range(N), 0, fixed(100), at(0)), b=("own", range(N), 0, fixed(400), at(10)))
        ident["events"] = [{"kind": "split", "frame": 60, "reason": "colour", "players": ["a", "a"], "detections": [[59, 0, 0], [60, 0, 0]]}]
        ident["players"]["b"]["number"] = 7
        spots = rs.find_spots(ident, boxes, ground, PITCH, N, best_back={"b": 200}, unsure={"a": 250})
        kinds = sorted(k for s in spots for k in s.kinds)
        self.assertEqual(kinds, ["number", "number-unsure", "split"])
        number = next(s for s in spots if "number" in s.kinds)
        self.assertEqual((number.frame, number.number), (200, 7))


class MergeTest(unittest.TestCase):
    def test_close_spots_with_shared_players_merge(self):
        moving = lambda f: [200 - f, 100, 220 - f, 160]         # noqa: E731
        ident, boxes, ground = scene(a=("own", range(0, 105), 0, fixed(100), at(0)), b=("own", range(N), 0, moving, at(0)))
        spots = rs.find_spots(ident, boxes, ground, PITCH, N)
        self.assertEqual(len(spots), 1)
        self.assertEqual(set(spots[0].kinds), {"occlusion", "end"})

    def test_spots_are_in_time_order_with_stable_ids(self):
        moving = lambda f: [200 - f, 100, 220 - f, 160]         # noqa: E731
        later = lambda f: [400 - f, 100, 420 - f, 160]          # noqa: E731
        ident, boxes, ground = scene(a=("own", range(N), 0, fixed(100), at(0)), b=("own", range(N), 0, moving, at(0)),
                                     c=("own", range(N), 0, later, at(0)))
        spots = rs.find_spots(ident, boxes, ground, PITCH, N)
        self.assertEqual([s.frame for s in spots], sorted(s.frame for s in spots))
        self.assertEqual([s.id for s in spots], [s.id for s in rs.find_spots(ident, boxes, ground, PITCH, N)])


class ControlTest(unittest.TestCase):
    def test_controls_are_repeatable_and_away_from_spots(self):
        moving = lambda f: [200 - f, 100, 220 - f, 160]         # noqa: E731
        ident, boxes, ground = scene(a=("own", range(N), 0, fixed(100), at(0)), b=("own", range(N), 0, moving, at(0)),
                                     c=("opponent", range(N), 0, fixed(600), at(20)))
        spots = rs.find_spots(ident, boxes, ground, PITCH, N)
        one = rs.control_spots(ident, boxes, spots, N, seed=3, n=5)
        two = rs.control_spots(ident, boxes, spots, N, seed=3, n=5)
        self.assertEqual(len(one), 5)
        self.assertEqual([s.id for s in one], [s.id for s in two])
        for c in one:
            self.assertEqual(c.kinds, ["control"])
            self.assertEqual(len(c.before), 1)
            for s in spots:
                if s.before and c.before[0].player in {p.player for p in s.before + s.after}:
                    self.assertGreater(abs(c.frame - s.frame), 2 * FPS)


class CropTest(unittest.TestCase):
    def test_crop_holds_all_participants(self):
        moving = lambda f: [200 - f, 100, 220 - f, 160]         # noqa: E731
        ident, boxes, ground = scene(a=("own", range(N), 0, fixed(100), at(0)), b=("own", range(N), 0, moving, at(0)))
        s = rs.find_spots(ident, boxes, ground, PITCH, N)[0]
        x, y, w, h = s.crop
        for p in s.before + s.after:
            for b in p.boxes.values():
                self.assertTrue(x <= b[0] and b[2] <= x + w and y <= b[1] and b[3] <= y + h)

    def test_crop_has_fixed_aspect_and_stays_in_the_lens(self):
        near_edge = lambda f: [2020, 900, 2040, 1000]            # noqa: E731  am Rand des Linsenbilds
        ident, boxes, ground = scene(a=("own", range(0, 150), 0, near_edge, at(0)), c=("own", range(160, N), 0, near_edge, at(1)))
        for s in rs.find_spots(ident, boxes, ground, PITCH, N):
            x, y, w, h = s.crop
            self.assertAlmostEqual(w / h, rs.CROP_ASPECT, delta=0.02)
            self.assertGreaterEqual(w, rs.CROP_MIN)
            self.assertTrue(x >= 0 and y >= 0 and x + w <= 2048 and y + h <= 1024)


class CrowdTest(unittest.TestCase):
    def test_no_question_has_more_than_three_people(self):
        ends = {f"e{i}": ("own", range(0, 150), 0, fixed(100 + 40 * i), at(i)) for i in range(3)}
        starts = {f"s{i}": ("own", range(160, N), 0, fixed(110 + 40 * i), at(i + 0.5)) for i in range(3)}
        ident, boxes, ground = scene(**ends, **starts)
        spots = rs.find_spots(ident, boxes, ground, PITCH, N)
        self.assertGreater(len(spots), 1)                        # sechs Beteiligte: mehrere Fragen
        for s in spots:
            self.assertLessEqual(len({p.player for p in s.before + s.after}), rs.MAX_PLAYERS)


if __name__ == "__main__":
    unittest.main()
