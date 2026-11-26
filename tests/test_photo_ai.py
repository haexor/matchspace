"""Bild-KI-Anbindung (tools/photo_ai.py, photo_ai_bench.py), Mannschaftserkennung (team_detect.py) und Abbildung der Fotos auf den Avatar (looks_from_photo.py)."""
import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import looks_from_photo as lfp
import photo_ai
import photo_ai_bench as bench
import team_detect

TEAM = {"shirt": "green", "shorts": "white", "socks": "white", "backText": [], "extra": "black long undershirt sleeves"}


def case(view, number):
    return {"id": f"x-{view}", "player": "x", "team": "t", "view": view, "number": number}


class PromptTest(unittest.TestCase):
    def test_unknown_number_without_text_gives_plain_back(self):
        p = bench.prompt_for(case("hinten", "?"), TEAM)
        self.assertIn("completely plain", p)
        self.assertNotIn("player number", p)

    def test_known_number_and_text(self):
        p = bench.prompt_for(case("hinten", "7"), dict(TEAM, backText=["SV Test"]))
        self.assertIn('"7"', p)
        self.assertIn('"SV Test"', p)

    def test_known_number_without_text_adds_no_lettering(self):
        p = bench.prompt_for(case("hinten", "7"), TEAM)
        self.assertIn('"7"', p)
        self.assertNotIn("above it", p)

    def test_front_is_plain_by_default(self):
        self.assertIn("completely plain", bench.prompt_for(case("vorn", "7"), TEAM))
        self.assertIn("a crest", bench.prompt_for(case("vorn", "7"), dict(TEAM, front="a crest")))


