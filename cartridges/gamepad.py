# gamepad.py
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

"""Navigate the app with an Xbox or PlayStation controller

libmanette translates every controller to one standard layout (the SDL game
controller database), so the buttons are named by position, not by label:

    south = A / Cross        east = B / Circle
    west  = X / Square       north = Y / Triangle

`GamepadInput` turns raw events into `Action`s (no GTK, easy to test) and
`GamepadController` applies the actions to the active window.
"""

import logging
from enum import Enum, auto
from typing import Any, Callable, Optional

import gi
from gi.repository import Adw, GLib, Gtk

from cartridges.game_widget import GameWidget

try:
    gi.require_version("Manette", "0.2")
    from gi.repository import Manette
except (ValueError, ImportError):  # libmanette is optional
    Manette = None


class Action(Enum):
    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()
    ACCEPT = auto()  # A / Cross: launch the game, press the button
    BACK = auto()  # B / Circle: close the menu, dialog or page
    SEARCH = auto()  # Y / Triangle
    GAME_MENU = auto()  # X / Square
    PREVIOUS_SOURCE = auto()  # LB / L1
    NEXT_SOURCE = auto()  # RB / R1
    SIDEBAR = auto()  # Menu / Options


DIRECTIONS = {
    Action.UP: Gtk.DirectionType.UP,
    Action.DOWN: Gtk.DirectionType.DOWN,
    Action.LEFT: Gtk.DirectionType.LEFT,
    Action.RIGHT: Gtk.DirectionType.RIGHT,
}

# Linux evdev codes, as reported by libmanette for the standard layout
BTN_SOUTH = 0x130
BTN_EAST = 0x131
BTN_NORTH = 0x133
BTN_WEST = 0x134
BTN_TL = 0x136
BTN_TR = 0x137
BTN_START = 0x13B
BTN_DPAD_UP = 0x220
BTN_DPAD_DOWN = 0x221
BTN_DPAD_LEFT = 0x222
BTN_DPAD_RIGHT = 0x223
ABS_X = 0x00
ABS_Y = 0x01
ABS_HAT0X = 0x10
ABS_HAT0Y = 0x11

BUTTON_ACTIONS = {
    BTN_SOUTH: Action.ACCEPT,
    BTN_EAST: Action.BACK,
    BTN_WEST: Action.GAME_MENU,
    BTN_NORTH: Action.SEARCH,
    BTN_TL: Action.PREVIOUS_SOURCE,
    BTN_TR: Action.NEXT_SOURCE,
    BTN_START: Action.SIDEBAR,
    BTN_DPAD_UP: Action.UP,
    BTN_DPAD_DOWN: Action.DOWN,
    BTN_DPAD_LEFT: Action.LEFT,
    BTN_DPAD_RIGHT: Action.RIGHT,
}

STICK_PRESS = 0.6  # How far the stick must go to count as a press...
STICK_RELEASE = 0.4  # ...and how close to the center to count as released
REPEAT_DELAY_MS = 400  # Holding a direction repeats it after this long...
REPEAT_INTERVAL_MS = 110  # ...and then this often


