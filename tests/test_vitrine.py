"""The legend of controller buttons, the row of recent games and the family of controllers.

The window itself (banner, legend contexts) is checked by gamepad_ui.py.
"""

# pylint: disable=missing-function-docstring
import unittest
from unittest import mock

from tests.support import TMP  # noqa: F401  (sandbox first)

from gi.repository import Adw  # noqa: E402

from cartridges import hints  # noqa: E402
from cartridges.game import Game  # noqa: E402
from cartridges.hints import HintBar, controller_family, hints_for  # noqa: E402
from cartridges.rail import RAIL_SIZE, recent_games  # noqa: E402

# SDL GUIDs as libmanette reports them: bus, crc, vendor, 0, product, 0, ...
DUALSENSE_GUID = "030000004c050000e60c000011810000"
DUALSHOCK4_GUID = "030000004c050000cc09000011810000"
XBOX_SERIES_GUID = "030000005e040000130b000017050000"
EIGHTBITDO_GUID = "03000000c82d00000631000000000000"


def make_game(name: str, last_played: int) -> Game:
    return Game(
        {
            "game_id": f"imported_{name}",
            "source": "imported",
            "name": name,
            "executable": "true",
            "last_played": last_played,
        }
    )


class ControllerFamilyTests(unittest.TestCase):
    def test_sony_controllers_by_vendor(self):
        self.assertEqual(controller_family("", DUALSENSE_GUID), hints.PLAYSTATION)
        self.assertEqual(controller_family("", DUALSHOCK4_GUID), hints.PLAYSTATION)

    def test_xbox_controllers_by_vendor(self):
        self.assertEqual(controller_family("", XBOX_SERIES_GUID), hints.XBOX)

    def test_the_name_is_used_when_the_guid_says_nothing(self):
        for name in ("DualSense Wireless Controller", "Sony Interactive Entertainment Wireless Controller",
                     "PS4 Controller"):
            self.assertEqual(controller_family(name, ""), hints.PLAYSTATION, name)
        self.assertEqual(controller_family("Xbox Wireless Controller", ""), hints.XBOX)

    def test_vendor_beats_the_name(self):
        self.assertEqual(controller_family("Xbox lookalike", DUALSENSE_GUID), hints.PLAYSTATION)

    def test_other_brands_and_garbage_look_like_an_xbox_controller(self):
        self.assertEqual(controller_family("8BitDo Pro 2", EIGHTBITDO_GUID), hints.XBOX)
        self.assertEqual(controller_family("", "zzzzzzzzzzzzzzzz"), hints.XBOX)
        self.assertEqual(controller_family("", ""), hints.XBOX)
        self.assertEqual(controller_family(), hints.XBOX)


class LegendTests(unittest.TestCase):
    def test_every_context_has_a_legend_with_known_buttons(self):
        for context in (hints.MENU, hints.DIALOG, hints.SEARCH, hints.DETAILS, hints.SIDEBAR,
                        hints.LIBRARY, hints.HIDDEN):
            legend = hints_for(context)
            self.assertTrue(legend, context)
            for hint in legend:
                self.assertTrue(hint.label, context)
                for button in hint.buttons:
                    for style in (hints.XBOX, hints.PLAYSTATION):
                        self.assertIn(button, hints.GLYPHS[style], f"{context}/{style}")

    def test_every_hint_is_something_the_controller_really_does(self):
        # The library legend must match the controller map of the README
        library = {h.label: h.buttons for h in hints_for(hints.LIBRARY)}
        self.assertEqual(library["Play"], ("a",))
        self.assertEqual(library["Menu"], ("x",))
        self.assertEqual(library["Search"], ("y",))
        self.assertEqual(library["Sources"], ("lb", "rb"))
        self.assertEqual(library["Sidebar"], ("menu",))

    def test_both_styles_cover_the_same_buttons(self):
        self.assertEqual(set(hints.GLYPHS[hints.XBOX]), set(hints.GLYPHS[hints.PLAYSTATION]))

    def test_playstation_uses_its_own_symbols(self):
        glyphs = hints.GLYPHS[hints.PLAYSTATION]
        self.assertEqual([glyphs[b] for b in hints.FACE_BUTTONS], ["✕", "○", "□", "△"])
        self.assertEqual([hints.GLYPHS[hints.XBOX][b] for b in hints.FACE_BUTTONS], list("ABXY"))

    def test_the_bar_draws_symbols_and_texts(self):
        Adw.init()
        bar = HintBar()
        bar.set_hints(hints_for(hints.LIBRARY), hints.PLAYSTATION)

        texts, glyph_texts = [], []
        item = bar.get_first_child()
        while item:
            child = item.get_first_child()
            while child:
                (texts if child.has_css_class("hint-label") else glyph_texts).append(child.get_label())
                child = child.get_next_sibling()
            item = item.get_next_sibling()
        self.assertEqual(texts, ["Play", "Menu", "Search", "Sources", "Sidebar"])
        self.assertEqual(glyph_texts, ["✕", "□", "△", "L1", "R1", "OPTIONS"])

        bar.set_hints(hints_for(hints.LIBRARY), hints.XBOX)  # same hints, other style
        self.assertEqual(bar.get_first_child().get_first_child().get_label(), "A")

    def test_setting_the_same_hints_does_not_rebuild_the_bar(self):
        Adw.init()
        bar = HintBar()
        bar.set_hints(hints_for(hints.LIBRARY), hints.XBOX)
        first = bar.get_first_child()
        bar.set_hints(hints_for(hints.LIBRARY), hints.XBOX)
        self.assertIs(bar.get_first_child(), first)


