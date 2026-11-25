import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import body_pose as bp

NAMES = ["pelvis", "neck", "head", "nose", "lShoulder", "rShoulder", "lElbow", "rElbow", "lWrist", "rWrist", "lHip", "rHip",
         "lKnee", "rKnee", "lAnkle", "rAnkle", "lHeel", "rHeel", "lToe", "rToe"]


def mhr_person():
    """Ein Mensch (Kamerakoordinaten, y nach unten): Becken im Ursprung, Kopf oben (y negativ), Blick zur Kamera hin (-z)."""
    kp = np.zeros((1, 70, 3))
    kp[0, bp.L_HIP], kp[0, bp.R_HIP] = (0.1, 0, 0), (-0.1, 0, 0)
    kp[0, bp.NECK] = (0, -0.5, 0)
    kp[0, bp.L_EAR], kp[0, bp.R_EAR] = (0.08, -0.65, 0), (-0.08, -0.65, 0)
    kp[0, bp.L_SHOULDER], kp[0, bp.R_SHOULDER] = (0.18, -0.45, 0), (-0.18, -0.45, 0)
    kp[0, bp.L_BIG_TOE], kp[0, bp.L_SMALL_TOE] = (0.1, 0.9, -0.2), (0.14, 0.9, -0.15)
    return kp


class SkeletonTest(unittest.TestCase):
    def test_pelvis_is_the_middle_of_the_hips_and_toe_the_middle_of_two_toes(self):
        out = bp.to_skeleton(mhr_person(), NAMES)
        np.testing.assert_allclose(out[0, NAMES.index("pelvis")], 0, atol=1e-12)
        np.testing.assert_allclose(out[0, NAMES.index("lToe")], (0.12, 0.9, -0.175))
        np.testing.assert_allclose(out[0, NAMES.index("head")], (0, -0.65, 0))


class AxesTest(unittest.TestCase):
    def test_looking_along_y_with_pixels_right_and_down(self):
        # Blick nach +y (Platz), Pixel nach rechts = +x, Pixel nach unten = -z
        R = bp.camera_axes(np.array([0, 1.0, 0]), np.array([0.1, 1.0, 0]), np.array([0, 1.0, -0.1]))
        np.testing.assert_allclose(R[:, 0], (1, 0, 0), atol=1e-9)
        np.testing.assert_allclose(R[:, 1], (0, 0, -1), atol=1e-9)
        np.testing.assert_allclose(R[:, 2], (0, 1, 0), atol=1e-9)
        self.assertGreater(np.linalg.det(R), 0)

    def test_axes_are_orthonormal_for_a_tilted_view(self):
        R = bp.camera_axes(np.array([0.2, 1.0, -0.3]), np.array([0.3, 1.0, -0.3]), np.array([0.2, 1.0, -0.4]))
        np.testing.assert_allclose(R.T @ R, np.eye(3), atol=1e-9)


def fake_rays(cam, lens, pixels):
    p = np.asarray(pixels, float).reshape(-1, 2)
    d = np.column_stack([p[:, 0] / 1000, np.ones(len(p)), -p[:, 1] / 1000])
    return d / np.linalg.norm(d, axis=1, keepdims=True)


class WorldJointsTest(unittest.TestCase):
    def body(self, ids=("a", "b")):
        kp = mhr_person()
        return {"ids": np.array(ids), "player": np.array([1, 0]), "frame": np.array([2, 4]), "lens": np.array([0, 0]),
                "box": np.array([[0, 0, 0.0, 0.0], [0, 0, 0.0, 0.0]]), "kp3d": np.concatenate([kp, kp])}

    def test_person_stands_upright_in_the_world(self):
        out = bp.world_joints(self.body(), "a", 6, None, fake_rays, NAMES)
        self.assertEqual(int(np.isnan(out[:, 0, 0]).sum()), 5)       # nur Bild 4 gehört zu "a"
        neck = out[4, NAMES.index("neck")]
        self.assertGreater(neck[2], 0.45)                           # Hals über dem Becken
        self.assertLess(abs(neck[0]) + abs(neck[1]), 0.1)

    def test_left_stays_left(self):
        out = bp.world_joints(self.body(), "b", 6, None, fake_rays, NAMES)
        left, right = out[2, NAMES.index("lShoulder")], out[2, NAMES.index("rShoulder")]
        # Mensch blickt zur Kamera (Kamera schaut nach +y): seine Linke liegt in der Welt bei -x? Kamera-x (rechts im Bild) bleibt Welt-x
        self.assertGreater(left[0], right[0])

    def test_unknown_player_gives_nothing(self):
        out = bp.world_joints(self.body(), "zzz", 6, None, fake_rays, NAMES)
        self.assertTrue(np.isnan(out).all())


