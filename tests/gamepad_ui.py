"""Drives the real window with simulated controller input, under Broadway.

Not run directly: tests/test_gamepad_ui.py starts a Broadway display and runs
this module inside it (`python3 -m tests.gamepad_ui`). It creates a small
library in a throwaway environment, presses the controller buttons through
`GamepadInput` (the same entry point libmanette events use) and prints one
`RESULT {...}` line with a boolean per check.

With GAMEPAD_UI_SHOTS=<dir> it also renders PNGs of the window from its own
widgets (nothing is grabbed from the real screen).
"""

# pylint: disable=missing-function-docstring,import-outside-toplevel
import json
import os
import sys
import traceback
from pathlib import Path

from tests.support import SANDBOX, iterate_main_loop  # noqa: F401  (sets the environment)

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk  # noqa: E402

from cartridges import main as app_main  # noqa: E402
from cartridges import shared  # noqa: E402
from cartridges.game import Game  # noqa: E402
from cartridges.gamepad import (  # noqa: E402
    ABS_HAT0Y,
    ABS_X,
    BTN_DPAD_DOWN,
    BTN_DPAD_LEFT,
    BTN_DPAD_RIGHT,
    BTN_DPAD_UP,
    BTN_EAST,
    BTN_NORTH,
    BTN_SOUTH,
    BTN_START,
    BTN_TL,
    BTN_TR,
    BTN_WEST,
)

N_GAMES = 24
results: dict[str, bool] = {}
launched: list[str] = []


def make_library() -> None:
    games = SANDBOX / "data" / "cartridges" / "games"
    games.mkdir(parents=True)
    (SANDBOX / "data" / "cartridges" / "covers").mkdir()
    for i in range(N_GAMES):
        source = "steam" if i % 2 else "imported"
        game_id = f"{source}_{i}"
        (games / f"{game_id}.json").write_text(
            json.dumps(
                {
                    "added": 1_700_000_000 + i,
                    "executable": "true",
                    "game_id": game_id,
                    "source": source,
                    "hidden": False,
                    "last_played": 1_700_000_000 + i,
                    "name": f"Game {i:02d}",
                    "developer": "Test",
                    "removed": False,
                    "blacklisted": False,
                    "version": 1.5,
                }
            )
        )


def render(widget: Gtk.Widget, path: Path) -> bool:
    gi.require_version("Graphene", "1.0")
    from gi.repository import Graphene

    width, height = widget.get_width(), widget.get_height()
    for _ in range(50):
        snapshot = Gtk.Snapshot()
        Gtk.WidgetPaintable.new(widget).snapshot(snapshot, width, height)
        node = snapshot.to_node()
        if node:
            texture = widget.get_native().get_renderer().render_texture(
                node, Graphene.Rect().init(0, 0, width, height)
            )
            texture.save_to_png(str(path))
            return True
        iterate_main_loop(timeout=0.05)
    return False


def glyph_offsets(win, path: Path) -> list:
    """(symbol, width, height, x offset, y offset) of every symbol of the legend

    The offset is the distance, in pixels, between the center of the ink and the
    center of its button, measured on the rendered window.
    """
    from PIL import Image  # system python only: skipped by the caller if missing

    if not render(win, path):
        return []
    image = Image.open(path).convert("RGB")
    found, item = [], win.hint_bar.get_first_child()
    while item:
        child = item.get_first_child()
        while child:
            if child.has_css_class("pad-glyph"):
                _ok, bounds = child.compute_bounds(win)
                box = (round(bounds.get_x()), round(bounds.get_y()),
                       round(bounds.get_x() + bounds.get_width()),
                       round(bounds.get_y() + bounds.get_height()))
                region = image.crop(box)
                pixels = region.load()
                width, height = region.size
                colors: dict = {}
                for y in range(height):
                    for x in range(width):
                        colors[pixels[x, y]] = colors.get(pixels[x, y], 0) + 1
                background = max(colors, key=colors.get)
                ink = [
                    (x, y)
                    for y in range(height)
                    for x in range(width)
                    if min(x, width - 1 - x) > 2 and min(y, height - 1 - y) > 2  # rounded corners
                    and sum(abs(a - b) for a, b in zip(pixels[x, y], background)) > 90
                ]
                if ink:
                    xs, ys = [p[0] for p in ink], [p[1] for p in ink]
                    found.append((
                        child.get_label(), width, height,
                        (min(xs) + max(xs) + 1) / 2 - width / 2,
                        (min(ys) + max(ys) + 1) / 2 - height / 2,
                    ))
                else:
                    found.append((child.get_label(), width, height, 99.0, 99.0))
            child = child.get_next_sibling()
        item = item.get_next_sibling()
    return found


