import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import reference as ref
import review_server as rv

BOX = [10, 10, 20, 40]


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        (d / "scene.mp4").write_bytes(bytes(range(256)) * 4)
        det = d / "scene.det.json"
        det.write_text(json.dumps({"fps": 10, "lensSize": [64, 64], "frames": []}))
        identity = {"fps": 10, "stamp": "x", "players": {
            "a": {"team": "own", "keeper": False, "number": None, "detections": [[f, 0, 0] for f in range(100)]},
            "b": {"team": "own", "keeper": False, "number": None, "detections": [[f, 0, 1] for f in range(100)]}}}
        Path(f"{det}.identity.json").write_text(json.dumps(identity))
        part = lambda player, letter, f, box: ref.Participant(player, letter, [f, 0, box, *BOX], {f: BOX})  # noqa: E731
        spot = ref.Spot("s1", ["occlusion"], 50, 35, 65, 0, [0, 0, 64, 64],
                        [part("a", "A", 49, 0), part("b", "B", 49, 1)], [part("a", "A", 50, 0), part("b", "B", 50, 1)],
                        {"A": "A", "B": "B"}, 2.0)
        self.ref_path = Path(f"{det}.reference.json")
        self.ref_path.write_text(json.dumps(ref.to_json("scene", "x", [spot], [], 1)))
        web = d / "web"
        web.mkdir()
        for name in ("index.html", "review.js", "review.css"):
            (web / name).write_text(name)
        self.server = rv.make_server(rv.Review(d / "scene.mp4", det, web), 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def get(self, path, headers=None):
        return urllib.request.urlopen(urllib.request.Request(self.base + path, headers=headers or {}))

    def post(self, body):
        req = urllib.request.Request(self.base + "/answer", json.dumps(body).encode(), {"Content-Type": "application/json"})
        return urllib.request.urlopen(req)

    def test_binds_only_to_localhost(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_video_range(self):
        r = self.get("/video", {"Range": "bytes=0-99"})
        self.assertEqual((r.status, len(r.read()), r.headers["Content-Range"]), (206, 100, "bytes 0-99/1024"))

    def test_page_and_spots(self):
        self.assertEqual(self.get("/").read(), b"index.html")
        data = json.loads(self.get("/spots").read())
        self.assertEqual((len(data["spots"]), data["open"], data["fps"]), (1, 1, 10))

    def test_answer_is_saved_and_reloadable(self):
        r = json.loads(self.post({"spot": "s1", "choice": "swapped", "numbers": {"A": 7}}).read())
        self.assertEqual((r["ok"], r["open"]), (True, 0))
        spots, answers, _ = ref.from_json(json.loads(self.ref_path.read_text()))
        self.assertEqual((answers[0].choice, answers[0].numbers), ("swapped", {"A": 7}))
        self.assertIn("A", answers[0].anchors)

    def test_contradiction_comes_back_as_warning(self):
        r = json.loads(self.post({"spot": "s1", "choice": "mapped", "mapping": {"A": "A", "B": "A"}}).read())
        self.assertTrue(r["ok"])
        self.assertTrue(any("zwei Orten" in w for w in r["warnings"]))

    def test_bad_answer_is_refused(self):
        for body in ({"spot": "s1", "choice": "maybe"}, {"spot": "nope", "choice": "proposed"},
                     {"spot": "s1", "choice": "mapped", "mapping": {"A": "Z"}},
                     {"spot": "s1", "choice": "proposed", "numbers": {"A": 100}}):
            with self.assertRaises(urllib.error.HTTPError) as e:
                self.post(body)
            self.assertEqual(e.exception.code, 400)
        self.assertEqual(ref.from_json(json.loads(self.ref_path.read_text()))[1], [])

    def test_other_paths_are_not_served(self):
        for path in ("/../scene.det.json", "/scene.mp4", "/web/index.html"):
            with self.assertRaises(urllib.error.HTTPError) as e:
                self.get(path)
            self.assertEqual(e.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
