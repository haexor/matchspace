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

    def test_penetration_depth_uses_the_players_scale(self):
        p = hands_in_belly(1)
        np.testing.assert_allclose(sc.penetration(p * 2), sc.penetration(p) * 2, atol=1e-6)

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


class SceneFileTest(unittest.TestCase):
    def test_a_finished_scene_is_rewritten_in_a_new_folder(self):
        import json
        import tempfile
        from pathlib import Path
        p = hands_in_belly(2)
        raw = np.round(p / 0.001).astype("<i2")[:, None]          # (Bilder, Spieler = 1, 20, 3)
        meta = {"frames": 2, "entities": [{"kind": "player", "id": "own-1"}],
                "poses": {"chunks": 1, "chunkFrames": 1500, "path": "poses/{chunk}.bin", "missing": -32768, "scale": 0.001}}
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / "src", Path(tmp) / "out"
            (src / "poses").mkdir(parents=True)
            (src / "meta.json").write_text(json.dumps(meta))
            raw.tofile(src / "poses" / "000.bin")
            before, after = sc.fix_scene(src, out)
            self.assertEqual((before, after), (2, 0))
            self.assertTrue((np.fromfile(src / "poses" / "000.bin", "<i2") == raw.ravel()).all())      # die Quelle bleibt unverändert
            fixed = np.fromfile(out / "poses" / "000.bin", "<i2").reshape(2, 1, 20, 3) * 0.001
            self.assertLess(sc.penetration(fixed[:, 0]).max(), 0.01)

    def test_a_player_on_the_ground_is_left_unchanged(self):
        import json
        import tempfile
        from pathlib import Path
        p = hands_in_belly(1)
        p[:, :, 2] -= 0.6
        raw = np.round(p / 0.001).astype("<i2")[:, None]
        meta = {"frames": 1, "entities": [{"kind": "player", "id": "own-1"}],
                "poses": {"chunks": 1, "chunkFrames": 1500, "path": "poses/{chunk}.bin", "missing": -32768, "scale": 0.001}}
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / "src", Path(tmp) / "out"
            (src / "poses").mkdir(parents=True)
            (src / "meta.json").write_text(json.dumps(meta))
            raw.tofile(src / "poses" / "000.bin")
            sc.fix_scene(src, out)
            actual = np.fromfile(out / "poses" / "000.bin", "<i2")
            np.testing.assert_array_equal(actual, raw.ravel())


if __name__ == "__main__":
    unittest.main()
