import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import foot_fit as ff

NAMES = ["pelvis", "lAnkle", "rAnkle", "lHeel", "rHeel", "lToe", "rToe"]
EYE = np.array([0.0, -30.0, 5.0])
CAM = {"lenses": {"left": {"centre": EYE}, "right": {"centre": EYE}}}


def fake_rays(cam, name, pixels):
    """Pixel = (Steigung nach rechts, Steigung nach oben) einer Blickrichtung mit y = 1."""
    p = np.asarray(pixels, float).reshape(-1, 2)
    d = np.column_stack([p[:, 0], np.ones(len(p)), p[:, 1]])
    return d / np.linalg.norm(d, axis=1, keepdims=True)


def pixel_of(point):
    v = point - EYE
    return [v[0] / v[1], v[2] / v[1]]


def joints_template(n=6):
    j = np.zeros((n, len(NAMES), 3))
    j[:, 1] = (-0.1, 0.0, 0.10)    # linker Knöchel
    j[:, 2] = (0.1, 0.0, 0.10)
    j[:, 3] = j[:, 1] + (0.0, -0.06, -0.07)   # Ferse (Vorlage, zeigt nach hinten)
    j[:, 4] = j[:, 2] + (0.0, -0.06, -0.07)
    j[:, 5] = j[:, 3] + (0.0, 0.25, 0.0)      # Zehe (Vorlage: nach vorn)
    j[:, 6] = j[:, 4] + (0.0, 0.25, 0.0)
    return j


class SpherePointTest(unittest.TestCase):
    def test_ray_through_point_on_sphere_finds_it(self):
        centre = np.array([0.0, 0.0, 0.1])
        target = centre + np.array([0.0, -0.1, -0.05])
        d = (target - EYE) / np.linalg.norm(target - EYE)
        got = ff.sphere_point(EYE, d, centre, np.linalg.norm(target - centre), prior=target)
        np.testing.assert_allclose(got, target, atol=1e-6)

    def test_prior_chooses_between_two_intersections(self):
        centre = np.array([0.0, 0.0, 0.1])
        d = (centre - EYE) / np.linalg.norm(centre - EYE)
        near = ff.sphere_point(EYE, d, centre, 0.2, prior=centre + [0, -0.2, 0])
        far = ff.sphere_point(EYE, d, centre, 0.2, prior=centre + [0, 0.2, 0])
        self.assertLess(near[1], far[1])

    def test_missing_the_sphere_gives_closest_point(self):
        centre = np.array([0.0, 0.0, 0.1])
        d = (centre + [1.0, 0, 0] - EYE)
        got = ff.sphere_point(EYE, d / np.linalg.norm(d), centre, 0.2, prior=centre)
        self.assertAlmostEqual(np.linalg.norm(got - centre), 0.2, places=6)


class MergeTest(unittest.TestCase):
    def kp(self, x, c):
        a = np.zeros((1, 17, 3))
        a[..., 0], a[..., 2] = x, c
        return a

    def test_both_sure_are_averaged_legs_favour_rtm(self):
        out = ff.merge_keypoints(self.kp(100, 0.9), self.kp(110, 0.9))
        self.assertAlmostEqual(out[0, 0, 0], 105.0)                   # Schulter: gleich
        self.assertGreater(out[0, 15, 0], 105.0)                      # Knöchel: näher an RTMPose

    def test_only_rtm_sure_takes_rtm(self):
        out = ff.merge_keypoints(self.kp(100, 0.1), self.kp(110, 0.8))
        self.assertEqual(out[0, 0, 0], 110.0)
        self.assertEqual(out[0, 0, 2], 0.8)

    def test_neither_sure_keeps_vitpose(self):
        out = ff.merge_keypoints(self.kp(100, 0.1), self.kp(110, 0.1))
        self.assertEqual(out[0, 0, 0], 100.0)

    def test_input_is_not_modified(self):
        v = self.kp(100, 0.9)
        ff.merge_keypoints(v, self.kp(110, 0.9))
        self.assertEqual(v[0, 0, 0], 100.0)


