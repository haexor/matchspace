import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import scene_output


class BallEventsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.det = str(Path(self.tmp.name) / "x.det.json")
        self.entities = [{"id": "own-2", "kind": "player"}, {"id": "own-9", "kind": "player"}, {"id": "ball", "kind": "ball"}]
        self.xy = np.zeros((100, 3, 2))
        self.xy[:, 0] = [10.0, -27.0]      # nah am Ball
        self.xy[:, 1] = [40.0, 0.0]
        self.xy[:, 2] = [10.5, -27.5]

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, time):
        Path(f"{self.det}.outlook.json").write_text(json.dumps({
            "events": [{"kind": "throw-in", "time": time, "pos": [10.5, -27.5], "height": 1.7}],
            "flights": [{"t_start": 2.0, "t_end": 3.0, "apex": 2.0, "speed": 9.0, "reliable": True, "continuation": None}], "note": "n"}))

    def test_missing_file_gives_nothing(self):
        self.assertEqual(scene_output.ball_events(self.det, self.xy, self.entities, 2), {})

    def test_thrower_is_the_nearest_player_and_times_are_output_frames(self):
        self.write(2.0)
        out = scene_output.ball_events(self.det, self.xy, self.entities, 2, fps=25)
        self.assertEqual(out["events"][0]["frame"], 50)
        self.assertEqual(out["events"][0]["player"], "own-2")
        self.assertEqual((out["ballFlights"][0]["fromFrame"], out["ballFlights"][0]["toFrame"]), (50, 75))

    def test_contacts_inside_a_held_run_are_dropped_but_the_release_stays(self):
        Path(f"{self.det}.outlook.json").write_text(json.dumps({
            "events": [], "flights": [], "note": "n",
            "contacts": [{"time": 1.0, "kind": "pass", "speed_in": 1.0, "speed_out": 9.0, "confidence": 1.0},
                         {"time": 2.9, "kind": "pass", "speed_in": 1.0, "speed_out": 9.0, "confidence": 1.0},
                         {"time": 3.6, "kind": "touch", "speed_in": 1.0, "speed_out": 2.0, "confidence": 1.0}]}))
        held = [{"fromFrame": 0, "toFrame": 74, "player": "own-2"}]
        out = scene_output.ball_events(self.det, self.xy, self.entities, 2, fps=25, held=held)
        self.assertEqual([c["frame"] for c in out["ballContacts"]], [72, 90])

    def test_nobody_in_reach_means_no_player(self):
        self.write(2.0)
        self.xy[:, 0] = [30.0, 5.0]
        out = scene_output.ball_events(self.det, self.xy, self.entities, 2, fps=25)
        self.assertIsNone(out["events"][0]["player"])

    def test_frame_is_clamped_to_the_scene(self):
        self.write(99.0)
        out = scene_output.ball_events(self.det, self.xy, self.entities, 2, fps=25)
        self.assertEqual(out["events"][0]["frame"], 99)


if __name__ == "__main__":
    unittest.main()
