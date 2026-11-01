# hints.py
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

"""The button legend at the bottom of the window

It shows what each controller button does right now, with the symbols of the
controller in use: A B X Y for Xbox, cross, circle, square and triangle for
PlayStation. The text follows the context (library, menu, dialog...).
"""

from dataclasses import dataclass
from typing import Optional

from gi.repository import GObject, Gtk

try:
    import cairo  # Comes with PyGObject; without it the font symbols are used
except ImportError:  # pragma: no cover
    cairo = None

XBOX = "xbox"
PLAYSTATION = "playstation"

# What is written inside each button symbol
GLYPHS = {
    XBOX: {"a": "A", "b": "B", "x": "X", "y": "Y", "lb": "LB", "rb": "RB", "menu": "☰"},
    PLAYSTATION: {
        "a": "✕",
        "b": "○",
        "x": "□",
        "y": "△",
        "lb": "L1",
        "rb": "R1",
        "menu": "OPTIONS",
    },
}
FACE_BUTTONS = ("a", "b", "x", "y")

SONY_VENDOR = 0x054C
MICROSOFT_VENDOR = 0x045E
PLAYSTATION_WORDS = ("dualsense", "dualshock", "playstation", "sony", "ps5", "ps4", "ps3")


@dataclass(frozen=True)
class Hint:
    buttons: tuple[str, ...]
    label: str


def controller_family(name: str = "", guid: str = "") -> str:
    """XBOX or PLAYSTATION, from the vendor in the SDL GUID or the name

    Controllers of other brands are laid out like an Xbox controller, which is
    what most of them copy.
    """
    # SDL GUIDs: bus (2 bytes), crc (2), vendor (2), 0, product (2), 0, version...
    if len(guid) >= 12:
        try:
            vendor = int(guid[10:12] + guid[8:10], 16)
        except ValueError:
            vendor = 0
        if vendor == SONY_VENDOR:
            return PLAYSTATION
        if vendor == MICROSOFT_VENDOR:
            return XBOX
    lowered = name.lower()
    if any(word in lowered for word in PLAYSTATION_WORDS):
        return PLAYSTATION
    return XBOX


# Contexts, from the most specific to the library itself
MENU = "menu"
DIALOG = "dialog"
SEARCH = "search"
DETAILS = "details"
SIDEBAR = "sidebar"
LIBRARY = "library"
HIDDEN = "hidden"


def hints_for(context: str) -> list[Hint]:
    """The legend for a context; the texts are the actions of gamepad.py"""
    if context in (MENU, DIALOG):
        return [Hint(("a",), _("Select")), Hint(("b",), _("Close"))]
    if context == SEARCH:
        return [Hint(("b",), _("Close Search"))]
    if context == DETAILS:
        return [Hint(("a",), _("Select")), Hint(("b",), _("Back"))]
    if context == SIDEBAR:
        return [
            Hint(("a",), _("Select")),
            Hint(("lb", "rb"), _("Sources")),
            Hint(("menu",), _("Sidebar")),
        ]
    if context == HIDDEN:
        return [
            Hint(("a",), _("Play")),
            Hint(("x",), _("Menu")),
            Hint(("y",), _("Search")),
            Hint(("b",), _("Back")),
        ]
    return [
        Hint(("a",), _("Play")),
        Hint(("x",), _("Menu")),
        Hint(("y",), _("Search")),
        Hint(("lb", "rb"), _("Sources")),
        Hint(("menu",), _("Sidebar")),
    ]


# The square and the triangle of PlayStation are drawn, not typed: in fonts they
# are thin, blurry, and of other sizes than the cross and the circle. Sizes are
# in pixels, inside a 22x22 button; lines are as heavy as the cross.
SHAPES = ("□", "△")
SHAPE_SIZE = 22
SHAPE_LINE = 1.6
SQUARE_SIDE = 10  # Outside edge to outside edge, so the edges land on pixels
TRIANGLE_WIDTH = 11.4
TRIANGLE_HEIGHT = 10
# A triangle is heavy at the bottom, so it looks low when its box is centered:
# it goes up a little (the way Sony draws it)
TRIANGLE_LIFT = 0.6