class GamepadInput:
    """Turns buttons, hats and sticks into actions, repeating held directions"""

    def __init__(
        self,
        callback: Callable[[Action], None],
        repeat_delay_ms: int = REPEAT_DELAY_MS,
        repeat_interval_ms: int = REPEAT_INTERVAL_MS,
    ) -> None:
        self.callback = callback
        self.repeat_delay_ms = repeat_delay_ms
        self.repeat_interval_ms = repeat_interval_ms

        self._held: dict[Any, Action] = {}  # Held direction of each source
        self._repeating: Optional[Action] = None
        self._timeout_id = 0
        self._stick = [0.0, 0.0]

    def button(self, code: int, pressed: bool) -> None:
        if (action := BUTTON_ACTIONS.get(code)) is None:
            return
        if action in DIRECTIONS:
            if pressed:
                self._press_direction(("button", code), action)
            else:
                self._release_direction(("button", code))
        elif pressed:
            self.callback(action)

    def hat(self, axis: int, value: int) -> None:
        """A d-pad reported as a hat: value is -1, 0 or 1"""
        if axis == ABS_HAT0X:
            action = Action.LEFT if value < 0 else Action.RIGHT
        elif axis == ABS_HAT0Y:
            action = Action.UP if value < 0 else Action.DOWN
        else:
            return
        if value:
            self._press_direction(("hat", axis), action)
        else:
            self._release_direction(("hat", axis))

    def axis(self, axis: int, value: float) -> None:
        """The left stick: value is between -1 and 1 (down and right are positive)"""
        if axis not in (ABS_X, ABS_Y):
            return
        self._stick[axis] = value
        x, y = self._stick

        # Past the press point, or still past the release point once pressed
        limit = STICK_RELEASE if ("stick",) in self._held else STICK_PRESS
        if max(abs(x), abs(y)) < limit:
            self._release_direction(("stick",))
        elif abs(x) > abs(y):
            self._press_direction(("stick",), Action.RIGHT if x > 0 else Action.LEFT)
        else:
            self._press_direction(("stick",), Action.DOWN if y > 0 else Action.UP)

    def release_all(self) -> None:
        """Forget everything that is held (the controller went away)"""
        self._held.clear()
        self._stick = [0.0, 0.0]
        self._stop_repeat()

    def _press_direction(self, source: Any, action: Action) -> None:
        if self._held.get(source) is action:
            return  # Already held (a stick moving around inside its direction)
        self._held[source] = action
        self.callback(action)
        self._start_repeat(action)

    def _release_direction(self, source: Any) -> None:
        if self._held.pop(source, None) is None:
            return
        if not self._held:
            self._stop_repeat()
        elif self._repeating not in self._held.values():
            # Another source is still held: repeat that one instead
            self._start_repeat(next(reversed(self._held.values())))

    def _start_repeat(self, action: Action) -> None:
        self._stop_repeat()
        self._repeating = action
        self._timeout_id = GLib.timeout_add(self.repeat_delay_ms, self._first_repeat)

    def _first_repeat(self) -> bool:
        self._timeout_id = GLib.timeout_add(self.repeat_interval_ms, self._repeat)
        self._repeat()
        return GLib.SOURCE_REMOVE

    def _repeat(self) -> bool:
        if self._repeating is None:
            return GLib.SOURCE_REMOVE
        self.callback(self._repeating)
        return GLib.SOURCE_CONTINUE

    def _stop_repeat(self) -> None:
        if self._timeout_id:
            GLib.source_remove(self._timeout_id)
        self._timeout_id = 0
        self._repeating = None