def steps(app):
    win = shared.win
    ctl = app.gamepad
    # Broadway never reports the window as active
    ctl.get_window = lambda: win
    shots = Path(os.environ["GAMEPAD_UI_SHOTS"]) if os.environ.get("GAMEPAD_UI_SHOTS") else None
    if shots:
        shots.mkdir(parents=True, exist_ok=True)

    def shot(name: str) -> None:
        if shots:
            render(win, shots / f"{name}.png")

    def shot_menu(card) -> None:
        """The window cannot be rendered while a popover is open: render both
        and paste the menu below its button"""
        if not shots:
            return
        from PIL import Image

        gi.require_version("Graphene", "1.0")
        from gi.repository import Graphene

        popover = card.menu_button.get_popover()
        window_png, popover_png = shots / "_window.png", shots / "_popover.png"
        popover.popdown()
        for _ in range(20):
            iterate_main_loop(timeout=0.05)
        render(win, window_png)
        popover.popup()
        for _ in range(20):
            iterate_main_loop(timeout=0.05)
        if not render(popover, popover_png):
            return
        button = card.menu_button
        ok, point = button.compute_point(win, Graphene.Point().init(0, 0))
        base = Image.open(window_png).convert("RGBA")
        menu = Image.open(popover_png).convert("RGBA")
        x = round(point.x + button.get_width() / 2 - menu.width / 2)
        y = round(point.y + button.get_height())
        base.alpha_composite(menu, (max(x, 0), y))
        base.save(shots / "4-menu.png")
        window_png.unlink()
        popover_png.unlink()

    def press(code: int) -> None:
        ctl.input.button(code, True)
        ctl.input.button(code, False)

    def card_name():
        card = win.get_focused_card()
        return card.game.name if card else None

    def check(name: str, value: bool) -> None:
        results[name] = bool(value)
        if not value:
            sys.stderr.write(f"FAILED {name}\n")

    def settle(condition, timeout_ms: int = 3000):
        """Let the main loop run until the condition holds (or time runs out)"""
        waited = 0
        while not condition() and waited < timeout_ms:
            yield 50
            waited += 50

    def cols() -> int:
        return win.library.get_max_columns()

    def in_sidebar() -> bool:
        focus = win.get_focus()
        return bool(focus and focus.get_ancestor(Gtk.ListBox) is win.sidebar)

    def in_popover() -> bool:
        focus = win.get_focus()
        return bool(focus and focus.get_ancestor(Gtk.Popover))

    win.overlay_split_view.set_show_sidebar(True)
    yield 400  # layout
    check("grid has several columns", cols() > 1)
    check("sidebar is shown", win.overlay_split_view.get_show_sidebar())
    shot("1-start")

    # The banner, the row of recent games and the legend
    def legend() -> list:
        return [h.label for h in win.hint_bar.hints]

    def glyphs() -> list:
        out, item = [], win.hint_bar.get_first_child()
        while item:
            out.append(item.get_first_child().get_label())
            item = item.get_next_sibling()
        return out

    yield 300
    check("banner is shown on top of the library", win.library_header_revealer.get_reveal_child())
    newest = f"Game {N_GAMES - 1:02d}"
    check("banner starts with the game played last", win.hero.game and win.hero.game.name == newest)
    check("the row lists the latest games, newest first",
          [win.rail.store.get_item(i).name for i in range(3)]
          == [f"Game {N_GAMES - 1 - i:02d}" for i in range(3)])
    # "auto": the legend shows only while a controller is connected AND in use.
    # Real controllers of the machine that runs the test count, so use a fake one
    # and judge by what the user did last.
    class FakePad:
        def get_name(self):
            return "Fake Xbox Controller"

        def get_guid(self):
            return ""

    pad = FakePad()
    keys, clicks, scroll, motion = win.input_controllers
    shown = win.hint_revealer.get_reveal_child

    def use_controller():
        ctl.set_in_use(True)
        ctl.last_input = 0

    ctl.devices.discard(pad)
    ctl.set_in_use(False)
    yield 100
    check("no controller connected: the legend is hidden", not shown())
    ctl.devices.add(pad)
    ctl._hints_changed()
    yield 100
    check("a controller is connected but not in use: the legend is hidden", not shown())
    use_controller()
    yield 100
    check("the controller is in use: the legend shows", shown())
    keys.emit("key-pressed", Gdk.KEY_a, 0, Gdk.ModifierType(0))
    check("a key of the keyboard hides it", not shown())
    use_controller()
    check("the controller brings it back", shown())
    clicks.emit("pressed", 1, 5.0, 5.0)
    check("a click hides it", not shown())
    use_controller()
    scroll.emit("scroll", 0.0, 1.0)
    check("the mouse wheel hides it", not shown())
    use_controller()
    motion.emit("motion", 100.0, 100.0)
    motion.emit("motion", 100.0, 100.0)
    motion.emit("motion", 103.0, 101.0)
    check("a pointer that stays (or twitches a few pixels) does not hide it", shown())
    ctl.last_input = GLib.get_monotonic_time()
    motion.emit("motion", 400.0, 100.0)
    check("pointer movement right after the controller moved something does not hide it", shown())
    ctl.last_input = 0
    motion.emit("motion", 400.0, 100.0)
    check("the pointer really moving hides it", not shown())
    ctl.devices.discard(pad)
    use_controller()
    ctl.set_in_use(False)
    shared.schema.set_string("hints-mode", "always")
    shared.schema.set_string("hints-style", "xbox")
    yield 300
    check("the legend shows with 'always'", win.hint_revealer.get_reveal_child())
    # The strip that has the background and the line on top must be as wide as
    # the window (the legend is centered in it), not a box around the symbols
    strip = win.hint_bar.get_parent()
    while strip is not None and not strip.has_css_class("hint-strip"):
        strip = strip.get_parent()
    check("the legend has a strip as wide as the window",
          strip is not None and strip.get_width() == win.get_width()
          and win.hint_bar.get_width() < strip.get_width())
    strip = strip or win.hint_bar.get_parent()
    first, last = win.hint_bar.get_first_child(), win.hint_bar.get_last_child()
    gap_left = first.compute_bounds(strip)[1].get_x()
    gap_right = strip.get_width() - (last.compute_bounds(strip)[1].get_x() + last.get_width())
    check(f"the legend is centered in the strip (gaps {gap_left:.0f} and {gap_right:.0f} px)",
          abs(gap_left - gap_right) <= 2)
    check("the library legend", legend() == ["Play", "Menu", "Search", "Sources", "Sidebar"])
    check("Xbox symbols", glyphs()[:3] == ["A", "X", "Y"])
    shared.schema.set_string("hints-style", "playstation")
    yield 300
    check("PlayStation symbols", glyphs()[:3] == ["✕", "□", "△"])

    # Every symbol sits in the middle of its button, and the buttons are round
    try:
        import PIL  # noqa: F401
    except ImportError:
        PIL = None
    if PIL:
        for style in ("xbox", "playstation"):
            shared.schema.set_string("hints-style", style)
            yield 300
            offsets = glyph_offsets(win, Path(SANDBOX) / f"glyphs-{style}.png")
            check(f"{style}: the symbols were measured", len(offsets) == 6)
            for symbol, width, height, dx, dy in offsets:
                check(f"{style}: {symbol} is centered (off {dx:+.1f}, {dy:+.1f})",
                      abs(dx) <= 1 and abs(dy) <= 1)
                check(f"{style}: {symbol} has the height of the legend", height == 22)
                if symbol in "ABXY✕○□△":
                    check(f"{style}: {symbol} is round", width == height)
        shared.schema.set_string("hints-style", "playstation")
        yield 300
    shot("1b-playstation-legend")
    shared.schema.set_string("hints-style", "xbox")
    yield 200

    # Nothing is focused yet: the first direction press focuses the first game
    press(BTN_DPAD_DOWN)
    yield 400
    first = card_name()
    check("first press focuses a card", first is not None)
    position = win.get_focused_card().list_item.get_position()

    press(BTN_DPAD_RIGHT)
    yield 400
    check("right moves one card",
          win.get_focused_card().list_item.get_position() == position + 1)
    press(BTN_DPAD_DOWN)
    yield 400
    check("down moves one row",
          win.get_focused_card().list_item.get_position() == position + 1 + cols())
    press(BTN_DPAD_UP)
    yield 400
    press(BTN_DPAD_LEFT)
    yield 400
    check("up and left come back",
          win.get_focused_card().list_item.get_position() == position)
    yield 400
    check("the banner follows the focused game",
          win.hero.game is win.get_focused_card().game)
    shot("2-card-focused")

    # A d-pad reported as a hat and the left stick do the same
    ctl.input.hat(ABS_HAT0Y, 1)
    ctl.input.hat(ABS_HAT0Y, 0)
    yield 400
    check("hat down moves one row",
          win.get_focused_card().list_item.get_position() == position + cols())
    ctl.input.axis(ABS_X, 0.9)
    ctl.input.axis(ABS_X, 0.0)
    yield 400
    check("stick right moves one card",
          win.get_focused_card().list_item.get_position() == position + cols() + 1)
    press(BTN_DPAD_UP)
    yield 300

    # Going left from the first column leaves the grid for the sidebar
    while win.get_focused_card().list_item.get_position() % cols():
        press(BTN_DPAD_LEFT)
        yield 400
    check("left stays in the grid until the first column", not in_sidebar())
    press(BTN_DPAD_LEFT)
    yield 400
    check("left from the first column enters the sidebar", in_sidebar())
    shot("3-sidebar")
    press(BTN_DPAD_DOWN)
    yield 300
    check("down moves between sidebar rows", in_sidebar())
    press(BTN_DPAD_RIGHT)
    yield 400
    check("right leaves the sidebar for the grid", not in_sidebar() and card_name() is not None)

    # LB / RB switch between sources (moving in the sidebar selects rows too)
    win.sidebar.select_row(win.all_games_row_box.get_parent())
    yield 300
    start_filter = win.filter_state
    press(BTN_TR)
    yield 300
    next_filter = win.filter_state
    check("RB selects the next source", next_filter != start_filter)
    press(BTN_TR)
    yield 300
    press(BTN_TL)
    yield 300
    check("LB selects the previous source", win.filter_state == next_filter)
    press(BTN_TL)
    yield 300
    check("LB goes back to the first source", win.filter_state == start_filter)
    press(BTN_TL)
    yield 300
    check("LB stops at the first source", win.filter_state == start_filter)
    win.focus_library()
    yield 200

    # A launches the game under the focus
    game = win.get_focused_card().game
    press(BTN_SOUTH)
    yield 300
    check("A launches the focused game", launched == [game.name])

    # X opens the card menu, the d-pad moves inside it, A picks Details
    press(BTN_WEST)
    yield 300
    card = win.get_focused_card()
    check("X opens the card menu", card.menu_button.get_active())
    shot_menu(card)
    check("the first menu item has the focus", in_popover())
    check("the legend describes the menu", legend() == ["Select", "Close"])
    press(BTN_DPAD_DOWN)
    yield 300
    press(BTN_DPAD_UP)
    yield 300
    check("down and up move inside the menu", in_popover())
    press(BTN_SOUTH)
    yield 600
    check("A on Details opens the details page",
          win.navigation_view.get_visible_page() == win.details_page
          and win.details_view_title.get_label() == game.name)
    shot("5-details")
    launched.clear()
    press(BTN_SOUTH)
    yield 300
    check("A on the details page launches the game", launched == [game.name])

    play_button = win.details_view_play_button
    for direction in (BTN_DPAD_RIGHT, BTN_DPAD_DOWN, BTN_DPAD_LEFT):
        if win.get_focus() is not play_button:
            break
        press(direction)
        yield from settle(lambda: win.get_focus() is not play_button, 1000)
    check("the d-pad moves between the detail buttons",
          win.get_focus() is not win.details_view_play_button)
    press(BTN_EAST)
    yield 500
    check("B goes back to the library",
          win.navigation_view.get_visible_page() == win.library_page)

    # B closes an open menu before anything else
    win.focus_library()
    yield 200
    press(BTN_WEST)
    yield 300
    press(BTN_EAST)
    yield 300
    check("B closes the card menu",
          not win.get_focused_card() or not win.get_focused_card().menu_button.get_active())
    check("B closing the menu stays on the library page",
          win.navigation_view.get_visible_page() == win.library_page)

    # Y toggles the search, B closes it
    press(BTN_NORTH)
    yield 300
    check("Y opens the search", win.search_bar.get_search_mode())
    yield 400
    check("the legend describes the search", legend() == ["Close Search"])
    check("the banner makes room for the search results",
          not win.library_header_revealer.get_reveal_child())
    press(BTN_EAST)
    yield 300
    check("B closes the search", not win.search_bar.get_search_mode())
    yield 500
    check("the banner is back after the search", win.library_header_revealer.get_reveal_child())
    check("the legend is back to the library", legend()[0] == "Play")

    # Menu / Options toggles the sidebar and focuses the selected row
    press(BTN_START)
    yield 300
    check("Menu hides the sidebar", not win.overlay_split_view.get_show_sidebar())
    press(BTN_START)
    yield 300
    check("Menu shows the sidebar", win.overlay_split_view.get_show_sidebar())
    check("the selected source gets the focus", in_sidebar())

    # Dialogs: the focus stays inside and B closes them
    app.on_preferences_action()
    yield from settle(lambda: win.get_visible_dialog() is not None)
    yield 400
    check("preferences dialog is open", win.get_visible_dialog() is not None)
    check("the legend describes the dialog", legend() == ["Select", "Close"])
    before = win.get_focus()
    press(BTN_DPAD_DOWN)
    yield from settle(lambda: win.get_focus() is not before)
    press(BTN_DPAD_DOWN)
    yield 300
    focus = win.get_focus()
    check("the focus moves inside the dialog",
          focus is not None and focus.get_ancestor(Adw.Dialog) is not None)
    shot("6-preferences")
    press(BTN_EAST)
    yield from settle(lambda: win.get_visible_dialog() is None)
    check("B closes the dialog", win.get_visible_dialog() is None)

    # Hidden games page and back
    win.activate_action("win.show_hidden", None)
    yield 500
    check("hidden page is open", win.navigation_view.get_visible_page() == win.hidden_library_page)
    press(BTN_EAST)
    yield 500
    check("B leaves the hidden page", win.navigation_view.get_visible_page() == win.library_page)

    # The Play button of the banner launches the game it shows
    launched.clear()
    win.hero.play_button.emit("clicked")
    yield 300
    check("the banner's Play launches its game", launched == [win.hero.game.name])
    win.hero.details_button.emit("clicked")
    yield 600
    check("the banner's Details opens the details page",
          win.navigation_view.get_visible_page() == win.details_page)
    press(BTN_EAST)
    yield 500

    print("RESULT " + json.dumps(results), flush=True)
    app.quit()


def main() -> None:
    make_library()
    Game.launch = lambda self, *args, **kwargs: launched.append(self.name)

    app_cls = app_main.CartridgesApplication
    orig_activate = app_cls.do_activate

    class DriverApp(app_cls):
        def do_activate(self):
            orig_activate(self)
            shared.win.set_default_size(960, 700)
            generator = steps(self)

            def run() -> bool:
                try:
                    delay = next(generator)
                except StopIteration:
                    return GLib.SOURCE_REMOVE
                except Exception:  # pylint: disable=broad-except
                    traceback.print_exc()
                    print("RESULT " + json.dumps({"driver crashed": False}), flush=True)
                    self.quit()
                    return GLib.SOURCE_REMOVE
                GLib.timeout_add(delay, run)
                return GLib.SOURCE_REMOVE

            GLib.timeout_add(300, run)

    from gi.repository import Gio

    app = DriverApp()
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    app.run([sys.argv[0]])


if __name__ == "__main__":
    main()
