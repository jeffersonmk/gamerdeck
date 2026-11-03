"""Tests for the platform badge: where a game came from and how to open its app."""

# pylint: disable=missing-function-docstring,protected-access
import os
import shutil
import unittest
from unittest import mock

import tests.support  # noqa: F401  (sets the environment)
from gi.repository import Adw, Gio  # noqa: E402

from cartridges import platforms, shared  # noqa: E402
from cartridges.game import Game  # noqa: E402


def make_game(source: str, name: str = "Some Game", game_id: str = "", hidden=False):
    return Game(
        {
            "game_id": game_id or f"{source}_1",
            "source": source,
            "name": name,
            "executable": "true",
            "hidden": hidden,
        }
    )


class PlatformOfTests(unittest.TestCase):
    def test_every_source_has_the_right_platform(self):
        for source, platform_id in (
            ("steam", "steam"),
            ("lutris_wine", "lutris"),
            ("lutris_linux", "lutris"),
            ("faugus", "faugus"),
            ("heroic_legendary", "epic"),
            ("heroic_gog", "gog"),
            ("heroic_nile", "amazon"),
            ("heroic_sideload", "heroic"),
            ("bottles", "bottles"),
            ("itch", "itch"),
            ("retroarch", "retroarch"),
            ("legendary", "legendary"),
        ):
            platform = platforms.platform_of(make_game(source))
            self.assertIsNotNone(platform, source)
            self.assertEqual(platform.id, platform_id, source)

    def test_sources_without_a_client_have_no_badge(self):
        for source in ("imported", "desktop", "flatpak", "something_else"):
            self.assertIsNone(platforms.platform_of(make_game(source)), source)

    def test_epic_games_are_opened_with_heroic(self):
        platform = platforms.platform_of(make_game("heroic_legendary"))
        self.assertEqual(platform.icon, "epic-source-symbolic")
        self.assertEqual(platform.client.name, "Heroic")

    def test_legendary_has_no_app_to_open(self):
        game = make_game("legendary")
        self.assertIsNone(platforms.client_of(game))
        self.assertIsNone(platforms.client_command(game))
        self.assertFalse(platforms.open_client(game))

    def test_desktop_emulator_opens_its_emulator_app(self):
        game = make_game("desktop", name="Gran Turismo 4")
        game.emulator = "pcsx2"
        game.console = "ps2"
        client = platforms.client_of(game)
        if client is None:
            self.fail("PCSX2 must be recognized as the desktop game's client")
        self.assertEqual(client.name, "PCSX2")
        with mock.patch("shutil.which", return_value="/usr/bin/pcsx2-qt"):
            self.assertEqual(platforms.client_command(game), "pcsx2-qt")

    def test_unrecognized_emulator_has_no_client(self):
        game = make_game("desktop")
        game.emulator = "some-emulator"
        self.assertIsNone(platforms.client_of(game))
        self.assertIsNone(platforms.client_command(game))

    def test_every_console_icon_is_in_the_resources(self):
        from cartridges.emulators import CONSOLE_ICONS

        for icon in set(CONSOLE_ICONS.values()):
            Gio.resources_get_info(
                f"{shared.PREFIX}/icons/consoles/{icon}", 0
            )

    def test_every_icon_is_in_the_resources(self):
        for platform in platforms.PLATFORMS.values():
            path = f"{shared.PREFIX}/icons/scalable/categories/{platform.icon}.svg"
            Gio.resources_get_info(path, 0)  # raises if the icon is missing


class ClientCommandTests(unittest.TestCase):
    def setUp(self):
        self.flatpak_dirs = []
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("FLATPAK_ID", None)

    def tearDown(self):
        for path in self.flatpak_dirs:
            shutil.rmtree(path, ignore_errors=True)

    def install_flatpak(self, flatpak_id: str):
        path = shared.flatpak_dir / flatpak_id
        path.mkdir(parents=True, exist_ok=True)
        self.flatpak_dirs.append(path)

    def test_emulator_flatpak_is_used_when_it_is_installed(self):
        self.install_flatpak("net.pcsx2.PCSX2")
        game = make_game("desktop")
        game.emulator = "pcsx2"
        with mock.patch("shutil.which", return_value=None):
            self.assertEqual(
                platforms.client_command(game), "flatpak run net.pcsx2.PCSX2"
            )

    def test_steam_opens_the_page_of_the_game(self):
        game = make_game("steam", game_id="steam_1364780")
        self.assertEqual(
            platforms.client_command(game),
            "xdg-open steam://nav/games/details/1364780",
        )

    def test_steam_game_with_a_strange_id_opens_the_client(self):
        game = make_game("steam", game_id="steam_not-a-number; rm -rf")
        with mock.patch("shutil.which", return_value="/usr/bin/steam"):
            self.assertEqual(platforms.client_command(game), "steam")

    def test_native_client_is_used_when_installed(self):
        with mock.patch("shutil.which", return_value="/usr/bin/lutris"):
            self.assertEqual(platforms.client_command(make_game("lutris_wine")), "lutris")

    def test_flatpak_client_when_there_is_no_native_one(self):
        self.install_flatpak("com.heroicgameslauncher.hgl")
        with mock.patch("shutil.which", return_value=None):
            self.assertEqual(
                platforms.client_command(make_game("heroic_gog")),
                "flatpak run com.heroicgameslauncher.hgl",
            )

    def test_native_client_wins_over_a_leftover_flatpak(self):
        self.install_flatpak("net.lutris.Lutris")
        with mock.patch("shutil.which", return_value="/usr/bin/lutris"):
            self.assertEqual(platforms.client_command(make_game("lutris_wine")), "lutris")

    def test_command_is_tried_even_if_nothing_is_found(self):
        with mock.patch("shutil.which", return_value=None):
            self.assertEqual(
                platforms.client_command(make_game("faugus")), "faugus-launcher"
            )

    def test_inside_the_sandbox_host_commands_cannot_be_looked_up(self):
        os.environ["FLATPAK_ID"] = shared.APP_ID
        self.install_flatpak("io.github.Faugus.faugus-launcher")
        with mock.patch("shutil.which", return_value="/usr/bin/faugus-launcher"):
            self.assertEqual(
                platforms.client_command(make_game("faugus")),
                "flatpak run io.github.Faugus.faugus-launcher",
            )

    def test_open_client_runs_the_command(self):
        game = make_game("steam", game_id="steam_42")
        with mock.patch.object(platforms, "run_executable") as run:
            self.assertTrue(platforms.open_client(game))
        run.assert_called_once_with("xdg-open steam://nav/games/details/42")


