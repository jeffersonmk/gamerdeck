"""Tests for importing only games: launchers, tools and runtimes are skipped."""

# pylint: disable=missing-function-docstring,protected-access,import-outside-toplevel
import shutil
import unittest
from types import SimpleNamespace

from tests.support import TMP

from gi.repository import GLib, Gtk  # noqa: E402

from cartridges import shared  # noqa: E402
from cartridges.game import Game  # noqa: E402
from cartridges.importer import not_games  # noqa: E402
from cartridges.importer.desktop_source import (  # noqa: E402
    DesktopSource,
    DesktopSourceIterable,
)
from cartridges.importer.importer import Importer  # noqa: E402


class NameTests(unittest.TestCase):
    def test_steam_tools_and_runtimes(self):
        for name in (
            "Proton 11.0",
            "Proton 9.0-4",
            "Proton Experimental",
            "Proton Hotfix",
            "Proton EasyAntiCheat Runtime",
            "Proton-GE 9-1",
            "Steam Linux Runtime 4.0",
            "Steam Linux Runtime 3.0 (sniper)",
            "Steamworks Common Redistributables",
            "SteamVR",
            "Wallpaper Engine",
            "Source SDK Base 2013 Multiplayer",
            "Half-Life Dedicated Server",
        ):
            self.assertTrue(not_games.is_not_a_game_name(name), name)

    def test_launchers_stores_and_tools(self):
        for name in (
            "Steam",
            "Epic Games Launcher",
            "Epic Games Store",
            "Heroic Games Launcher",
            "Lutris",
            "Faugus",
            "Bottles",
            "Battle.net®",
            "EA app",
            "GOG GALAXY",
            "Ubisoft Connect",
            "Goverlay",
            "ProtonUp-Qt",
            "Parsec",
            "PCSX2",
            "RetroArch",
            "Gamerdeck (TESTE)",
            "Cartridges",
        ):
            self.assertTrue(not_games.is_not_a_game_name(name), name)

    def test_real_games_are_kept(self):
        for name in (
            "Elden Ring",
            "Street Fighter™ 6",
            "Resident Evil 4",
            "Stellar Blade™",
            "Gran Turismo 4",
            "Proton Pulse",  # starts like Proton, is a game
            "Epic Mickey",
            "Heroic Hearts",
            "Steam Hammer",
            "Origin of the Universe",
            "Portal",
            "Hades",
        ):
            self.assertFalse(not_games.is_not_a_game_name(name), name)


class DesktopEntryTests(unittest.TestCase):
    def check(self, entry_id, name, executable, categories) -> bool:
        return not_games.is_not_a_game_desktop_entry(
            entry_id, name, executable, categories
        )

    def test_clients_and_tools_are_skipped(self):
        for args in (
            ("steam", "Steam", "/usr/bin/steam %U", ["Network", "FileTransfer", "Game"]),
            ("com.heroicgameslauncher.hgl", "Heroic Games Launcher", "heroic %U", ["Game"]),
            ("net.lutris.Lutris", "Lutris", "lutris %U", ["Game", "PackageManager"]),
            ("io.github.Faugus.faugus-launcher", "Faugus", "faugus-launcher %f", ["Game"]),
            ("parsecd", "Parsec", "/usr/bin/parsecd %u", ["Network", "Game", "Utility"]),
            ("pcsx2", "PCSX2", "pcsx2 %f", ["Game", "Emulator"]),
            ("net.davidotek.pupgui2", "ProtonUp-Qt", "net.davidotek.pupgui2", ["Game", "Utility"]),
            ("x", "Some tool", "env FOO=1 goverlay", ["Game"]),
            ("fp", "Client", "flatpak run com.valvesoftware.Steam @@u %U @@", ["Game"]),
        ):
            self.assertTrue(self.check(*args), args)

    def test_games_are_kept(self):
        for args in (
            ("supertuxkart", "SuperTuxKart", "supertuxkart", ["Game", "ArcadeGame"]),
            ("0ad", "0 A.D.", "0ad %f", ["Game", "StrategyGame"]),
            # A shortcut that starts one game on an emulator is a game
            (
                "gt4",
                "Gran Turismo 4",
                'mangohud pcsx2-qt -fullscreen "/roms/GT4.iso"',
                ["Game", "Emulator"],
            ),
            ("sf", "Retro Game", "flatpak run org.libretro.RetroArch -L core.so rom.sfc", ["Game"]),
            ("elden", "Elden Ring", "steam steam://rungameid/1245620", ["Game"]),
        ):
            self.assertFalse(self.check(*args), args)

    def test_has_target(self):
        self.assertFalse(not_games.has_target("steam %U"))
        self.assertFalse(not_games.has_target("/usr/bin/steam -silent %U"))
        self.assertFalse(not_games.has_target("flatpak run --branch=stable com.valvesoftware.Steam @@u %U @@"))
        self.assertTrue(not_games.has_target("flatpak run com.x.Emu game.iso"))
        self.assertTrue(not_games.has_target("pcsx2-qt -fullscreen /roms/a.iso"))
        self.assertFalse(not_games.has_target("gamemoderun mangohud ./game"))  # the game itself
        self.assertTrue(not_games.has_target("mangohud pcsx2-qt game.iso"))

    def test_program_name(self):
        self.assertEqual(not_games.program_name("/usr/bin/steam %U"), "steam")
        self.assertEqual(not_games.program_name("env A=1 mangohud lutris %U"), "lutris")
        self.assertEqual(
            not_games.program_name("flatpak run --branch=stable com.valvesoftware.Steam"),
            "com.valvesoftware.Steam",
        )