class PlanTest(unittest.TestCase):
    def test_number_of(self):
        self.assertEqual(photo_ai.number_of("own-6"), "6")
        self.assertEqual(photo_ai.number_of("opponent-15"), "15")
        self.assertEqual(photo_ai.number_of("opponent-1001"), "?")     # Kennungen ab 1000 sind keine Trikotnummern

    def make(self, folder):
        d = Path(folder)
        (d / "own-6").mkdir(parents=True)
        cv2.imwrite(str(d / "own-6" / "hinten.png"), np.full((60, 30, 3), 90, np.uint8))
        (d / "index.json").write_text(json.dumps({"own-6": {"team": "own", "views": {"hinten": {}}}}))
        return d

    def test_jobs_digest_changes_with_input_and_prompt_and_cache_hits(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.make(tmp)
            jobs = photo_ai.jobs(d, {"own": TEAM}, ("hinten", "vorn"), set())
            self.assertEqual([j["case"]["id"] for j in jobs], ["own-6-hinten"])       # vorn: kein Ausschnitt
            again = photo_ai.jobs(d, {"own": TEAM}, ("hinten",), set())
            self.assertEqual(jobs[0]["digest"], again[0]["digest"])
            other = photo_ai.jobs(d, {"own": dict(TEAM, backText=["FC X"])}, ("hinten",), set())
            self.assertNotEqual(jobs[0]["digest"], other[0]["digest"])
            out = Path(tmp) / "ki"
            (out / "own-6").mkdir(parents=True)
            (out / "own-6" / "hinten.png").write_bytes(b"x")
            index = {"own-6": {"hinten": {"ok": True, "model": photo_ai.MODEL, "digest": jobs[0]["digest"]}}}
            self.assertTrue(photo_ai.cached(index, jobs[0], photo_ai.MODEL, out))
            self.assertFalse(photo_ai.cached(index, other[0], photo_ai.MODEL, out))
            self.assertFalse(photo_ai.cached(index, jobs[0], "other/model", out))

    def test_front_gets_back_as_reference_once_it_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = self.make(tmp)
            cv2.imwrite(str(d / "own-6" / "vorn.png"), np.full((60, 30, 3), 120, np.uint8))
            index = json.loads((d / "index.json").read_text())
            index["own-6"]["views"]["vorn"] = {}
            (d / "index.json").write_text(json.dumps(index))
            out = Path(tmp) / "ki"
            front = lambda: [j for j in photo_ai.jobs(d, {"own": TEAM}, ("hinten", "vorn"), set(), out) if j["case"]["view"] == "vorn"][0]   # noqa: E731
            self.assertIsNone(front()["ref"])
            (out / "own-6").mkdir(parents=True)
            (out / "own-6" / "hinten.png").write_bytes(cv2.imencode(".png", np.zeros((8, 8, 3), np.uint8))[1].tobytes())
            self.assertIsNotNone(front()["ref"])
            self.assertIn("Image 2", front()["prompt"])


class CostTest(unittest.TestCase):
    def test_cost_prefers_openrouter_figure(self):
        self.assertEqual(bench.cost_of({"cost": 0.012}, {}), (0.012, "openrouter"))
        cost, source = bench.cost_of({"prompt_tokens": 1000, "completion_tokens": 10}, {"prompt": "0.000001", "completion": "0.00001"})
        self.assertEqual(source, "geschätzt")
        self.assertAlmostEqual(cost, 0.0011)


class TeamDetectTest(unittest.TestCase):
    def test_colour_names_from_hue_and_saturation(self):
        for rgb, name in (((200, 30, 40), "red"), ((110, 0, 0), "red"), ((20, 130, 40), "green"), ((111, 142, 170), "white"), ((10, 10, 10), "black"), ((110, 110, 110), "grey")):
            self.assertEqual(team_detect.colour_name(np.array(rgb[::-1], float)), name, rgb)


class PhotoMappingTest(unittest.TestCase):
    def test_arm_is_rotated_from_t_pose_into_the_photo_arm(self):
        # linker Arm im T: Schulter (0.2, 1.4), Ellbogen (0.5, 1.4); im Foto (Rückansicht) hängt er: Schulter (400, 300), Ellbogen (400, 600)
        joints = {"upperarm_l": np.array([0.2, 1.4, 0.0]), "lowerarm_l": np.array([0.5, 1.4, 0.0]), "hand_l": np.array([0.8, 1.4, 0.0])}
        kp = np.zeros((17, 2))
        kp[5], kp[7], kp[9] = (400, 300), (400, 600), (400, 900)
        fm = {"kp": kp, "conf": np.ones(17), "view": "hinten"}
        pts = np.array([[0.2, 1.4, 0.0], [0.5, 1.4, 0.0], [0.35, 1.45, 0.0]])        # Schulter, Ellbogen, Mitte 5 cm oben
        u, v = lfp.project_arm(fm, "upperarm_l", pts, joints)
        self.assertAlmostEqual(u[0], 400, delta=1e-6)
        self.assertAlmostEqual(v[0], 300, delta=1e-6)
        self.assertAlmostEqual(u[1], 400, delta=1e-6)       # Ellbogen im Foto
        self.assertAlmostEqual(v[1], 600, delta=1e-6)
        self.assertAlmostEqual(v[2], 450, delta=1e-6)       # halbe Strecke
        self.assertGreater(abs(u[2] - 400), 1)               # 5 cm Versatz quer zum Knochen wird zur Breite

    def test_unsure_keypoints_skip_the_arm(self):
        conf = np.ones(17)
        conf[7] = 0.2
        fm = {"kp": np.zeros((17, 2)), "conf": conf, "view": "vorn"}
        joints = {"upperarm_l": np.zeros(3), "lowerarm_l": np.array([0.3, 0, 0]), "hand_l": np.array([0.6, 0, 0])}
        self.assertIsNone(lfp.project_arm(fm, "upperarm_l", np.zeros((1, 3)), joints))

    def test_snap_inside_moves_gap_pixels_to_the_nearest_sleeve_pixel(self):
        inner = np.zeros((20, 20), bool)
        inner[:, :5] = True
        sy, sx, dist = lfp.snap_inside(inner)
        self.assertEqual((sy[7, 12], sx[7, 12]), (7, 4))
        self.assertEqual(sx[3, 2], 2)
        self.assertGreater(dist[7, 12], 0)

    def test_grass_mask_ignores_the_person_and_catches_grass_in_a_gap(self):
        img = np.zeros((60, 60, 3), np.uint8)
        img[:] = (52, 125, 100)           # Rasen (BGR)
        img[:, 25:35] = (20, 20, 160)     # Person (rot)
        person = np.zeros((60, 60), bool)
        person[:, 20:40] = True           # Maske größer als die Person (füllt die Lücke)
        grass = lfp.grass_mask(img, person)
        self.assertTrue(grass[30, 22])    # Rasen innerhalb der Maske
        self.assertFalse(grass[30, 30])   # Trikot


if __name__ == "__main__":
    unittest.main()
