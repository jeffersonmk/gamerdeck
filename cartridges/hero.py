# hero.py
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

from typing import Any, Optional

from gi.repository import GObject, Gtk

from cartridges import shared
from cartridges.game import Game
from cartridges.game_cover import GameCover
from cartridges.platforms import platform_of
from cartridges.utils.protondb import open_page, show_rating
from cartridges.utils.relative_date import relative_date


@Gtk.Template(resource_path=shared.PREFIX + "/gtk/hero.ui")
class LibraryHero(Gtk.Box):
    """The banner on top of the library: the game that has the focus

    It shows the cover and its blurred copy in the colors of the theme, where
    the game came from, the ProtonDB rating, and the Play and Details buttons.
    Main thread only.
    """

    __gtype_name__ = "LibraryHero"

    hero_size = Gtk.Template.Child()
    background = Gtk.Template.Child()
    cover = Gtk.Template.Child()
    content = Gtk.Template.Child()
    info = Gtk.Template.Child()
    actions = Gtk.Template.Child()
    title = Gtk.Template.Child()
    subtitle = Gtk.Template.Child()
    platform_button = Gtk.Template.Child()
    protondb_button = Gtk.Template.Child()
    play_button = Gtk.Template.Child()
    details_button = Gtk.Template.Child()

    game: Optional[Game] = None
    game_cover: Optional[GameCover] = None

    # Narrow windows only keep the title and the buttons
    compact = GObject.Property(type=bool, default=False)

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.play_button.connect("clicked", self.on_play)
        self.details_button.connect("clicked", self.on_details)
        self.platform_button.connect("clicked", self.on_platform)
        self.protondb_button.connect("clicked", self.on_protondb)
        self.connect("notify::compact", self.on_compact_changed)

    def on_compact_changed(self, *_args: Any) -> None:
        self.cover.set_visible(not self.compact)
        self.content.set_orientation(
            Gtk.Orientation.VERTICAL if self.compact else Gtk.Orientation.HORIZONTAL
        )
        self.content.set_spacing(10 if self.compact else 20)
        self.actions.set_halign(Gtk.Align.START if self.compact else Gtk.Align.FILL)
        self.info.set_valign(Gtk.Align.END if self.compact else Gtk.Align.CENTER)
        self.actions.set_valign(Gtk.Align.START if self.compact else Gtk.Align.CENTER)
        self.hero_size.set_size_request(-1, 170 if self.compact else 190)

    def set_game(self, game: Optional[Game]) -> None:
        """Show a game (or nothing)"""
        if game is self.game:
            self.sync()
            return

        if self.game_cover:
            self.game_cover.remove_picture(self.cover)
        self.game = game
        self.game_cover = game.game_cover if game else None
        if self.game_cover:
            self.game_cover.add_picture(self.cover)
            self.background.set_paintable(self.game_cover.get_blurred())
        else:
            self.background.set_paintable(None)
        self.sync()

    def sync(self) -> None:
        """Show the current values of the game"""
        game = self.game
        self.play_button.set_sensitive(game is not None)
        self.details_button.set_sensitive(game is not None)
        if game is None:
            self.title.set_label("")
            self.subtitle.set_label("")
            self.platform_button.set_visible(False)
            show_rating(self.protondb_button, None)
            return

        self.title.set_label(game.name)
        parts = []
        if game.developer:
            parts.append(game.developer)
        parts.append(
            # The variable is the date a game was played
            _("Last played: {}").format(relative_date(game.last_played))
            if game.last_played
            else _("Never played")
        )
        self.subtitle.set_label(" · ".join(parts))

        platform = platform_of(game)
        client = platform.client if platform else None
        self.platform_button.set_visible(platform is not None)
        if platform:
            box = Gtk.Box(spacing=6)
            box.append(Gtk.Image.new_from_icon_name(platform.icon))
            box.append(Gtk.Label(label=platform.name))
            self.platform_button.set_child(box)
            self.platform_button.set_sensitive(client is not None)
            self.platform_button.set_tooltip_text(
                # The variable is the name of an app, like Steam
                _("Open {}").format(client.name)
                if client
                else None
            )

        enabled = shared.schema.get_boolean("protondb")
        show_rating(self.protondb_button, game.protondb if enabled else None)
        if enabled:
            game.request_protondb()

    def on_play(self, *_args: Any) -> None:
        if self.game:
            self.game.launch()

    def on_details(self, *_args: Any) -> None:
        if self.game:
            shared.win.show_details_page(self.game)

    def on_platform(self, *_args: Any) -> None:
        if self.game:
            shared.win.active_game = self.game
            shared.win.get_application().activate_action("open_game_client", None)

    def on_protondb(self, *_args: Any) -> None:
        if self.game and self.game.protondb:
            open_page(self.game.protondb)