class FeetPositionTest(unittest.TestCase):
    EYE = np.array([0.0, -30.0, 5.0])
    CAM = {"lenses": {"left": {"centre": EYE}, "right": {"centre": EYE}}}
    NAMES = ["pelvis", "lAnkle", "rAnkle", "lHeel", "rHeel", "lToe", "rToe"]

    def rays(self, cam, lens, pixels):
        p = np.asarray(pixels, float).reshape(-1, 2)
        d = np.column_stack([p[:, 0], np.ones(len(p)), p[:, 1]])        # Pixel = Steigung rechts, Steigung hoch
        return d / np.linalg.norm(d, axis=1, keepdims=True)

    def pixel(self, point):
        v = np.asarray(point, float) - self.EYE
        return [v[0] / v[1], v[2] / v[1]]

    def scene(self, ground_xy, rel):
        """Körper mit Bodenpunkt ground_xy; rel: Gelenke relativ zum Bodenpunkt (7, 3); Rückgabe body, joints (6, 7, 3)."""
        kp2d = np.zeros((1, 70, 2))
        world = rel + [ground_xy[0], ground_xy[1], 0.0]
        kp2d[0, bp.L_ANKLE], kp2d[0, bp.R_ANKLE] = self.pixel(world[1]), self.pixel(world[2])
        kp2d[0, bp.L_HEEL], kp2d[0, bp.R_HEEL] = self.pixel(world[3]), self.pixel(world[4])
        kp2d[0, bp.L_BIG_TOE] = kp2d[0, bp.L_SMALL_TOE] = self.pixel(world[5])
        kp2d[0, bp.R_BIG_TOE] = kp2d[0, bp.R_SMALL_TOE] = self.pixel(world[6])
        body = {"ids": np.array(["a"]), "player": np.array([0]), "frame": np.array([3]), "lens": np.array([0]), "kp2d": kp2d}
        joints = np.tile(rel, (6, 1, 1))
        return body, joints

    REL = np.array([[0, 0, 0.95], [-0.1, 0, 0.08], [0.1, 0, 0.08], [-0.1, -0.08, 0.04], [0.1, -0.08, 0.04], [-0.1, 0.15, 0.035], [0.1, 0.15, 0.035]])

    def test_recovers_the_ground_point_from_the_feet(self):
        body, joints = self.scene((2.0, 10.0), self.REL)
        out = bp.position_from_feet(body, "a", 6, self.CAM, self.rays, joints, self.NAMES)
        np.testing.assert_allclose(out[3], (2.0, 10.0), atol=1e-6)
        self.assertTrue(np.isnan(out[0]).all())

    def test_feet_in_the_air_give_nothing(self):
        rel = self.REL.copy()
        rel[1:, 2] += 0.4
        body, joints = self.scene((2.0, 10.0), rel)
        out = bp.position_from_feet(body, "a", 6, self.CAM, self.rays, joints, self.NAMES)
        self.assertTrue(np.isnan(out).all())

    def test_only_the_foot_on_the_ground_counts(self):
        rel = self.REL.copy()
        rel[[2, 4, 6], 2] += 0.5                      # rechter Fuß in der Luft
        body, joints = self.scene((2.0, 10.0), rel)
        out = bp.position_from_feet(body, "a", 6, self.CAM, self.rays, joints, self.NAMES)
        np.testing.assert_allclose(out[3], (2.0, 10.0), atol=1e-6)


class AssignRowsTest(unittest.TestCase):
    """Zwei Bahnen a, b; die Projektion legt Welt-x auf Pixel-x (Boxhöhe 200)."""
    project = staticmethod(lambda lens, pts: np.column_stack([pts[:, 0] * 100, np.full(len(pts), 100.0)]))

    def body(self, hips, origin, frames=None):
        n = len(hips)
        kp2d = np.zeros((n, 70, 2))
        for i, h in enumerate(hips):
            kp2d[i, bp.L_HIP] = kp2d[i, bp.R_HIP] = (h, 100)
        return {"ids": np.array(["a", "b"]), "player": np.array(origin), "frame": np.array(frames if frames is not None else [0] * n),
                "lens": np.zeros(n, int), "box": np.tile([0.0, 0.0, 100.0, 200.0], (n, 1)), "kp2d": kp2d, "kp3d": np.zeros((n, 70, 3))}

    def tracks(self, a=1.0, b=3.0, frames=1):
        return {"a": np.tile([a, 0.0], (frames, 1)), "b": np.tile([b, 0.0], (frames, 1))}

    def test_each_person_goes_to_the_track_it_stands_at(self):
        out, moved, dropped = bp.assign_rows(self.body([100, 300], [0, 1]), self.tracks(), self.project)
        self.assertEqual(list(out["player"]), [0, 1])
        self.assertEqual((moved, dropped), (0, 0))

    def test_a_swapped_person_is_given_to_the_right_track(self):
        out, moved, dropped = bp.assign_rows(self.body([300, 100], [0, 1]), self.tracks(), self.project)
        self.assertEqual(list(out["player"]), [1, 0])
        self.assertEqual((moved, dropped), (2, 0))

    def test_the_same_person_found_twice_is_used_once(self):
        # beide Boxen finden den Spieler b (Hüfte bei 300); a ist verdeckt
        out, moved, dropped = bp.assign_rows(self.body([305, 298], [0, 1]), self.tracks(), self.project)
        self.assertEqual(len(out["player"]), 1)
        self.assertEqual(int(out["player"][0]), 1)
        self.assertEqual(dropped, 1)

    def test_one_person_found_twice_with_two_close_tracks_is_used_once(self):
        # Bahnen von a und b nur 20 Pixel auseinander (Zweikampf), beide Boxen finden dieselbe Person bei x=100
        tracks = {"a": np.array([[1.0, 0.0]]), "b": np.array([[1.2, 0.0]])}
        out, _, dropped = bp.assign_rows(self.body([100, 101], [0, 1]), tracks, self.project)
        self.assertEqual(len(out["player"]), 1)
        self.assertEqual(int(out["player"][0]), 0)        # a liegt genau bei der Hüfte
        self.assertEqual(dropped, 1)

    def test_a_person_far_from_every_track_is_dropped(self):
        out, _, dropped = bp.assign_rows(self.body([700], [0]), self.tracks(), self.project)
        self.assertEqual((len(out["player"]), dropped), (0, 1))

    def test_frames_are_decided_separately(self):
        tracks = {"a": np.array([[1.0, 0], [5.0, 0]]), "b": np.array([[3.0, 0], [7.0, 0]])}
        out, _, _ = bp.assign_rows(self.body([100, 700], [0, 1], frames=[0, 1]), tracks, self.project)
        self.assertEqual(list(out["player"]), [0, 1])

    def test_a_track_without_position_gets_nothing(self):
        tracks = {"a": np.array([[np.nan, np.nan]]), "b": np.array([[3.0, 0]])}
        out, _, dropped = bp.assign_rows(self.body([100], [0]), tracks, self.project)
        self.assertEqual((len(out["player"]), dropped), (0, 1))

    def test_empty_stays_empty(self):
        body = {"player": np.array([], int)}
        self.assertIs(bp.assign_rows(body, {}, self.project)[0], body)


