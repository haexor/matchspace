import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import helpers

TOOL = helpers.TOOLS / "no_veo_check.py"


class NoVeoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        (d / "veo").mkdir()
        (d / "veo" / "export.json").write_text("{}")
        (d / "veo" / "lens.json").write_text("{}")
        (d / "veo-szene-1").mkdir()
        self.d = d
        self.script = d / "tool.py"

    def run_tool(self, body, *extra):
        self.script.write_text("import sys\n" + body)
        return subprocess.run([sys.executable, str(TOOL), "--verbiete", str(self.d / "veo"), *extra, str(self.script)],
                              capture_output=True, text=True)

    def test_opening_a_forbidden_file_fails(self):
        r = self.run_tool(f"open({str(self.d / 'veo' / 'export.json')!r}).read()\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Veo", r.stderr)

    def test_listing_a_forbidden_folder_fails(self):
        r = self.run_tool(f"import os\nos.listdir({str(self.d / 'veo')!r})\n")
        self.assertNotEqual(r.returncode, 0)

    def test_allowed_file_and_output_folder_named_veo(self):
        r = self.run_tool(f"open({str(self.d / 'veo' / 'lens.json')!r}).read()\n"
                          f"open({str(self.d / 'veo-szene-1' / 'out.txt')!r}, 'w').write('x')\n",
                          "--erlaube", str(self.d / "veo" / "lens.json"))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_forbidden_path_in_arguments_fails_early(self):
        self.script.write_text("pass\n")
        r = subprocess.run([sys.executable, str(TOOL), "--verbiete", str(self.d / "veo"), str(self.script),
                            str(self.d / "veo" / "export.json")], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