def ink_of(symbol: str, size: int = 22):
    """The pixels (alpha) that draw_shape paints, and their bounding box"""
    import cairo

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    hints.draw_shape(symbol, cairo.Context(surface), size, (1, 1, 1, 1))
    data, stride = bytes(surface.get_data()), surface.get_stride()
    alpha = [[data[y * stride + x * 4 + 3] for x in range(size)] for y in range(size)]
    cells = [(x, y) for y in range(size) for x in range(size) if alpha[y][x] > 40]
    xs, ys = [c[0] for c in cells], [c[1] for c in cells]
    return alpha, (min(xs), min(ys), max(xs) + 1, max(ys) + 1)


class DrawnSymbolTests(unittest.TestCase):
    def test_the_square_is_centered_and_has_crisp_outer_edges(self):
        alpha, (x0, y0, x1, y1) = ink_of("□")
        self.assertEqual((x0 + x1, y0 + y1), (22, 22))  # centered, to the pixel
        self.assertEqual((x1 - x0, y1 - y0), (hints.SQUARE_SIDE, hints.SQUARE_SIDE))
        # The outside edges are whole pixels (not blurred over two)
        for x in range(x0, x1):
            self.assertGreater(alpha[y0][x], 200)
            self.assertGreater(alpha[y1 - 1][x], 200)
        for y in range(y0, y1):
            self.assertGreater(alpha[y][x0], 200)
            self.assertGreater(alpha[y][x1 - 1], 200)

    def test_the_square_is_hollow(self):
        alpha, _box = ink_of("□")
        self.assertEqual(alpha[11][11], 0)

    def test_the_triangle_is_centered_across_and_a_little_high(self):
        _alpha, (x0, y0, x1, y1) = ink_of("△")
        self.assertEqual(x0 + x1, 22)  # symmetric
        # The box is lifted by less than a pixel and a half, never lowered
        lift = (22 - (y0 + y1)) / 2
        self.assertTrue(0 <= lift <= 1.5, lift)

    def test_the_triangle_is_hollow_and_points_up(self):
        alpha, (x0, y0, x1, y1) = ink_of("△")
        self.assertEqual(alpha[(y0 + y1) // 2 + 1][11], 0)  # the hole
        top = sum(1 for x in range(22) if alpha[y0][x] > 40)
        bottom = sum(1 for x in range(22) if alpha[y1 - 1][x] > 40)
        self.assertLess(top, bottom)  # narrow apex, wide base

    def test_both_shapes_are_about_the_size_of_the_cross(self):
        # The cross measures 9x9 to 10x10 on the screen
        for symbol in ("□", "△"):
            _alpha, (x0, y0, x1, y1) = ink_of(symbol)
            self.assertTrue(9 <= x1 - x0 <= 12, symbol)
            self.assertTrue(9 <= y1 - y0 <= 11, symbol)

    def test_the_legend_draws_them_and_keeps_the_font_for_the_rest(self):
        Adw.init()
        shapes = {b: hints.make_glyph(b, hints.PLAYSTATION) for b in ("a", "b", "x", "y")}
        self.assertIsInstance(shapes["x"], hints.PadShape)
        self.assertIsInstance(shapes["y"], hints.PadShape)
        self.assertEqual((shapes["x"].get_label(), shapes["y"].get_label()), ("□", "△"))
        self.assertNotIsInstance(shapes["a"], hints.PadShape)  # the cross and circle: font
        self.assertNotIsInstance(shapes["b"], hints.PadShape)
        # Xbox letters are text
        self.assertNotIsInstance(hints.make_glyph("x", hints.XBOX), hints.PadShape)

    def test_a_drawn_symbol_paints_without_errors(self):
        Adw.init()
        glyph = hints.make_glyph("y", hints.PLAYSTATION)
        self.assertEqual((glyph.get_content_width(), glyph.get_content_height()), (22, 22))
        import cairo

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 22, 22)
        glyph._draw(glyph, cairo.Context(surface), 22, 22)  # pylint: disable=protected-access


class FamilyOfTheControllerInUseTests(unittest.TestCase):
    def make(self, *devices):
        from cartridges.gamepad import GamepadController

        controller = GamepadController(mock.Mock())
        controller.devices = set(devices)
        return controller

    @staticmethod
    def device(name, guid):
        return mock.Mock(get_name=lambda: name, get_guid=lambda: guid)

    def test_no_controller_means_xbox(self):
        self.assertEqual(self.make().family, hints.XBOX)

    def test_the_controller_used_last_wins(self):
        xbox = self.device("Xbox Wireless Controller", XBOX_SERIES_GUID)
        sony = self.device("DualSense Wireless Controller", DUALSENSE_GUID)
        controller = self.make(xbox, sony)
        controller.last_device = sony
        self.assertEqual(controller.family, hints.PLAYSTATION)
        controller.last_device = xbox
        self.assertEqual(controller.family, hints.XBOX)

    def test_a_disconnected_controller_is_forgotten(self):
        sony = self.device("DualSense Wireless Controller", DUALSENSE_GUID)
        xbox = self.device("Xbox Wireless Controller", XBOX_SERIES_GUID)
        controller = self.make(xbox)
        controller.last_device = sony  # no longer in `devices`
        self.assertEqual(controller.family, hints.XBOX)


class StyleSheetTests(unittest.TestCase):
    def test_the_style_sheets_do_not_force_an_accent_color(self):
        """Buttons, the banner and the focus ring follow the accent color of the system"""
        from gi.repository import Gio

        from cartridges import shared

        for name in ("style.css", "style-dark.css"):
            try:
                css = bytes(Gio.resources_lookup_data(f"{shared.PREFIX}/{name}", 0).get_data()).decode()
            except Exception:  # pylint: disable=broad-exception-caught
                continue  # not part of the resources of this build
            self.assertNotIn("--accent-color", css, name)
            self.assertNotIn("--accent-bg-color", css, name)
            self.assertNotIn("purple", css, name)

    def test_the_main_style_sheet_was_found(self):
        from gi.repository import Gio

        from cartridges import shared

        data = Gio.resources_lookup_data(f"{shared.PREFIX}/style.css", 0)
        self.assertIn(b"hint-strip", bytes(data.get_data()))  # the test above looked at the real one


class RecentGamesTests(unittest.TestCase):
    def test_newest_first_and_never_played_games_are_left_out(self):
        games = [make_game("old", 10), make_game("never", 0), make_game("new", 30), make_game("mid", 20)]
        self.assertEqual([g.name for g in recent_games(games)], ["new", "mid", "old"])

    def test_the_row_has_a_limit(self):
        games = [make_game(f"g{i}", i + 1) for i in range(RAIL_SIZE + 5)]
        found = recent_games(games)
        self.assertEqual(len(found), RAIL_SIZE)
        self.assertEqual(found[0].name, f"g{RAIL_SIZE + 4}")

    def test_no_games(self):
        self.assertEqual(recent_games([]), [])
        self.assertEqual(recent_games([make_game("never", 0)]), [])


if __name__ == "__main__":
    unittest.main()