class FootPointsTest(unittest.TestCase):
    def test_toe_is_mean_of_big_and_small(self):
        k = np.zeros((1, 26, 3))
        k[0, 20] = (10, 20, 0.9)
        k[0, 22] = (14, 24, 0.8)
        k[0, 24] = (5, 5, 0.7)
        out = ff.foot_points(k)
        np.testing.assert_allclose(out[0, 0], [12, 22, 0.8])
        np.testing.assert_allclose(out[0, 2], [5, 5, 0.7])

    def test_one_toe_is_used_alone(self):
        k = np.zeros((1, 26, 3))
        k[0, 21] = (30, 40, 0.9)
        self.assertEqual(tuple(ff.foot_points(k)[0, 1]), (30, 40, 0.9))

    def test_unseen_has_zero_confidence(self):
        self.assertEqual(ff.foot_points(np.zeros((1, 26, 3)))[0, 0, 2], 0.0)


class ApplyTest(unittest.TestCase):
    def observed(self, j, i, side):
        """Wahre Fußpunkte als Bildpunkte: Fuß dreht um 45° nach außen."""
        ankle = j[i, 1 + side]
        heel = ankle + (0.03 * (1 if side else -1), -0.05, -0.07)
        toe = heel + np.array([0.18 * (1 if side else -1), 0.18, 0.0])
        return heel, toe

    def test_turned_foot_is_recovered(self):
        j = joints_template()
        pos = np.zeros((6, 2))
        foot2d = np.zeros((6, 4, 3))
        truth = {}
        for i in range(6):
            for side in (0, 1):
                heel, toe = self.observed(j, i, side)
                foot2d[i, 2 + side] = (*pixel_of(heel), 0.9)
                foot2d[i, side] = (*pixel_of(toe), 0.9)
                truth[(i, side)] = (heel, toe)
        out, changed = ff.apply(j, pos, foot2d, np.zeros(6), CAM, NAMES, fake_rays)
        self.assertGreater(changed, 0)
        for side, (heel_i, toe_i) in enumerate(((3, 5), (4, 6))):
            heel, toe = truth[(3, side)]
            # Länge Knöchel-Ferse bleibt; die Zehe zeigt jetzt schräg nach außen wie in Wahrheit
            self.assertAlmostEqual(np.linalg.norm(out[3, heel_i] - j[3, 1 + side]), np.linalg.norm(j[3, heel_i] - j[3, 1 + side]), places=5)
            self.assertAlmostEqual(np.linalg.norm(out[3, toe_i] - out[3, heel_i]), 0.25, places=5)
            truth_dir = (toe - heel) / np.linalg.norm(toe - heel)
            got_dir = (out[3, toe_i] - out[3, heel_i]) / 0.25
            self.assertGreater(float(truth_dir @ got_dir), 0.9)

    def test_unseen_frames_keep_the_template(self):
        j = joints_template()
        out, changed = ff.apply(j, np.zeros((6, 2)), np.zeros((6, 4, 3)), np.zeros(6), CAM, NAMES, fake_rays)
        np.testing.assert_allclose(out, j)
        self.assertEqual(changed, 0)

    def test_no_lens_keeps_the_template(self):
        j = joints_template()
        foot2d = np.zeros((6, 4, 3))
        foot2d[:, :, 2] = 0.9
        out, _ = ff.apply(j, np.zeros((6, 2)), foot2d, np.full(6, np.nan), CAM, NAMES, fake_rays)
        np.testing.assert_allclose(out, j)

    def test_nothing_goes_below_the_turf(self):
        j = joints_template()
        j[:, 1:3, 2] = 0.05
        j[:, 3:5, 2] = -0.02
        out, _ = ff.apply(j, np.zeros((6, 2)), np.zeros((6, 4, 3)), np.zeros(6), CAM, NAMES, fake_rays)
        self.assertTrue((out[:, 3:, 2] >= 0.0).all())


class SmoothTest(unittest.TestCase):
    def test_smooths_valid_and_leaves_invalid_nan(self):
        v = np.array([[0.0, 0, 0], [10.0, 0, 0], [0.0, 0, 0], [np.nan] * 3])
        out = ff.smooth_vectors(v, np.array([True, True, True, False]), half=1)
        self.assertAlmostEqual(out[1, 0], 10 / 3)
        self.assertTrue(np.isnan(out[3]).all())


if __name__ == "__main__":
    unittest.main()