class FillGapsTest(unittest.TestCase):
    def directions(self, steps):
        d = np.full((steps, 20, 3), np.nan)
        return d

    def test_a_gap_between_two_readings_is_bridged_with_unit_directions(self):
        d = self.directions(6)
        d[0, 1] = (0, 0, 1)
        d[5, 1] = (1, 0, 0)
        out, filled = bp.fill_gaps(d, np.ones(6, bool), 10)
        self.assertEqual(list(filled), [False, True, True, True, True, False])
        self.assertAlmostEqual(float(np.linalg.norm(out[2, 1])), 1.0)
        self.assertGreater(out[4, 1, 0], out[1, 1, 0])        # dreht von z nach x

    def test_a_gap_longer_than_allowed_is_left_open(self):
        d = self.directions(8)
        d[0, 1] = d[7, 1] = (0, 0, 1)
        out, filled = bp.fill_gaps(d, np.ones(8, bool), 3)
        self.assertFalse(filled.any())
        self.assertTrue(np.isnan(out[3, 1, 0]))

    def test_nothing_is_made_up_before_the_first_or_after_the_last_reading(self):
        d = self.directions(6)
        d[2, 1] = d[3, 1] = (0, 0, 1)
        _, filled = bp.fill_gaps(d, np.ones(6, bool), 10)
        self.assertFalse(filled.any())

    def test_frames_without_the_player_stay_open(self):
        d = self.directions(5)
        d[0, 1] = d[4, 1] = (0, 0, 1)
        _, filled = bp.fill_gaps(d, np.array([True, True, False, True, True]), 10)
        self.assertEqual(list(filled), [False, True, False, True, False])


class RefinePositionTest(unittest.TestCase):
    def test_constant_offset_is_corrected_and_noise_is_not_copied(self):
        rng = np.random.default_rng(1)
        n = 60
        pos = np.column_stack([np.linspace(0, 5, n), np.zeros(n)])
        seen = pos + (0.5, 0.0) + rng.normal(0, 0.3, (n, 2))
        out = bp.refine_position(pos, seen, np.ones(n, bool))
        np.testing.assert_allclose((out - pos)[10:50].mean(axis=0), (0.5, 0.0), atol=0.12)
        self.assertLess(float((out - pos)[10:50, 1].std()), 0.1)             # Rauschen wird nicht übernommen

    def test_shift_is_capped(self):
        pos = np.zeros((30, 2))
        out = bp.refine_position(pos, pos + (3.0, 0), np.ones(30, bool), max_shift=0.8)
        self.assertLessEqual(float(np.linalg.norm(out, axis=1).max()), 0.8 + 1e-9)

    def test_frames_outside_use_or_the_seen_span_are_untouched(self):
        pos = np.zeros((30, 2))
        seen = np.full((30, 2), np.nan)
        seen[10:20] = (0.5, 0)
        use = np.ones(30, bool)
        out = bp.refine_position(pos, seen, use)
        self.assertTrue((out[:10] == 0).all() and (out[21:] == 0).all())
        self.assertGreater(float(out[15, 0]), 0.3)

    def test_too_few_observations_change_nothing(self):
        pos = np.zeros((10, 2))
        seen = np.full((10, 2), np.nan)
        seen[2] = (1, 0)
        np.testing.assert_array_equal(bp.refine_position(pos, seen, np.ones(10, bool)), pos)


if __name__ == "__main__":
    unittest.main()
