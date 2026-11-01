# platforms.py
#
# Copyright 2026 GameDeck contributors
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

"""Where a game was installed from, and how to open that app

Every game has a `source` ("steam", "heroic_gog", "lutris_wine"...). The
platform is what the player knows it by (Steam, Epic, GOG...) and the client
is the program that installed it (Heroic installs Epic, GOG and Amazon games).
"""

import logging
import os
import shutil
from dataclasses import dataclass
from shlex import quote
from typing import Optional

from cartridges import shared
from cartridges.game import Game
from cartridges.utils.run_executable import run_executable


@dataclass(frozen=True)
class Client:
    """A program that installs and manages games"""

    name: str
    command: str
    flatpak_id: Optional[str] = None


@dataclass(frozen=True)
class Platform:
    id: str
    name: str
    icon: str  # Symbolic icon name (data/icons/sources)
    client: Optional[Client] = None  # None when there is no app to open


STEAM = Client("Steam", "steam", "com.valvesoftware.Steam")
LUTRIS = Client("Lutris", "lutris", "net.lutris.Lutris")
HEROIC = Client("Heroic", "heroic", "com.heroicgameslauncher.hgl")
FAUGUS = Client("Faugus", "faugus-launcher", "io.github.Faugus.faugus-launcher")
BOTTLES = Client("Bottles", "bottles", "com.usebottles.bottles")
ITCH = Client("itch", "itch", "io.itch.itch")
RETROARCH = Client("RetroArch", "retroarch", "org.libretro.RetroArch")

PLATFORMS = {
    "steam": Platform("steam", _("Steam"), "steam-source-symbolic", STEAM),
    "lutris": Platform("lutris", _("Lutris"), "lutris-source-symbolic", LUTRIS),
    "faugus": Platform("faugus", _("Faugus"), "faugus-source-symbolic", FAUGUS),
    "epic": Platform("epic", _("Epic Games"), "epic-source-symbolic", HEROIC),
    "gog": Platform("gog", _("GOG"), "gog-source-symbolic", HEROIC),
    "amazon": Platform("amazon", _("Amazon Games"), "amazon-source-symbolic", HEROIC),
    "heroic": Platform("heroic", _("Heroic"), "heroic-source-symbolic", HEROIC),
    "bottles": Platform("bottles", _("Bottles"), "bottles-source-symbolic", BOTTLES),
    "itch": Platform("itch", _("itch"), "itch-source-symbolic", ITCH),
    "retroarch": Platform(
        "retroarch", _("RetroArch"), "retroarch-source-symbolic", RETROARCH
    ),
    # Legendary is a command line tool: there is no window to open
    "legendary": Platform("legendary", _("Epic Games"), "epic-source-symbolic"),
}

# What Heroic calls its stores, in the `source` of a game ("heroic_legendary")
HEROIC_STORES = {"legendary": "epic", "gog": "gog", "nile": "amazon"}


def platform_of(game: Game) -> Optional[Platform]:
    """The platform a game came from, or None (added by hand, desktop entries,
    Flatpak apps...)"""
    base, _separator, store = game.source.partition("_")
    if base == "heroic":
        return PLATFORMS[HEROIC_STORES.get(store, "heroic")]
    return PLATFORMS.get(base)


def client_of(game: Game) -> Optional[Client]:
    """The app to open for a game, if there is one"""
    platform = platform_of(game)
    return platform.client if platform else None


def _sandboxed() -> bool:
    return os.getenv("FLATPAK_ID") == shared.APP_ID


def client_command(game: Game) -> Optional[str]:
    """The command that opens the client of a game (the game page for Steam)"""
    if (client := client_of(game)) is None:
        return None

    if client is STEAM:
        appid = game.game_id.removeprefix("steam_")
        if appid.isdigit():
            # Opens the client on the page of the game
            return f"xdg-open steam://nav/games/details/{quote(appid)}"

    flatpak_installed = bool(
        client.flatpak_id and (shared.flatpak_dir / client.flatpak_id).is_dir()
    )
    # Inside the sandbox the host commands cannot be looked up
    native_installed = not _sandboxed() and shutil.which(client.command) is not None
    if flatpak_installed and not native_installed:
        return f"flatpak run {client.flatpak_id}"
    return client.command


def open_client(game: Game) -> bool:
    """Open the client a game was installed from. False if there is none."""
    if (command := client_command(game)) is None:
        return False
    run_executable(command)
    logging.info("Opened the client of %s: %s", game.name, command)
    return True