def draw_shape(symbol: str, cr: "cairo.Context", size: int, color: tuple) -> None:
    """Draw the square or the triangle, centered in a size x size box"""
    center = size / 2
    cr.set_source_rgba(*color)
    cr.set_line_width(SHAPE_LINE)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    if symbol == "□":
        side = SQUARE_SIDE - SHAPE_LINE  # The line is drawn on both sides of the path
        cr.rectangle(center - side / 2, center - side / 2, side, side)
    else:
        # Same joins at the corners as the stroke, so the outside box is a
        # little bigger than the path: subtract it
        width = TRIANGLE_WIDTH - SHAPE_LINE * 1.15
        height = TRIANGLE_HEIGHT - SHAPE_LINE * 1.5
        top = center - height / 2 - TRIANGLE_LIFT
        cr.move_to(center, top)
        cr.line_to(center + width / 2, top + height)
        cr.line_to(center - width / 2, top + height)
        cr.close_path()
    cr.stroke()


class PadShape(Gtk.DrawingArea):
    """A drawn controller symbol, in the color the style sheet gives it"""

    __gtype_name__ = "PadShape"

    def __init__(self, symbol: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.symbol = symbol
        self.set_content_width(SHAPE_SIZE)
        self.set_content_height(SHAPE_SIZE)
        self.set_draw_func(self._draw)
        self.update_property([Gtk.AccessibleProperty.LABEL], [symbol])

    def get_label(self) -> str:
        """The symbol this draws, like a label has (for tests and screen readers)"""
        return self.symbol

    def _draw(self, _area: Gtk.DrawingArea, cr: "cairo.Context", width: int, _h: int) -> None:
        color = self.get_color()
        draw_shape(self.symbol, cr, width, (color.red, color.green, color.blue, color.alpha))


def make_glyph(button: str, style: str) -> Gtk.Widget:
    symbol = GLYPHS[style][button]
    if cairo is not None and style == PLAYSTATION and symbol in SHAPES:
        glyph = PadShape(symbol, valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
        glyph.add_css_class("pad-shape")
    else:
        glyph = Gtk.Label(label=symbol, valign=Gtk.Align.CENTER)
    glyph.add_css_class("pad-glyph")
    glyph.add_css_class(f"pad-{style}")
    glyph.add_css_class(f"pad-{button}" if button in FACE_BUTTONS else "pad-pill")
    if len(GLYPHS[style][button]) > 3:
        glyph.add_css_class("pad-text")  # A word like OPTIONS, not a symbol
    return glyph


class HintBar(Gtk.Box):
    """A row of "symbol + what it does" pairs"""

    __gtype_name__ = "HintBar"

    # Narrow windows: tighter spacing so the whole legend fits
    compact = GObject.Property(type=bool, default=False)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.set_spacing(18)
        self.add_css_class("hint-bar")
        self.set_halign(Gtk.Align.CENTER)
        self.style = XBOX
        self.hints: list[Hint] = []
        self.connect("notify::compact", lambda *_: self.set_css_classes(
            ["hint-bar", "compact"] if self.compact else ["hint-bar"]
        ))

    def set_hints(self, hints: list[Hint], style: Optional[str] = None) -> None:
        style = style or self.style
        if hints == self.hints and style == self.style and self.get_first_child():
            return
        self.hints, self.style = list(hints), style

        while child := self.get_first_child():
            self.remove(child)
        for hint in hints:
            item = Gtk.Box(spacing=7)
            item.add_css_class("hint-item")
            for button in hint.buttons:
                item.append(make_glyph(button, style))
            label = Gtk.Label(label=hint.label)
            label.add_css_class("hint-label")
            item.append(label)
            self.append(item)
