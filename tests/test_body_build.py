import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import body_build as bb
import body_pose as bp
import pose_limits


def person(shoulder=0.36, hip=0.20, thigh=0.45, shank=0.45, torso=0.55):
    """Ein Mensch (n=1, 70 Punkte), aufrecht, y nach unten: Beine unter dem Becken, Rumpf darüber."""
    kp = np.zeros((1, 70, 3))
    kp[0, bp.L_HIP], kp[0, bp.R_HIP] = (hip / 2, 0, 0), (-hip / 2, 0, 0)
    kp[0, bp.L_KNEE], kp[0, bp.R_KNEE] = (hip / 2, thigh, 0), (-hip / 2, thigh, 0)
    kp[0, bp.L_ANKLE], kp[0, bp.R_ANKLE] = (hip / 2, thigh + shank, 0), (-hip / 2, thigh + shank, 0)
    kp[0, bp.NECK] = (0, -torso, 0)
    kp[0, bp.L_SHOULDER], kp[0, bp.R_SHOULDER] = (shoulder / 2, -torso, 0), (-shoulder / 2, -torso, 0)
    kp[0, bp.L_ELBOW], kp[0, bp.R_ELBOW] = (shoulder / 2, -torso + 0.3, 0), (-shoulder / 2, -torso + 0.3, 0)
    kp[0, bp.L_WRIST], kp[0, bp.R_WRIST] = (shoulder / 2, -torso + 0.55, 0), (-shoulder / 2, -torso + 0.55, 0)
    return kp


def body_of(people, rows=30):
    """people: Liste (Kennung, Person); je rows Bilder, Boxhöhe 100 Pixel."""
    kp = np.concatenate([np.repeat(p, rows, axis=0) for _, p in people])
    player = np.repeat(np.arange(len(people)), rows)
    box = np.tile([0.0, 0.0, 100.0, 100.0], (len(kp), 1))
    return {"ids": np.array([i for i, _ in people]), "player": player, "kp3d": kp, "box": box}


class MeasureTest(unittest.TestCase):
    def test_wider_shoulders_than_the_others_give_a_factor_above_one(self):
        body = body_of([("a", person()), ("b", person()), ("wide", person(shoulder=0.40))])
        build = bb.measure(body)
        self.assertGreater(build["wide"]["shoulder"], 1.03)
        self.assertAlmostEqual(build["a"]["hip"], 1.0, places=2)

    def test_the_same_build_for_everybody_changes_nothing(self):
        build = bb.measure(body_of([("a", person()), ("b", person())]))
        for part in bb.PARTS:
            self.assertAlmostEqual(build["a"][part], 1.0, places=6)

    def test_scale_of_the_model_does_not_matter(self):
        body = body_of([("a", person()), ("b", person() * 1.3), ("wide", person(shoulder=0.40))])
        build = bb.measure(body)
        self.assertAlmostEqual(build["b"]["shoulder"], build["a"]["shoulder"], places=6)

    def test_few_rows_stay_near_the_template(self):
        few = body_of([("a", person()), ("b", person()), ("few", person(shoulder=0.40))], rows=30)
        keep = (few["player"] != 2) | (np.arange(len(few["player"])) % 30 < 3)
        few = {k: (v[keep] if isinstance(v, np.ndarray) and len(v) == len(keep) else v) for k, v in few.items()}
        self.assertLess(bb.measure(few)["few"]["shoulder"], bb.measure(body_of([("a", person()), ("b", person()), ("wide", person(shoulder=0.40))]))["wide"]["shoulder"])

    def test_factors_are_limited(self):
        build = bb.measure(body_of([("a", person()), ("b", person()), ("huge", person(shoulder=0.9))], rows=300))
        self.assertLessEqual(build["huge"]["shoulder"], bb.WIDTH_RANGE[1])

    def test_small_boxes_are_ignored(self):
        body = body_of([("a", person()), ("b", person())])
        body["box"][:] = [0, 0, 10, 10]
        self.assertEqual(bb.measure(body), {})

    def test_no_people_no_build(self):
        self.assertEqual(bb.measure({"player": np.array([], int), "ids": np.array([])}), {})


class ApplyTest(unittest.TestCase):
    def test_no_build_keeps_the_lengths(self):
        lengths = pose_limits.bone_lengths(1.6)
        self.assertEqual(bb.apply(lengths, None), lengths)

    def test_widths_scale_and_body_length_stays_the_measured_one(self):
        lengths = pose_limits.bone_lengths(1.6)
        build = {"shoulder": 1.1, "hip": 0.9, "thigh": 1.05, "shank": 1.0, "torso": 0.97, "upperArm": 1.0, "foreArm": 1.0}
        out = bb.apply(lengths, build)
        self.assertAlmostEqual(out["lShoulder"], lengths["lShoulder"] * 1.1)
        self.assertAlmostEqual(out["rHip"], lengths["rHip"] * 0.9)
        total = lambda d: d["lKnee"] + d["lAnkle"] + d["neck"]
        self.assertAlmostEqual(total(out), total(lengths))
        self.assertGreater(out["lKnee"] / out["lAnkle"], lengths["lKnee"] / lengths["lAnkle"])


if __name__ == "__main__":
    unittest.main()
