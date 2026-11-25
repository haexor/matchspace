import unittest

from tests import helpers  # noqa: F401  (macht tools/ importierbar)
import viewer_shot as vs


class BrowserOptionsTest(unittest.TestCase):
    def test_without_nix_variables_the_environment_is_untouched(self):
        args, env = vs.browser_options({"PATH": "/bin", "HOME": "/h"})
        self.assertEqual(env, {"PATH": "/bin", "HOME": "/h"})
        self.assertIn("--use-angle=gl", args)

    def test_mesa_paths_go_to_the_browser_only(self):
        environ = {"PATH": "/bin", "LD_LIBRARY_PATH": "/host/lib", "PLAYWRIGHT_GL_LIBRARY_PATH": "/nix/mesa/lib:/nix/glvnd/lib",
                   "PLAYWRIGHT_GL_EGL_VENDOR": "/nix/mesa/50_mesa.json", "PLAYWRIGHT_GL_DRIVERS": "/nix/mesa/dri"}
        args, env = vs.browser_options(environ)
        self.assertEqual(env["LD_LIBRARY_PATH"], "/nix/mesa/lib:/nix/glvnd/lib")
        self.assertEqual(env["__EGL_VENDOR_LIBRARY_FILENAMES"], "/nix/mesa/50_mesa.json")
        self.assertEqual(env["LIBGL_DRIVERS_PATH"], "/nix/mesa/dri")
        self.assertEqual(env["LIBGL_ALWAYS_SOFTWARE"], "1")
        self.assertEqual(environ["LD_LIBRARY_PATH"], "/host/lib")             # die Shell bleibt unverändert

    def test_arguments_are_a_copy(self):
        args, _ = vs.browser_options({})
        args.append("--x")
        self.assertNotIn("--x", vs.GL_ARGS)


class UrlTest(unittest.TestCase):
    def test_minimal(self):
        self.assertEqual(vs.viewer_url(8000, "szene", None, None, None, True, True), "http://127.0.0.1:8000/?match=szene")

    def test_all_options(self):
        url = vs.viewer_url(8000, "szene", 3.2, "own-6", "follow", False, False)
        self.assertEqual(url, "http://127.0.0.1:8000/?match=szene&t=3.2&player=own-6&mode=follow&ui=0&ref=0")


if __name__ == "__main__":
    unittest.main()
