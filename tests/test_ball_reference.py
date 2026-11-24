import json
import tempfile
import unittest
from pathlib import Path

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import ball_reference as br


class ReferenceTest(unittest.TestCase):
    def test_add_replaces_contact_at_same_frame(self):
        ref = br.new("s", 30.0)
        br.add_contact(ref, 10, "touch")
        br.add_contact(ref, 10, "pass", "right-foot")
        self.assertEqual(len(ref["contacts"]), 1)
        self.assertEqual(ref["contacts"][0]["kind"], "pass")

    def test_contacts_are_sorted(self):
        ref = br.new("s", 30.0)
        for f in (30, 10, 20):
            br.add_contact(ref, f, "touch")
        self.assertEqual([c["frame"] for c in ref["contacts"]], [10, 20, 30])

    def test_unknown_kind_or_part_is_refused(self):
        ref = br.new("s", 30.0)
        with self.assertRaises(ValueError):
            br.add_contact(ref, 1, "dive")
        with self.assertRaises(ValueError):
            br.add_contact(ref, 1, "pass", "elbow")

    def test_remove(self):
        ref = br.new("s", 30.0)
        br.add_contact(ref, 10, "touch")
        br.remove_contact(ref, 10)
        self.assertEqual(ref["contacts"], [])

    def test_save_and_load_round_trip(self):
        ref = br.new("s", 29.97)
        br.add_contact(ref, 10, "shot", "left-foot", [0, 1, 2, 3, 4])
        path = Path(tempfile.mkdtemp()) / "ref.json"
        br.save(ref, path)
        self.assertEqual(br.load(path), ref)

    def test_no_names_or_images_can_be_stored(self):
        ref = br.new("s", 30.0)
        ref["contacts"].append({"frame": 1, "kind": "pass", "part": None, "box": None, "name": "Anna"})
        self.assertTrue(br.validate(ref))
        with self.assertRaises(ValueError):
            br.save(ref, Path(tempfile.mkdtemp()) / "x.json")
        ref2 = br.new("s", 30.0)
        ref2["image"] = "data:..."
        self.assertTrue(br.validate(ref2))

    def test_wrong_version_is_refused(self):
        path = Path(tempfile.mkdtemp()) / "x.json"
        path.write_text(json.dumps({"version": 99}))
        with self.assertRaises(ValueError):
            br.load(path)


if __name__ == "__main__":
    unittest.main()
