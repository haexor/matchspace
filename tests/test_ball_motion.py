import tempfile
import unittest
from pathlib import Path

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import ball_motion as bm
import ball_physics as bp
import own_scene


class SampleTest(unittest.TestCase):
    def test_interpolates_between_valid_neighbours(self):
        v = np.array([[0.0, 0.0], [10.0, 0.0], [20.0, 0.0]])
        out = bm.sample(v, 3, 0.5)
        np.testing.assert_allclose(out[:, 0], [0.0, 5.0, 10.0])

    def test_nan_is_not_smeared(self):
        v = np.array([[0.0, 0.0], [np.nan, np.nan], [20.0, 0.0], [30.0, 0.0]])
        out = bm.sample(v, 4, 1.0)
        self.assertTrue(np.isnan(out[1]).all())
        self.assertEqual(out[2, 0], 20.0)

    def test_takes_valid_neighbour_at_a_gap_edge(self):
        v = np.array([[0.0], [10.0], [np.nan]])
        self.assertEqual(bm.sample(v, 2, 1.2)[1, 0], 10.0)
        self.assertTrue(np.isnan(bm.sample(v, 2, 1.5)[1, 0]))

    def test_one_dimension(self):
        out = bm.sample(np.array([0.0, 4.0, 8.0]), 5, 0.5)
        np.testing.assert_allclose(out, [0, 2, 4, 6, 8])


class OutputTrackTest(unittest.TestCase):
    def write(self, xyz, kind, inferred, contacts):
        d = tempfile.mkdtemp()
        path = Path(d) / "x.ball3d.npz"
        np.savez(path, xyz=xyz, kind=kind, inferred=inferred, z_sigma=np.zeros(len(kind)), fps=30.0,
                 contacts=np.array(contacts, float).reshape(-1, 5))
        return path

    def test_height_is_measured_at_the_ball_bottom(self):
        xyz = np.tile([1.0, 2.0, bp.RADIUS + 1.0], (10, 1))
        path = self.write(xyz, np.full(10, bm.FLIGHT), np.zeros(10, bool), [])
        t = bm.output_track(path, 8, 1.2)
        np.testing.assert_allclose(t.z, 1.0)
        self.assertTrue(t.flight.all())

    def test_ground_ball_has_height_zero(self):
        xyz = np.tile([1.0, 2.0, bp.RADIUS], (10, 1))
        t = bm.output_track(self.write(xyz, np.full(10, bm.GROUND), np.zeros(10, bool), []), 8, 1.2)
        np.testing.assert_allclose(t.z, 0.0)

    def test_contacts_are_mapped_to_output_frames(self):
        xyz = np.tile([1.0, 2.0, bp.RADIUS], (60, 1))
        path = self.write(xyz, np.ones(60, np.uint8), np.zeros(60, bool), [[30, 0, 5, 5, 1.0]])
        t = bm.output_track(path, 50, 30 / 25)
        self.assertEqual(list(t.contacts), [25])

    def test_unknown_stretch_has_no_position(self):
        xyz = np.full((10, 3), np.nan)
        t = bm.output_track(self.write(xyz, np.zeros(10, np.uint8), np.zeros(10, bool), []), 8, 1.2)
        self.assertTrue(np.isnan(t.xy).all())
        self.assertTrue((t.z == 0).all())


class AttachActiveTest(unittest.TestCase):
    def test_only_active_frames_are_pulled(self):
        T = 40
        feet = np.zeros((T, 1, 2))
        ball = np.tile([0.5, 0.0], (T, 1))
        active = np.zeros(T, bool)
        active[18:23] = True
        out = own_scene.attach_ball(ball, feet, 25, active)
        self.assertLess(np.linalg.norm(out[20]), 0.5)
        np.testing.assert_allclose(out[5], ball[5])
        np.testing.assert_allclose(out[35], ball[35])

    def test_none_means_everywhere(self):
        T = 40
        feet = np.zeros((T, 1, 2))
        ball = np.tile([0.5, 0.0], (T, 1))
        np.testing.assert_allclose(own_scene.attach_ball(ball, feet, 25, None), own_scene.attach_ball(ball, feet, 25))


if __name__ == "__main__":
    unittest.main()
