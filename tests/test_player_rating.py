"""Spielwerte und Spielbewertung aus Bahnen (tools/player_rating.py)."""
import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import player_rating as pr

FPS = 25


def run(speed, seconds, y=0.0):
    """Gerade Spur mit gleichmäßiger Geschwindigkeit (m/s)."""
    n = int(seconds * FPS)
    return np.stack([np.arange(n) * speed / FPS, np.full(n, y)], axis=1)


class StatsTest(unittest.TestCase):
    def test_distance_and_top_speed_of_a_steady_run(self):
        s = pr.stats_of(run(6.0, 60), FPS)
        self.assertAlmostEqual(s["distance"], 6.0 * 60, delta=1.0)
        self.assertAlmostEqual(s["topSpeed"], 6.0, delta=0.1)
        self.assertAlmostEqual(s["seconds"], 60.0, delta=0.1)

    def test_one_glitch_frame_does_not_set_the_top_speed(self):
        xy = run(5.0, 60)
        xy[700:] += 8.0                                    # ein Sprung der Spur um 8 m in einem Bild
        self.assertLess(pr.stats_of(xy, FPS)["topSpeed"], 7.0)

    def test_missing_frames_are_ignored(self):
        xy = run(5.0, 60)
        xy[300:400] = np.nan
        s = pr.stats_of(xy, FPS)
        self.assertAlmostEqual(s["seconds"], 56.0, delta=0.1)
        self.assertAlmostEqual(s["distance"], 5.0 * 56, delta=3.0)

    def test_sprints_need_speed_and_duration(self):
        slow = pr.stats_of(run(4.0, 60), FPS)["sprints"]
        fast = pr.stats_of(run(7.0, 60), FPS)["sprints"]
        self.assertEqual(slow, 0)
        self.assertEqual(fast, 1)
        burst = np.concatenate([run(2.0, 5), run(7.0, 0.4) + [[10, 0]], run(2.0, 5) + [[20, 0]]])      # zu kurz für einen Sprint
        self.assertEqual(pr.stats_of(burst, FPS)["sprints"], 0)

    def test_a_track_that_is_hardly_seen_has_no_top_speed(self):
        xy = np.full((100, 2), np.nan)
        self.assertIsNone(pr.stats_of(xy, FPS)["topSpeed"])


class RatingTest(unittest.TestCase):
    def squad(self):
        speeds = [4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0]
        stats = {f"p{i}": pr.stats_of(run(v, 120), FPS, touches=i) for i, v in enumerate(speeds)}
        minute = {k: pr.per_minute(s) for k, s in stats.items()}
        return stats, minute

    def peers_of(self, minute, key):
        return [m for k, m in minute.items() if k != key]

    def test_faster_player_gets_the_higher_rating(self):
        stats, minute = self.squad()
        slow = pr.match_rating(stats["p0"], self.peers_of(minute, "p0"))
        fast = pr.match_rating(stats["p6"], self.peers_of(minute, "p6"))
        self.assertGreater(fast, slow)
        self.assertTrue(1.0 <= slow <= 10.0 and 1.0 <= fast <= 10.0)

    def test_the_middle_player_is_about_average(self):
        stats, minute = self.squad()
        mid = pr.match_rating(stats["p3"], self.peers_of(minute, "p3"))
        self.assertAlmostEqual(mid, 6.0, delta=0.8)

    def test_no_rating_without_enough_peers_or_time(self):
        stats, minute = self.squad()
        self.assertIsNone(pr.match_rating(stats["p3"], self.peers_of(minute, "p3")[:2]))
        short = pr.stats_of(run(6.0, 10), FPS)
        self.assertIsNone(pr.match_rating(short, self.peers_of(minute, "p3")))

    def test_pace_follows_the_top_speed_on_the_viewer_scale(self):
        stats, minute = self.squad()
        pace = {k: pr.ratings_of(s, self.peers_of(minute, k))["pace"] for k, s in stats.items()}
        self.assertEqual(sorted(pace.values()), list(pace.values()))       # monoton in der Reihenfolge der Tempi
        self.assertEqual(pr.scale(4.6, *pr.PACE_RANGE), 0)
        self.assertEqual(pr.scale(8.8, *pr.PACE_RANGE), 99)

    def test_stamina_is_relative_to_the_others(self):
        stats, minute = self.squad()
        low = pr.ratings_of(stats["p0"], self.peers_of(minute, "p0"))["stamina"]
        high = pr.ratings_of(stats["p6"], self.peers_of(minute, "p6"))["stamina"]
        self.assertLess(low, 70)
        self.assertGreater(high, 70)

    def test_a_short_scene_gives_no_attributes_that_need_time(self):
        short = pr.stats_of(run(6.0, 10), FPS)
        self.assertEqual(pr.ratings_of(short, []), {})


if __name__ == "__main__":
    unittest.main()
