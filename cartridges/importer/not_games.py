# not_games.py
#
# Copyright 2026 Gamerdeck contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tell games apart from game launchers, tools and emulators

Sources only know that something is installed next to games: a desktop entry
in the "Game" category can be Steam itself, an overlay configurator or an
emulator, and Steam lists Proton and its runtimes as installed "apps". Games
added by hand are never filtered.
"""

import re
import shlex
from pathlib import PurePath
from typing import Iterable

# Desktop entry categories of programs that are not games, even when they
# also say "Game" (Steam: Network;FileTransfer;Game, Lutris: Game;PackageManager)
NOT_GAME_CATEGORIES = frozenset(
    {
        "Network",
        "FileTransfer",
        "Utility",
        "PackageManager",
        "System",
        "Settings",
        "Development",
        "Emulator",
        "Monitor",
        "Audio",
        "AudioVideo",
        "Video",
        "Graphics",
        "Office",
    }
)

# Launchers, stores, tools and emulators, by name (see `normalize`)
NOT_GAME_NAMES = frozenset(
    {
        # Stores and launchers
        "steam",
        "epic games launcher",
        "epic games store",
        "epic games",
        "heroic games launcher",
        "heroic",
        "lutris",
        "faugus",
        "faugus launcher",
        "bottles",
        "itch",
        "itch io",
        "battle net",
        "battle net launcher",
        "ea app",
        "ea desktop",
        "origin",
        "ubisoft connect",
        "uplay",
        "gog galaxy",
        "gog galaxy 2 0",
        "rockstar games launcher",
        "xbox",
        "xbox app",
        "amazon games",
        "minigalaxy",
        "gamehub",
        "cartridges",
        "gamerdeck",
        "prism launcher",
        "minecraft launcher",
        "playnite",
        # Tools
        "goverlay",
        "protonup qt",
        "protontricks",
        "steamtinkerlaunch",
        "parsec",
        "mangohud",
        "wine",
        "winecfg",
        # Emulators
        "retroarch",
        "pcsx2",
        "dolphin emulator",
        "rpcs3",
        "duckstation",
        "ppsspp",
        "cemu",
        "ryujinx",
        "yuzu",
        "citra",
        "melonds",
        "mgba",
        "xemu",
    }
)

# Things Steam installs next to the games
NOT_GAME_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^Proton (Experimental|Hotfix|\d[\w. \-]*|EasyAntiCheat Runtime|BattlEye Runtime)$",
        r"^Proton-GE[\w. \-]*$",
        r"^Steam Linux Runtime\b.*$",
        r"^Steamworks Common Redistributables$",
        r"^SteamVR$",
        r"^Steam Controller Configs$",
        r"^Wallpaper Engine$",
        r"^Source SDK Base 20\d\d\b.*$",
        r"^.+ Dedicated Server$",
        r"^(Gamerdeck|Cartridges)\b.*$",  # this app, including its test build
    )
)

# Desktop entry ids (the file name without .desktop) and Flatpak ids, lowercase
NOT_GAME_DESKTOP_IDS = frozenset(
    {
        "steam",
        "com.valvesoftware.steam",
        "heroic",
        "com.heroicgameslauncher.hgl",
        "net.lutris.lutris",
        "lutris",
        "io.github.faugus.faugus-launcher",
        "faugus-launcher",
        "com.usebottles.bottles",
        "io.itch.itch",
        "itch",
        "page.kramo.cartridges",
        "hu.kramo.cartridges",
        "io.github.jeffersonmk.gamerdeck",
        "io.github.sharkwouter.minigalaxy",
        "com.github.tkashkin.gamehub",
        "org.prismlauncher.prismlauncher",
        "io.github.benjamimgois.goverlay",
        "goverlay",
        "net.davidotek.pupgui2",
        "com.github.matoking.protontricks",
        "parsecd",
        "com.moonlight_stream.moonlight",
        "dev.lizardbyte.app.sunshine",
        "org.libretro.retroarch",
        "retroarch",
        "net.pcsx2.pcsx2",
        "pcsx2",
    }
)

# Commands (the first word of Exec) that start one of those programs
NOT_GAME_COMMANDS = frozenset(
    {
        "steam",
        "heroic",
        "lutris",
        "faugus-launcher",
        "bottles",
        "itch",
        "goverlay",
        "protontricks",
        "steamtinkerlaunch",
        "parsecd",
        "moonlight",
        "sunshine",
        "retroarch",
        "pcsx2",
        "pcsx2-qt",
        "cartridges",
        "gamerdeck",
    }
)


def normalize(name: str) -> str:
    """Lowercase letters and digits separated by single spaces: "Battle.net®" -> "battle net" """
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def is_not_a_game_name(name: str) -> bool:
    """Whether a name is a launcher, a tool, an emulator or a Steam runtime"""
    if normalize(name) in NOT_GAME_NAMES:
        return True
    return any(pattern.match(name.strip()) for pattern in NOT_GAME_PATTERNS)


# Programs that wrap another command: "mangohud pcsx2-qt -fullscreen game.iso"
WRAPPERS = frozenset({"env", "mangohud", "gamemoderun", "prime-run", "nice", "taskset"})


def command_words(executable: str) -> list[str]:
    """The words of a command line without field codes (%U, @@u) and wrappers"""
    try:
        words = shlex.split(executable)
    except ValueError:
        words = executable.split()
    words = [w for w in words if not w.startswith(("%", "@@"))]
    # Skip "env", "VAR=value" and wrappers to reach the program
    while words and (
        "=" in words[0] and not words[0].startswith("-") or words[0] in WRAPPERS
    ):
        words.pop(0)
    return words


def program_name(executable: str) -> str:
    """The program a command line runs: the command, or the app id for Flatpak"""
    words = command_words(executable)
    if not words:
        return ""
    if PurePath(words[0]).name == "flatpak" and words[1:2] == ["run"]:
        app_ids = [w for w in words[2:] if not w.startswith("-")]
        return app_ids[0] if app_ids else "flatpak"
    return PurePath(words[0]).name


def has_target(executable: str) -> bool:
    """Whether a command line starts a specific game, file or URL

    "steam %U" opens the Steam client, "pcsx2-qt -fullscreen game.iso" starts a
    game on an emulator. Flags and desktop entry field codes do not count.
    """
    words = command_words(executable)
    rest = words[1:]
    if words[:2] and PurePath(words[0]).name == "flatpak" and words[1] == "run":
        rest = [w for w in words[2:] if not w.startswith("-")][1:]  # drop the app id
    return any(not word.startswith("-") for word in rest)


def is_not_a_game_desktop_entry(
    entry_id: str, name: str, executable: str, categories: Iterable[str]
) -> bool:
    """Whether a desktop entry in the "Game" category is not actually a game

    Launchers are told by name; categories, ids and commands only count when
    the entry opens the program itself. A shortcut that starts one game on an
    emulator keeps its game.
    """
    if is_not_a_game_name(name):
        return True
    if has_target(executable):
        return False

    if not NOT_GAME_CATEGORIES.isdisjoint(categories):
        return True
    if entry_id.lower() in NOT_GAME_DESKTOP_IDS:
        return True
    program = program_name(executable)
    return program in NOT_GAME_COMMANDS or program.lower() in NOT_GAME_DESKTOP_IDS
