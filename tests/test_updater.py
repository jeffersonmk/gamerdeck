"""scripts/update.sh and the in-app updater, against a throwaway git repository."""

# pylint: disable=missing-function-docstring
import os
import shutil
import subprocess
import unittest
from pathlib import Path

from tests.support import REPO, TMP  # noqa: F401  (sandbox first)

from cartridges.utils import updater  # noqa: E402

GIT = ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false"]


def git(cwd, *args):
    return subprocess.run([*GIT, *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def write_version(clone, version):
    (clone / "meson.build").write_text(f"project('x',\n  version: '{version}',\n)\n")
    git(clone, "add", "-A")
    git(clone, "commit", "-qm", f"v{version}")


@unittest.skipUnless(shutil.which("git"), "needs git")
class UpdateScriptTests(unittest.TestCase):
    def setUp(self):
        base = Path(TMP) / self.id().split(".")[-1]
        self.origin, self.clone, self.author = base / "origin.git", base / "clone", base / "author"
        base.mkdir()
        git(base, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(base, "clone", "-q", str(self.origin), str(self.author))
        (self.author / "scripts").mkdir()
        shutil.copy(REPO / "scripts" / "update.sh", self.author / "scripts" / "update.sh")
        # The installer is replaced by a stub that records it ran, with its arguments
        (self.author / "scripts" / "install-source.sh").write_text(
            '#!/bin/sh\necho "$@" >> "$(dirname "$0")/../installed.log"\n'
        )
        for name in ("update.sh", "install-source.sh"):
            (self.author / "scripts" / name).chmod(0o755)
        git(self.author, "branch", "-M", "main")
        write_version(self.author, "1.0.0")
        git(self.author, "push", "-q", "-u", "origin", "main")
        git(base, "clone", "-q", str(self.origin), str(self.clone))
        self.prefix = base / "prefix"
        (self.prefix / "share" / "gamerdeck").mkdir(parents=True)
        (self.prefix / "share" / "gamerdeck" / "source-dir").write_text(f"{self.clone}\n")

    def publish(self, version):
        write_version(self.author, version)
        git(self.author, "push", "-q")

    def installed(self):
        log = self.clone / "installed.log"
        return log.read_text().splitlines() if log.exists() else []

    def test_source_dir_is_found_only_for_a_real_clone(self):
        self.assertEqual(updater.source_dir(self.prefix), self.clone)
        (self.prefix / "share" / "gamerdeck" / "source-dir").write_text("/nowhere\n")
        self.assertIsNone(updater.source_dir(self.prefix))
        self.assertIsNone(updater.source_dir(self.prefix / "empty"))

    def test_check_says_when_up_to_date_and_when_not(self):
        result = updater.check(self.clone, self.prefix)
        self.assertEqual((result.ok, result.code), (True, updater.UP_TO_DATE))
        self.publish("1.1.0")
        result = updater.check(self.clone, self.prefix)
        self.assertEqual((result.ok, result.code), (True, updater.UPDATE_AVAILABLE))
        self.assertEqual(self.installed(), [])  # checking installs nothing

    def test_update_downloads_and_installs_in_the_prefix(self):
        self.publish("1.1.0")
        result = updater.update(self.clone, self.prefix)
        self.assertTrue(result.ok, result.output)
        self.assertEqual(updater.source_version(self.clone), "1.1.0")
        self.assertEqual(self.installed(), [f"--prefix {self.prefix}"])

    def test_nothing_new_installs_nothing(self):
        result = updater.update(self.clone, self.prefix)
        self.assertTrue(result.ok, result.output)
        self.assertIn("already up to date", result.output)
        self.assertEqual(self.installed(), [])

    def test_local_changes_that_conflict_give_a_clear_error(self):
        self.publish("1.1.0")
        (self.clone / "meson.build").write_text("edited\n")
        result = updater.update(self.clone, self.prefix)
        self.assertFalse(result.ok)
        self.assertIn("Could not apply", result.output)
        self.assertEqual(self.installed(), [])

    def test_a_folder_that_is_not_a_clone_is_refused(self):
        plain = Path(TMP) / "plain"
        (plain / "scripts").mkdir(parents=True)
        shutil.copy(REPO / "scripts" / "update.sh", plain / "scripts" / "update.sh")
        done = subprocess.run([str(plain / "scripts" / "update.sh")], capture_output=True,
                              text=True, check=False, env={**os.environ})
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("not a git clone", done.stderr)


if __name__ == "__main__":
    unittest.main()
