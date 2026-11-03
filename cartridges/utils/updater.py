# updater.py
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Update Gamerdeck from the app, with the same script a terminal would use.

Only an installation made by scripts/install-source.sh can do this: it writes
where the code is (share/gamerdeck/source-dir), and the update is a
`scripts/update.sh` run in that folder (git pull, then install again).
"""

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

UP_TO_DATE = 0
UPDATE_AVAILABLE = 10


@dataclass(frozen=True)
class UpdateResult:
    ok: bool
    code: int
    output: str

    @property
    def last_line(self) -> str:
        lines = [line for line in self.output.splitlines() if line.strip()]
        return lines[-1] if lines else ""


def default_prefix() -> Path:
    """The prefix this code was installed in (…/lib/python3.x/site-packages/cartridges/utils)"""
    return Path(__file__).resolve().parents[4].parent


def source_dir(prefix: Optional[Path] = None) -> Optional[Path]:
    """The folder with the code and scripts, if this installation knows it"""
    prefix = prefix or default_prefix()
    try:
        folder = Path(
            (prefix / "share" / "gamerdeck" / "source-dir").read_text().strip()
        )
    except (OSError, ValueError):
        return None
    if (folder / "scripts" / "update.sh").is_file() and (folder / ".git").exists():
        return folder
    return None


def source_version(folder: Path) -> str:
    """The version written in the code, as of the last download"""
    try:
        text = (folder / "meson.build").read_text()
    except OSError:
        return ""
    found = re.search(r"^\s*version:\s*'([^']+)'", text, re.M)
    return found.group(1) if found else ""


def _run(folder: Path, args: list[str], prefix: Path, timeout: int) -> UpdateResult:
    env = dict(os.environ)
    # The desktop session does not always have the user's tools in the PATH
    env["PATH"] = os.pathsep.join(
        [str(Path.home() / ".local" / "bin"), "/usr/local/bin", "/usr/bin", "/bin"]
        + [p for p in env.get("PATH", "").split(os.pathsep) if p]
    )
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        done = subprocess.run(
            [str(folder / "scripts" / "update.sh"), *args, "--prefix", str(prefix)],
            cwd=folder,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return UpdateResult(False, -1, f"{type(error).__name__}: {error}")
    output = (done.stdout or "") + (done.stderr or "")
    return UpdateResult(done.returncode in (UP_TO_DATE, UPDATE_AVAILABLE), done.returncode, output)


def check(folder: Path, prefix: Optional[Path] = None) -> UpdateResult:
    """Ask GitHub if there is a newer version (`code` 10: there is). Blocking."""
    return _run(folder, ["--check"], prefix or default_prefix(), 60)


def update(folder: Path, prefix: Optional[Path] = None) -> UpdateResult:
    """Download and install the newest version. Blocking, can take minutes."""
    result = _run(folder, [], prefix or default_prefix(), 900)
    return UpdateResult(result.code == UP_TO_DATE, result.code, result.output)
