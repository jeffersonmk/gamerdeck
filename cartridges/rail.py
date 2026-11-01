# rail.py
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

import heapq
from typing import Any, Iterable, Optional

from gi.repository import Gio, Gtk, Pango

from cartridges import shared
from cartridges.game import Game
from cartridges.game_cover import GameCover

RAIL_SIZE = 10
RAIL_HEIGHT = 172  # The cover, the title and the padding of an item


def recent_games(games: Iterable[Game], size: int = RAIL_SIZE) -> list[Game]:
    """The games played last, newest first (games never played are left out)"""
    return heapq.nlargest(
        size, (game for game in games if game.last_played), key=lambda g: g.last_played
    )


class RailItem(Gtk.Button):
    """A small cover that launches its game: one of the "continue playing" row"""

    __gtype_name__ = "RailItem"

    game: Optional[Game] = None
    game_cover: Optional[GameCover] = None

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.add_css_class("rail-item")
        self.cover = Gtk.Picture(
            width_request=84,
            height_request=126,
            content_fit=Gtk.ContentFit.COVER,
            can_shrink=True,
        )
        self.cover.add_css_class("rail-cover")
        self.title = Gtk.Label(
            ellipsize=Pango.EllipsizeMode.END, max_width_chars=12, xalign=0.5
        )
        self.title.add_css_class("caption")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.append(self.cover)
        box.append(self.title)
        self.set_child(box)
        self.connect("clicked", self.on_clicked)

        focus = Gtk.EventControllerFocus()
        focus.connect("enter", self.show_in_banner)
        self.add_controller(focus)
        motion = Gtk.EventControllerMotion()
        motion.connect("enter", self.show_in_banner)
        self.add_controller(motion)

    def show_in_banner(self, *_args: Any) -> None:
        if self.game and shared.win is not None:
            shared.win.set_hero_game(self.game)

    def bind(self, game: Game) -> None:
        self.unbind()
        self.game = game
        self.title.set_label(game.name)
        self.set_tooltip_text(game.name)
        self.game_cover = game.game_cover
        if self.game_cover:
            self.game_cover.add_picture(self.cover)

    def unbind(self) -> None:
        if self.game_cover:
            self.game_cover.remove_picture(self.cover)
        self.game_cover = None
        self.game = None

    def on_clicked(self, *_args: Any) -> None:
        if self.game:
            self.game.launch()


class LibraryRail(Gtk.ScrolledWindow):
    """A row of the games played last"""

    __gtype_name__ = "LibraryRail"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(
            hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vscrollbar_policy=Gtk.PolicyType.NEVER,
            **kwargs,
        )
        # min-content-height is ignored without vertical scrolling, and
        # constructor properties are not applied to widgets made by Blueprint
        self.set_size_request(-1, RAIL_HEIGHT)
        self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        self.store = Gio.ListStore(item_type=Game)
        factory = Gtk.SignalListItemFactory()

        def setup(_factory: Any, list_item: Gtk.ListItem) -> None:
            list_item.set_child(RailItem())

        def bind(_factory: Any, list_item: Gtk.ListItem) -> None:
            list_item.get_child().bind(list_item.get_item())

        def unbind(_factory: Any, list_item: Gtk.ListItem) -> None:
            list_item.get_child().unbind()

        factory.connect("setup", setup)
        factory.connect("bind", bind)
        factory.connect("unbind", unbind)

        self.view = Gtk.ListView(
            model=Gtk.NoSelection(model=self.store),
            factory=factory,
            orientation=Gtk.Orientation.HORIZONTAL,
            single_click_activate=False,
        )
        self.view.add_css_class("rail")
        self.set_child(self.view)

    def set_games(self, games: list[Game]) -> None:
        """Replace the games of the row (only when they really changed)"""
        current = [self.store.get_item(i) for i in range(self.store.get_n_items())]
        if current != games:
            self.store.splice(0, len(current), games)