APPLICATIONS = {
    "steam.desktop": ("Steam", "/usr/bin/steam %U", "Network;FileTransfer;Game;"),
    "heroic.desktop": ("Heroic Games Launcher", "heroic %U", "Game;"),
    "lutris.desktop": ("Lutris", "lutris %U", "Game;PackageManager;"),
    "goverlay.desktop": ("Goverlay", "goverlay", "Game;"),
    "pcsx2.desktop": ("PCSX2", "pcsx2 %f", "Game;Emulator"),
    "parsec.desktop": ("Parsec", "/usr/bin/parsecd %u", "Network;Game;Utility;"),
    "gt4.desktop": ("Gran Turismo 4", 'mangohud pcsx2-qt "/roms/GT4.iso"', "Game;Emulator;"),
    "tux.desktop": ("SuperTuxKart", "supertuxkart", "Game;ArcadeGame;"),
    "editor.desktop": ("Text Editor", "gedit %U", "Utility;TextEditor;"),
}


class DesktopSourceTests(unittest.TestCase):
    def test_only_games_are_imported_from_desktop_entries(self):
        data = TMP / "desktop-data"
        shutil.rmtree(data, ignore_errors=True)
        (data / "applications").mkdir(parents=True)
        for file_name, (name, exec_, categories) in APPLICATIONS.items():
            (data / "applications" / file_name).write_text(
                f"[Desktop Entry]\nType=Application\nName={name}\nExec={exec_}\n"
                f"Categories={categories}\n"
            )

        real = (shared.host_data_dir, GLib.get_system_data_dirs, getattr(shared, "win", None))
        shared.host_data_dir = data
        GLib.get_system_data_dirs = lambda: []
        shared.win = SimpleNamespace(get_direction=lambda: Gtk.TextDirection.LTR)
        try:
            source = DesktopSource()
            games = [
                item[0] if isinstance(item, tuple) else item
                for item in DesktopSourceIterable(source)
            ]
        finally:
            shared.host_data_dir, GLib.get_system_data_dirs = real[0], real[1]
            if real[2] is not None:
                shared.win = real[2]

        self.assertEqual(
            sorted(game.name for game in games), ["Gran Turismo 4", "SuperTuxKart"]
        )


def make_game(name: str, source: str = "steam", game_id: str = "") -> Game:
    return Game(
        {
            "game_id": game_id or f"{source}_{name}",
            "source": source,
            "name": name,
            "executable": "true",
        }
    )


class FakeStore(list):
    def __init__(self, games=()):
        super().__init__(games)
        self.added: list[Game] = []

    def add_game(self, game, _additional_data):
        self.added.append(game)


class ImporterTests(unittest.TestCase):
    def setUp(self):
        self.old_store = getattr(shared, "store", None)
        self.addCleanup(setattr, shared, "store", self.old_store)
        shared.schema.set_boolean("flatpak-import-launchers", False)
        self.importer = Importer.__new__(Importer)  # no dialog or progress needed
        self.importer.removed_game_ids = set()
        self.importer.game_pipelines = set()

    def test_sources_skip_what_is_not_a_game(self):
        class FakeSource:
            is_available = True
            source_id = "steam"

            def __iter__(self):
                return iter(
                    [
                        make_game("Elden Ring"),
                        make_game("Proton 11.0"),
                        make_game("Steam Linux Runtime 4.0"),
                        make_game("Epic Games Launcher", "lutris_wine"),
                        (make_game("Hades"), {"steam_appid": "1145360"}),
                        make_game("Lutris", "flatpak"),
                    ]
                )

        shared.store = FakeStore()
        self.importer.source_task_thread_func((FakeSource(),))
        self.assertEqual([g.name for g in shared.store.added], ["Elden Ring", "Hades"])

    def test_flatpak_launchers_can_be_asked_for(self):
        shared.schema.set_boolean("flatpak-import-launchers", True)
        self.assertFalse(self.importer.is_not_a_game(make_game("Steam", "flatpak")))
        self.assertTrue(self.importer.is_not_a_game(make_game("Steam", "steam")))

    def test_games_added_by_hand_are_never_filtered(self):
        self.assertFalse(self.importer.is_not_a_game(make_game("Steam", "imported")))

    def test_earlier_imports_are_cleaned_up_even_without_remove_missing(self):
        shared.schema.set_boolean("remove-missing", False)
        games = [
            make_game("Resident Evil 4"),
            make_game("Proton 11.0"),
            make_game("Steamworks Common Redistributables"),
            make_game("Goverlay", "desktop"),
            make_game("My Own Steam", "imported"),
        ]
        for game in games:
            game.save = game.update = lambda: None
        shared.store = FakeStore(games)

        self.importer.remove_not_games()

        self.assertEqual(
            sorted(g.name for g in games if g.removed),
            ["Goverlay", "Proton 11.0", "Steamworks Common Redistributables"],
        )
        self.assertEqual(len(self.importer.removed_game_ids), 3)

        self.importer.remove_not_games()  # nothing more to do the second time
        self.assertEqual(len(self.importer.removed_game_ids), 3)


if __name__ == "__main__":
    unittest.main()
