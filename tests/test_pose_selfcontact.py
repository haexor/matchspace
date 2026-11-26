import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import pose_selfcontact as sc
from synth_poses import NAMES

I = {n: i for i, n in enumerate(NAMES)}


def standing(frames=3):
    """Aufrechte Figur, Arme hängen neben dem Rumpf (Becken 0,95 m, Hals 1,52 m; z hoch, vorn ist −y)."""
    p = np.zeros((frames, 20, 3))
    pts = {"pelvis": (0, 0, 0.95), "neck": (0, 0, 1.52), "head": (0, 0, 1.68), "nose": (0, -0.1, 1.70),
           "lShoulder": (0.18, 0, 1.46), "rShoulder": (-0.18, 0, 1.46), "lElbow": (0.24, 0, 1.2), "rElbow": (-0.24, 0, 1.2),
           "lWrist": (0.25, 0, 0.95), "rWrist": (-0.25, 0, 0.95), "lHip": (0.09, 0, 0.95), "rHip": (-0.09, 0, 0.95),
           "lKnee": (0.09, 0, 0.5), "rKnee": (-0.09, 0, 0.5), "lAnkle": (0.09, 0, 0.1), "rAnkle": (-0.09, 0, 0.1),
           "lHeel": (0.09, 0.05, 0.02), "rHeel": (-0.09, 0.05, 0.02), "lToe": (0.09, -0.15, 0.02), "rToe": (-0.09, -0.15, 0.02)}
    for name, xyz in pts.items():
        p[:, I[name]] = xyz
    return p


def hands_in_belly(frames=3):
    p = standing(frames)
    p[:, I["lElbow"]] = (0.12, -0.05, 1.2)         # Ellbogen vor dem Rumpf
    p[:, I["lWrist"]] = (0.0, 0.0, 1.1)            # Hand mitten im Bauch
    return p


def lengths(p):
    return [np.linalg.norm(p[:, I[a]] - p[:, I[b]], axis=-1) for a, b in (("lShoulder", "lElbow"), ("lElbow", "lWrist"))]


class SelfContactTest(unittest.TestCase):
    def test_hanging_arms_are_left_alone(self):
        p = standing()
        self.assertLess(sc.penetration(p).max(), 0.01)
        np.testing.assert_allclose(sc.keep_arms_out(p), p)

    def test_hand_in_the_belly_is_moved_out_and_bone_lengths_stay(self):
        p = hands_in_belly()
        self.assertGreater(sc.penetration(p)[:, 0].min(), 0.03)
        fixed = sc.keep_arms_out(p)
        self.assertLess(sc.penetration(fixed).max(), 0.01)
        for before, after in zip(lengths(p), lengths(fixed)):
            np.testing.assert_allclose(after, before, atol=1e-6)
        np.testing.assert_allclose(fixed[:, I["lShoulder"]], p[:, I["lShoulder"]])      # die Schulter bleibt, nur Ellbogen und Hand wandern

    def test_hand_behind_the_back_leaves_through_the_back(self):
        p = standing()
        p[:, I["rElbow"]] = (-0.12, 0.05, 1.2)
        p[:, I["rWrist"]] = (0.0, 0.0, 1.1)            # hinter dem Körper ist +y
        fixed = sc.keep_arms_out(p)
        self.assertLess(sc.penetration(fixed).max(), 0.01)
        self.assertGreater(fixed[:, I["rWrist"], 1].min(), -0.02)         # nicht nach vorn durch den Bauch geschoben

    def test_missing_frames_stay_missing(self):
        p = hands_in_belly(4)
        p[1] = np.nan
        fixed = sc.keep_arms_out(p)
        self.assertTrue(np.isnan(fixed[1]).all())
        self.assertFalse(np.isnan(fixed[0]).any())
        self.assertEqual(sc.penetration(p)[1].tolist(), [0.0, 0.0])


if __name__ == "__main__":
    unittest.main()
