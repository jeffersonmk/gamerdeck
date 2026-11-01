"""Controller navigation on the real window, without opening anything on your screen.

Runs tests/gamepad_ui.py through tests/run_gamepad_ui.sh: on a virtual KWin
Wayland session when KWin is installed, else on a Broadway display with a
headless browser (GAMERDECK_BROWSER, a Chromium/Chrome binary).
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
    keep = ("XDG_RUNTIME_DIR", "GAMERDECK_BROWSER", "GAMERDECK_PREFIX", "GAMEPAD_UI_DISPLAY")
    env = {key: os.environ[key] for key in keep if key in os.environ}
    env["PATH"] = "/usr/local/bin:/usr/bin:/bin"
    env["HOME"] = pwd.getpwuid(os.getuid()).pw_dir
    return env


def has_virtual_wayland() -> bool:
    return bool(shutil.which("kwin_wayland") and shutil.which("dbus-run-session"))


def has_broadway_and_browser() -> bool:
    browser = os.environ.get("GAMERDECK_BROWSER")
    return bool(shutil.which("gtk4-broadwayd") and browser and Path(browser).is_file())


@unittest.skipUnless(
    has_virtual_wayland() or has_broadway_and_browser(),
    "needs kwin_wayland, or gtk4-broadwayd and GAMERDECK_BROWSER (a Chromium binary)",
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
