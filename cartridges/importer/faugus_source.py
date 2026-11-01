# faugus_source.py
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

import json
import logging
import shlex
from datetime import datetime
from typing import Any, NamedTuple

from cartridges import shared
from cartridges.game import Game
from cartridges.importer.location import Location, LocationSubPath
from cartridges.importer.source import Source, SourceIterable

FLATPAK_ID = "io.github.Faugus.faugus-launcher"


def parse_last_played(value: Any) -> int:
    """Faugus stores the last time a game was played as an ISO date string"""
    if not isinstance(value, str) or not value:
        return 0
    try:
        return int(datetime.fromisoformat(value).timestamp())
    except (ValueError, OverflowError, OSError):
        return 0


class FaugusSourceIterable(SourceIterable):
    source: "FaugusSource"

    def __iter__(self):
        """Generator method producing games"""

        games_file = self.source.locations.data["games.json"]
        try:
            entries = json.loads(games_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            logging.warning("Couldn't read Faugus games from %s: %s", games_file, error)
            return
        if not isinstance(entries, list):
            logging.warning("Unexpected content in %s", games_file)
            return

        root = self.source.locations.data.root

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            game_id, title = entry.get("gameid"), entry.get("title")
            if not (isinstance(game_id, str) and game_id) or not (
                isinstance(title, str) and title
            ):
                logging.debug("Skipped an invalid Faugus entry: %r", entry)
                continue

            values = {
                "added": shared.import_time,
                "name": title,
                "source": self.source.source_id,
                "game_id": self.source.game_id_format.format(game_id=game_id),
                "executable": self.source.make_executable(game_id=game_id),
                "hidden": bool(entry.get("hidden")),
            }
            if last_played := parse_last_played(entry.get("last_played")):
                values["last_played"] = last_played
            game = Game(values)

            # Faugus covers are named after the game id; use the icon if the
            # game has no cover (only one of them, the later one would win)
            additional_data = {}
            for folder, key in (
                ("covers", "local_image_path"),
                ("icons", "local_icon_path"),
            ):
                if (image := root / folder / f"{game_id}.png").is_file():
                    additional_data[key] = image
                    break

            yield (game, additional_data)


class FaugusLocations(NamedTuple):
    data: Location


class FaugusSource(Source):
    """Games added to Faugus Launcher"""

    source_id = "faugus"
    name = _("Faugus")
    iterable_class = FaugusSourceIterable
    available_on = {"linux"}

    locations: FaugusLocations

    def __init__(self) -> None:
        super().__init__()
        self.locations = FaugusLocations(
            Location(
                schema_key="faugus-location",
                candidates=(
                    shared.flatpak_dir / FLATPAK_ID / "data" / "faugus-launcher",
                    shared.data_dir / "faugus-launcher",
                    shared.host_data_dir / "faugus-launcher",
                    # Faugus before it moved its files to the data directory
                    shared.flatpak_dir / FLATPAK_ID / "config" / "faugus-launcher",
                    shared.config_dir / "faugus-launcher",
                    shared.host_config_dir / "faugus-launcher",
                ),
                paths={
                    "games.json": LocationSubPath("games.json"),
                },
                invalid_subtitle=Location.DATA_INVALID_SUBTITLE,
            )
        )

    @property
    def is_flatpak(self) -> bool:
        """Whether the games are managed by the Flatpak version of Faugus"""
        root = self.locations.data.root
        return root is not None and (shared.flatpak_dir / FLATPAK_ID) in (
            root,
            *root.parents,
        )

    def make_executable(self, *args: Any, **kwargs: Any) -> str:
        game_id = shlex.quote(kwargs["game_id"])
        if self.is_flatpak:
            return (
                f"flatpak run --command=/app/bin/faugus-launcher {FLATPAK_ID} "
                f"--game {game_id}"
            )
        return f"faugus-launcher --game {game_id}"
