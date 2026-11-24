import unittest
from unittest import mock

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import veo_ball as vb

FPS = 30.0


def at_ground(x, y):
    return mock.patch.object(vb.veo_camera, "to_ground", lambda cam, lens, px, h: (np.array([[x, y]]), None))


def hits(frames, u=500.0, v=300.0):
    """Feste Treffer in den angegebenen Bildern: Kandidaten je Bild als [Linse, u, v, Sicherheit]."""
    n = max(frames) + 1
    out = [[] for _ in range(n)]
    for f in frames:
        out[f].append([0, u, v, 0.8])
    return out


class SplitStaticTest(unittest.TestCase):
    def test_static_spot_is_dropped_and_returned(self):
        cands = hits(range(0, 150, 10))   # 15 Treffer über 5 s am selben Pixel
        kept, dropped, count = vb.split_static(cands, FPS)
        self.assertEqual(count, 1)
        self.assertTrue(all(not k for k in kept))
        self.assertEqual(sum(len(d) for d in dropped), 15)

    def test_drop_static_keeps_old_contract(self):
        kept, count = vb.drop_static(hits(range(0, 150, 10)), FPS)
        self.assertEqual(count, 1)
        self.assertTrue(all(not k for k in kept))

    def test_short_presence_is_not_static(self):
        kept, _, count = vb.split_static(hits(range(0, 30, 5)), FPS)   # 1 s
        self.assertEqual(count, 0)
        self.assertEqual(sum(len(k) for k in kept), 6)


class RestFillTest(unittest.TestCase):
    def run_fill(self, pos, dropped, at=(10.0, -20.0)):
        pix = np.full((len(pos), 3), np.nan)
        with at_ground(*at):
            filled = vb.rest_fill(pos, pix, dropped, None, FPS)
        return filled, pix

    def test_ball_resting_after_chain_end_is_filled(self):
        n = 150
        pos = np.full((n, 2), np.nan)
        pos[:40] = (10.0, -20.0)                       # bewegte Spur endet an der Ruhestelle
        dropped = hits(range(40, 140, 5)) + [[] for _ in range(n - 140)]
        filled, pix = self.run_fill(pos, dropped)
        self.assertGreater(filled, 90)
        self.assertEqual(tuple(pos[100]), (10.0, -20.0))
        self.assertEqual(pix[100, 0], 0)

    def test_resting_ball_before_chain_start_is_filled(self):
        n = 150
        pos = np.full((n, 2), np.nan)
        pos[100:] = (10.5, -20.2)
        dropped = hits(range(0, 100, 5)) + [[] for _ in range(n - 100)]
        filled, _ = self.run_fill(pos, dropped)
        self.assertGreater(filled, 90)
        self.assertFalse(np.isnan(pos[0, 0]))

    def test_reserve_ball_far_from_chain_is_ignored(self):
        n = 150
        pos = np.full((n, 2), np.nan)
        pos[:40] = (-5.0, -10.0)                       # Spur endet weit weg von der festen Stelle
        dropped = hits(range(40, 140, 5)) + [[] for _ in range(n - 140)]
        filled, _ = self.run_fill(pos, dropped)
        self.assertEqual(filled, 0)
        self.assertTrue(np.isnan(pos[100, 0]))

    def test_static_hits_running_into_a_chain_elsewhere_are_a_reserve_ball(self):
        n = 150
        pos = np.full((n, 2), np.nan)
        pos[:40] = (10.0, -20.0)
        pos[100:] = (-6.0, 3.0)                        # Spur setzt an anderer Stelle fort, die festen Treffer reichen bis dahin
        dropped = hits(range(40, 100, 5)) + [[] for _ in range(n - 100)]
        filled, _ = self.run_fill(pos, dropped)
        self.assertEqual(filled, 0)

    def test_no_chain_no_fill(self):
        pos = np.full((150, 2), np.nan)
        filled, _ = self.run_fill(pos, hits(range(0, 150, 5)))
        self.assertEqual(filled, 0)

    def test_pause_longer_than_limit_ends_rest(self):
        n = 200
        pos = np.full((n, 2), np.nan)
        pos[:20] = (10.0, -20.0)
        dropped = hits(list(range(20, 60, 5)) + list(range(150, 190, 5))) + [[] for _ in range(n - 186)]
        dropped = dropped[:n] + [[] for _ in range(max(0, n - len(dropped)))]
        filled, _ = self.run_fill(pos, dropped)
        self.assertTrue(np.isnan(pos[120, 0]))         # in der langen Pause nichts erfunden
        self.assertGreater(filled, 30)

    def test_filled_frames_do_not_overwrite_found_ball(self):
        n = 150
        pos = np.full((n, 2), np.nan)
        pos[:40] = (10.0, -20.0)
        pos[70] = (30.0, 0.0)
        dropped = hits(range(40, 140, 5)) + [[] for _ in range(n - 140)]
        self.run_fill(pos, dropped)
        self.assertEqual(tuple(pos[70]), (30.0, 0.0))


if __name__ == "__main__":
    unittest.main()
