"""The version of the app is written in two files that must agree

`meson.build` gives the version the app reports, and the newest `<release>` of
the metainfo is what the About dialog shows as its release notes and what the
release workflow publishes. A release made with only one of them changed would
ship the wrong notes.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class ReleaseTests(unittest.TestCase):
    def test_meson_and_the_metainfo_have_the_same_version(self):
        meson = (ROOT / "meson.build").read_text(encoding="utf-8")
        metainfo = (ROOT / "data" / "page.kramo.Cartridges.metainfo.xml.in").read_text(
            encoding="utf-8"
        )
        project_version = re.search(r"^\s*version:\s*'([^']+)'", meson, re.M)
        newest_release = re.search(r'<release version="([^"]+)"', metainfo)
        self.assertIsNotNone(project_version)
        self.assertIsNotNone(newest_release)
        self.assertEqual(project_version.group(1), newest_release.group(1))

    def test_the_releases_are_newest_first(self):
        metainfo = (ROOT / "data" / "page.kramo.Cartridges.metainfo.xml.in").read_text(
            encoding="utf-8"
        )
        dates = re.findall(r'<release version="[^"]+" date="([^"]+)"', metainfo)
        self.assertTrue(dates)
        self.assertEqual(dates, sorted(dates, reverse=True))


if __name__ == "__main__":
    unittest.main()