class GamepadController:
    """Listens to the connected controllers and drives the active window

    Controllers are read straight from the kernel, so they keep sending
    events while a game is running in front of the app. Input is only used
    while the app window has the focus.
    """

    def __init__(self, app: Adw.Application) -> None:
        self.app = app
        self.input = GamepadInput(self.dispatch)
        self.monitor = None
        self.devices: set = set()

    def start(self) -> bool:
        if Manette is None:
            logging.info("libmanette not found, gamepad navigation is disabled")
            return False

        self.monitor = Manette.Monitor()
        self.monitor.connect("device-connected", self._device_connected)
        self.monitor.connect("device-disconnected", self._device_disconnected)
        iterator = self.monitor.iterate()
        while True:
            found, device = iterator.next()
            if not found:
                break
            self._device_connected(self.monitor, device)
        return True

    def _device_connected(self, _monitor: Any, device: Any) -> None:
        if device in self.devices:
            return
        self.devices.add(device)
        logging.info("Gamepad connected: %s", device.get_name())
        device.connect("button-press-event", self._on_button, True)
        device.connect("button-release-event", self._on_button, False)
        device.connect("hat-axis-event", self._on_hat)
        device.connect("absolute-axis-event", self._on_axis)

    def _device_disconnected(self, _monitor: Any, device: Any) -> None:
        self.devices.discard(device)
        self.input.release_all()
        logging.info("Gamepad disconnected: %s", device.get_name())

    def _on_button(self, _device: Any, event: Any, pressed: bool) -> None:
        found, code = event.get_button()
        if found:
            self.input.button(code, pressed)

    def _on_hat(self, _device: Any, event: Any) -> None:
        found, axis, value = event.get_hat()
        if found:
            self.input.hat(axis, value)

    def _on_axis(self, _device: Any, event: Any) -> None:
        found, axis, value = event.get_absolute()
        if found:
            self.input.axis(axis, value)

    # Applying actions to the window

    def get_window(self) -> Optional[Any]:
        """The app window, if it is the one the user is looking at"""
        win = self.app.get_active_window()
        return win if win is not None and win.is_active() else None

    def dispatch(self, action: Action) -> None:
        if (win := self.get_window()) is None:
            self.input.release_all()
            return

        win.set_focus_visible(True)
        match action:
            case Action.UP | Action.DOWN | Action.LEFT | Action.RIGHT:
                self.move(win, action)
            case Action.ACCEPT:
                self.accept(win)
            case Action.BACK:
                self.back(win)
            case Action.SEARCH:
                win.activate_action("win.toggle_search", None)
            case Action.GAME_MENU:
                self.open_game_menu(win)
            case Action.PREVIOUS_SOURCE:
                win.select_adjacent_source(-1)
            case Action.NEXT_SOURCE:
                win.select_adjacent_source(1)
            case Action.SIDEBAR:
                self.toggle_sidebar(win)

    @staticmethod
    def get_open_popover(focus: Optional[Gtk.Widget]) -> Optional[Gtk.Popover]:
        """The menu that is open around the focus, if any"""
        if focus is None:
            return None
        if popover := focus.get_ancestor(Gtk.Popover):
            return popover
        # The menu button keeps the focus until a key moves it into the menu
        button = focus.get_ancestor(Gtk.MenuButton)
        if button is not None and button.get_active():
            return button.get_popover()
        return None

    def get_focus_root(self, win: Adw.ApplicationWindow) -> Gtk.Widget:
        """The widget the focus has to stay inside: a menu, a dialog or the window"""
        if popover := self.get_open_popover(win.get_focus()):
            return popover
        if dialog := win.get_visible_dialog():
            return dialog
        return win

    def move(self, win: Adw.ApplicationWindow, action: Action) -> None:
        focus = win.get_focus()
        if focus is None or focus is win:
            if not win.focus_library():
                win.child_focus(Gtk.DirectionType.TAB_FORWARD)
            return

        in_menu_or_dialog = (
            win.get_visible_dialog() is not None or self.get_open_popover(focus) is not None
        )
        if not in_menu_or_dialog:
            rtl = win.get_direction() == Gtk.TextDirection.RTL
            to_sidebar = Action.RIGHT if rtl else Action.LEFT
            to_grid = Action.LEFT if rtl else Action.RIGHT

            if win.is_in_sidebar():
                # The sidebar is a column of rows: sideways goes back to the grid
                if action is to_grid:
                    win.focus_library()
                    if win.overlay_split_view.get_collapsed():
                        win.overlay_split_view.set_show_sidebar(False)
                    return
                if action is to_sidebar:
                    return
            elif action is to_sidebar and win.is_at_first_column():
                win.focus_sidebar()
                return

            step, rows = {
                Action.LEFT: (-1, 0),
                Action.RIGHT: (1, 0),
                Action.UP: (0, -1),
                Action.DOWN: (0, 1),
            }[action]
            if win.move_library_focus(step, rows):
                return
            if win.get_focused_card() is not None and step:
                return  # Nothing beside the first or last card

        self.get_focus_root(win).child_focus(DIRECTIONS[action])

    def accept(self, win: Adw.ApplicationWindow) -> None:
        if (focus := win.get_focus()) is None:
            return

        card = focus.get_ancestor(GameWidget)
        if card is not None and card.game and focus is card.cover_button:
            card.game.launch()  # A on a card starts the game
            return
        focus.activate()

    def back(self, win: Adw.ApplicationWindow) -> None:
        if popover := self.get_open_popover(win.get_focus()):
            popover.popdown()
            return

        if dialog := win.get_visible_dialog():
            dialog.close()
            return

        page = win.navigation_view.get_visible_page()
        if page == win.library_page and win.search_bar.get_search_mode():
            win.activate_action("win.toggle_search", None)
        elif page == win.hidden_library_page and win.hidden_search_bar.get_search_mode():
            win.activate_action("win.toggle_search", None)
        elif page != win.library_page:
            win.navigation_view.pop()
        elif win.overlay_split_view.get_collapsed():
            win.overlay_split_view.set_show_sidebar(False)

    def open_game_menu(self, win: Adw.ApplicationWindow) -> None:
        if card := win.get_focused_card():
            card.menu_button.popup()

    def toggle_sidebar(self, win: Adw.ApplicationWindow) -> None:
        in_sidebar = win.is_in_sidebar()
        win.activate_action("win.show_sidebar", None)

        if win.overlay_split_view.get_show_sidebar():
            win.focus_sidebar()
        elif in_sidebar:
            win.focus_library()
