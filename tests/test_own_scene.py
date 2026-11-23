import unittest

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import own_scene


class AttachBallTest(unittest.TestCase):
    def test_ball_in_reach_is_pulled_toward_the_toe(self):
        T = 40
        feet = np.zeros((T, 1, 2))
        ball = np.tile([0.5, 0.0], (T, 1))           # 0,5 m vor der Fußspitze, innerhalb BALL_REACH
        mid = np.linalg.norm(own_scene.attach_ball(ball, feet, 25)[T // 2])
        self.assertLess(mid, 0.45)
        self.assertGreater(mid, own_scene.BALL_AT_FOOT)

    def test_ball_near_the_toe_ends_at_contact_distance(self):
        T = 40
        feet = np.zeros((T, 1, 2))
        ball = np.tile([0.2, 0.0], (T, 1))
        mid = np.linalg.norm(own_scene.attach_ball(ball, feet, 25)[T // 2])
        self.assertAlmostEqual(mid, own_scene.BALL_AT_FOOT, delta=0.02)

    def test_ball_out_of_reach_stays(self):
        T = 40
        feet = np.zeros((T, 1, 2))
        ball = np.tile([own_scene.BALL_REACH + 0.5, 0.0], (T, 1))
        np.testing.assert_allclose(own_scene.attach_ball(ball, feet, 25), ball)

    def test_no_feet_leaves_ball(self):
        feet = np.full((10, 2, 2), np.nan)
        ball = np.tile([1.0, 2.0], (10, 1))
        np.testing.assert_allclose(own_scene.attach_ball(ball, feet, 25), ball)


class OwnBallTest(unittest.TestCase):
    def test_short_gap_is_bridged_straight(self):
        track = np.array([[0.0, 0.0], [np.nan, np.nan], [np.nan, np.nan], [3.0, 0.0]])
        filled = own_scene.own_ball(track, max_gap=5)
        np.testing.assert_allclose(filled[:, 0], [0, 1, 2, 3])

    def test_long_gap_holds_last_then_next(self):
        track = np.full((12, 2), np.nan)
        track[0], track[11] = [0.0, 0.0], [11.0, 0.0]
        filled = own_scene.own_ball(track, max_gap=3)
        np.testing.assert_allclose(filled[1:6, 0], 0.0)
        np.testing.assert_allclose(filled[6:11, 0], 11.0)

    def test_edges_hold_nearest(self):
        track = np.full((6, 2), np.nan)
        track[2], track[3] = [2.0, 1.0], [3.0, 1.0]
        filled = own_scene.own_ball(track, max_gap=10)
        np.testing.assert_allclose(filled[:2, 0], 2.0)
        np.testing.assert_allclose(filled[4:, 0], 3.0)

    def test_nothing_found_stays_nan(self):
        track = np.full((5, 2), np.nan)
        self.assertTrue(np.isnan(own_scene.own_ball(track, 3)).all())


class DropSamePlaceTest(unittest.TestCase):
    def test_shorter_duplicate_gives_way(self):
        n = 3
        long_rows = np.zeros((n, 9))
        short_rows = np.zeros((n, 9))
        short_rows[0] = np.nan
        obs = {("own", 1001): long_rows, ("own", 1002): short_rows}
        where = [{("own", 1001): np.array([0.0, 0.0]), ("own", 1002): np.array([0.2, 0.0])} for _ in range(n)]
        removed = own_scene.drop_same_place(obs, where)
        self.assertEqual(removed, 3)
        self.assertTrue(all(("own", 1002) not in w for w in where))

    def test_other_team_is_kept(self):
        obs = {("own", 1001): np.zeros((1, 9)), ("opponent", 1001): np.zeros((1, 9))}
        where = [{("own", 1001): np.zeros(2), ("opponent", 1001): np.zeros(2)}]
        self.assertEqual(own_scene.drop_same_place(obs, where), 0)


class PlayerEntityTest(unittest.TestCase):
    def test_known_number(self):
        self.assertEqual(own_scene.player_entity(("own", 15), False, 1),
                         {"id": "own-15", "kind": "player", "team": "own", "number": 15})

    def test_unknown_number_keeps_track_name(self):
        e = own_scene.player_entity(("own", own_scene.OWN_ID + 4), False, 4)
        self.assertEqual(e, {"id": "own-1004", "kind": "player", "team": "own", "label": "S4"})

    def test_unknown_keeper(self):
        e = own_scene.player_entity(("own", own_scene.OWN_ID + 1), True, 1)
        self.assertEqual((e["label"], e["role"]), ("TW", "goalkeeper"))
        self.assertNotIn("number", e)

    def test_ids_round_trip_without_overlap(self):
        ids = {own_scene.player_entity(("own", k), False, 1)["id"] for k in list(range(1, 100)) + [own_scene.OWN_ID + j for j in range(1, 60)]}
        self.assertEqual(len(ids), 99 + 59)
        for i in ids:
            self.assertIn(int(i.rsplit("-", 1)[1]), list(range(1, 100)) + list(range(own_scene.OWN_ID + 1, own_scene.OWN_ID + 60)))

    def test_no_image_data(self):
        e = own_scene.player_entity(("opponent", 7), False, 2)
        self.assertTrue(set(e) <= {"id", "kind", "team", "number", "label", "role"})


if __name__ == "__main__":
    unittest.main()


class IdentityFileTest(unittest.TestCase):
    """{det}.identity.json: welche Erkennung gehört zu welchem Spieler (specs/003-eigene-referenz/data-model.md)."""

    def row(self, lens, box):
        return np.array([1.0, 2.0, 0, lens, 10, 20, 30, 80, box], float)

    def players(self):
        return {"own-7": ("own", False, 7, {f: self.row(0, 3) for f in (5, 3, 4)}),
                "opponent-1001": ("opponent", True, None, {f: self.row(1, 0) for f in range(2)})}

    def write(self, players, events=()):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scene.det.json.identity.json"
            own_scene.write_identity(path, players, list(events), {"own-7": [[7, 0.98], [1, 0.01]]}, 29.97)
            return json.loads(path.read_text())

    def test_form(self):
        data = self.write(self.players(), [{"kind": "split", "frame": 4, "reason": "colour", "detections": [[3, 0, 3], [4, 0, 3]]}])
        self.assertEqual(set(data), {"fps", "players", "events", "numbers", "stamp"})
        p = data["players"]["own-7"]
        self.assertEqual((p["team"], p["keeper"], p["number"]), ("own", False, 7))
        self.assertEqual(p["detections"], [[3, 0, 3], [4, 0, 3], [5, 0, 3]])
        self.assertTrue(data["players"]["opponent-1001"]["keeper"])
        self.assertEqual(data["events"][0]["players"], ["own-7", "own-7"])
        self.assertEqual(data["numbers"]["own-7"][0], [7, 0.98])

    def test_no_positions_or_images(self):
        text = str(self.write(self.players()))
        self.assertNotIn("2.0", text)   # keine Bodenlagen

    def test_stamp_follows_detections(self):
        a = self.write(self.players())["stamp"]
        self.assertEqual(a, self.write(self.players())["stamp"])
        changed = self.players()
        changed["own-7"][3][6] = self.row(0, 4)
        self.assertNotEqual(a, self.write(changed)["stamp"])
