"""Controller navigation on the real window, driven under Broadway.

Runs tests/gamepad_ui.py in a private Broadway display (see
tests/run_gamepad_ui.sh). Broadway only lays the grid out on time while a
browser is connected, so the test is skipped unless GAMEDECK_BROWSER points
to a Chromium/Chrome binary (it is started headless).
"""

# pylint: disable=missing-function-docstring
import json
import os
import pwd
import shutil
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def clean_env() -> dict:
    """tests.support points HOME/XDG_* at a sandbox in this process: the
    browser should not inherit that"""
    keep = ("XDG_RUNTIME_DIR", "GAMEDECK_BROWSER", "GAMEDECK_PREFIX", "GAMEPAD_UI_DISPLAY")
    env = {key: os.environ[key] for key in keep if key in os.environ}
    env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    env["HOME"] = pwd.getpwuid(os.getuid()).pw_dir
    return env


@unittest.skipUnless(shutil.which("gtk4-broadwayd"), "gtk4-broadwayd is not installed")
@unittest.skipUnless(
    os.environ.get("GAMEDECK_BROWSER") and Path(os.environ["GAMEDECK_BROWSER"]).is_file(),
    "set GAMEDECK_BROWSER to a Chromium/Chrome binary",
)
class GamepadWindowTests(unittest.TestCase):
    def test_controller_navigates_the_window(self):
        out = subprocess.run(
            [str(REPO / "tests" / "run_gamepad_ui.sh")],
            capture_output=True, text=True, timeout=300, check=False,
            env=clean_env(),
        )
        line = next((l for l in out.stdout.splitlines() if l.startswith("RESULT ")), None)
        self.assertIsNotNone(line, out.stdout[-2000:] + out.stderr[-4000:])
        results = json.loads(line[len("RESULT "):])
        failed = [name for name, ok in results.items() if not ok]
        self.assertGreater(len(results), 25)
        self.assertEqual(failed, [], out.stderr[-3000:])


if __name__ == "__main__":
    unittest.main()