class GameWidgetBadgeTests(unittest.TestCase):
    def setUp(self):
        Adw.init()
        from cartridges.game_widget import GameWidget

        self.card = GameWidget()

    def test_badge_follows_the_bound_game(self):
        steam = make_game("steam", game_id="steam_1")
        manual = make_game("imported", game_id="imported_1")
        self.assertFalse(self.card.platform_button.get_visible())

        self.card.bind(steam)
        self.assertTrue(self.card.platform_button.get_visible())
        self.assertEqual(self.card.platform_button.get_icon_name(), "steam-source-symbolic")
        self.assertEqual(self.card.platform_button.get_tooltip_text(), "Open Steam")

        self.card.unbind()
        self.assertFalse(self.card.platform_button.get_visible())

        self.card.bind(manual)  # recycled for a game with no app to open
        self.assertFalse(self.card.platform_button.get_visible())

        self.card.bind(make_game("heroic_gog", game_id="heroic_gog_1"))
        self.assertEqual(self.card.platform_button.get_icon_name(), "gog-source-symbolic")
        self.assertEqual(self.card.platform_button.get_tooltip_text(), "Open Heroic")

    def menu_items(self, model):
        """[(label, action)] of a menu, looking inside its sections"""
        items = []
        for i in range(model.get_n_items()):
            if section := model.get_item_link(i, "section"):
                items.extend(self.menu_items(section))
                continue
            label = model.get_item_attribute_value(i, "label", None)
            action = model.get_item_attribute_value(i, "action", None)
            items.append((label.get_string(), action.get_string()))
        return items

    def test_menu_has_the_open_client_entry(self):
        self.card.bind(make_game("steam", game_id="steam_1"))
        self.card.create_menu(self.card.menu_button)
        items = self.menu_items(self.card.menu_button.get_menu_model())
        self.assertEqual(
            items,
            [
                ("Details", "app.show_game_details"),
                ("Edit", "app.edit_game"),
                ("Hide", "app.hide_game"),
                ("Remove", "app.remove_game"),
                ("Open Steam", "app.open_game_client"),
            ],
        )

    def test_hidden_game_menu_and_rebinding(self):
        self.card.bind(make_game("steam", game_id="steam_1", hidden=True))
        self.card.create_menu(self.card.menu_button)
        labels = [label for label, _action in self.menu_items(self.card.menu_button.get_menu_model())]
        self.assertIn("Unhide", labels)
        self.assertIn("Open Steam", labels)

        # A game with no app to open gets the plain menu
        self.card.unbind()
        self.card.bind(make_game("imported", game_id="imported_1"))
        self.card.create_menu(self.card.menu_button)
        self.assertIs(self.card.menu_button.get_menu_model(), self.card.game_options)

    def test_menu_is_not_rebuilt_for_the_same_game_type(self):
        self.card.bind(make_game("steam", game_id="steam_1"))
        self.card.create_menu(self.card.menu_button)
        first = self.card.menu_button.get_menu_model()
        self.card.create_menu(self.card.menu_button)
        self.assertIs(self.card.menu_button.get_menu_model(), first)


class ConsoleIconTests(unittest.TestCase):
    def test_every_console_of_an_emulator_has_a_bundled_icon(self):
        from pathlib import Path

        from cartridges import emulators

        icons = Path(__file__).resolve().parent.parent / "data" / "icons" / "consoles"
        consoles = {e.console for e in emulators._EMULATORS.values()}  # pylint: disable=protected-access
        for console in consoles:
            self.assertIn(console, emulators.CONSOLE_ICONS, console)
        for console, icon_file in emulators.CONSOLE_ICONS.items():
            self.assertTrue((icons / icon_file).is_file(), console)
        bundled = {p.name for p in icons.iterdir() if p.suffix in (".png", ".svg")}
        self.assertEqual(bundled, set(emulators.CONSOLE_ICONS.values()))


if __name__ == "__main__":
    unittest.main()
