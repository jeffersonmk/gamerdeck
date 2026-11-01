"""Tests for the Faugus and Lutris sources, with data made like the launchers do."""

# pylint: disable=missing-function-docstring,protected-access
import json
import shutil
import sqlite3
import unittest
from datetime import datetime

from tests.support import TMP

from cartridges import shared  # noqa: E402
from cartridges.game import Game  # noqa: E402
from cartridges.importer.faugus_source import (  # noqa: E402
    FLATPAK_ID,
    FaugusSource,
    parse_last_played,
)
from cartridges.importer.importer import Importer  # noqa: E402
from cartridges.importer.lutris_source import LutrisSource  # noqa: E402


def fresh_dir(name: str):
    path = TMP / name
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    return path


def faugus_data(root, entries) -> None:
    """A Faugus data directory with games.json and some covers/icons"""
    root.mkdir(parents=True, exist_ok=True)
    (root / "games.json").write_text(json.dumps(entries), encoding="utf-8")
    for folder in ("covers", "icons"):
        (root / folder).mkdir(exist_ok=True)


def run_source(source) -> list:
    return list(iter(source))


class FaugusTests(unittest.TestCase):
    def setUp(self):
        shared.import_time = 1_700_000_000
        self.addCleanup(shared.schema.reset, "faugus-location")

    def test_parse_last_played(self):
        iso = "2026-10-31T12:30:00"
        self.assertEqual(parse_last_played(iso), int(datetime.fromisoformat(iso).timestamp()))
        for bad in ("", None, "yesterday", 5, "2026-13-45"):
            self.assertEqual(parse_last_played(bad), 0)

    def test_games_are_read_from_games_json(self):
        root = fresh_dir("faugus-native")
        faugus_data(
            root,
            [
                {"gameid": "cyberpunk-2077", "title": "Cyberpunk 2077", "hidden": False,
                 "playtime": 3600, "last_played": "2026-10-31T12:30:00"},
                {"gameid": "old-game", "title": "Old Game", "hidden": True, "last_played": ""},
                {"gameid": "no-title"},  # invalid entries are skipped
                {"title": "No id"},
                "not a dict",
                {"gameid": "weird id; rm -rf", "title": "Quoted"},
            ],
        )
        (root / "covers" / "cyberpunk-2077.png").write_bytes(b"png")
        (root / "icons" / "cyberpunk-2077.png").write_bytes(b"png")
        (root / "icons" / "old-game.png").write_bytes(b"png")
        shared.schema.set_string("faugus-location", str(root))

        results = run_source(FaugusSource())

        games = {game.name: (game, extra) for game, extra in results}
        self.assertEqual(sorted(games), ["Cyberpunk 2077", "Old Game", "Quoted"])

        cyberpunk, extra = games["Cyberpunk 2077"]
        self.assertEqual(cyberpunk.game_id, "faugus_cyberpunk-2077")
        self.assertEqual(cyberpunk.source, "faugus")
        self.assertEqual(cyberpunk.executable, "faugus-launcher --game cyberpunk-2077")
        self.assertFalse(cyberpunk.hidden)
        self.assertEqual(
            cyberpunk.last_played,
            int(datetime.fromisoformat("2026-10-31T12:30:00").timestamp()),
        )
        # The cover wins, and only one image is given (the icon would replace it)
        self.assertEqual(extra, {"local_image_path": root / "covers" / "cyberpunk-2077.png"})

        old, extra = games["Old Game"]
        self.assertTrue(old.hidden)
        self.assertEqual(extra, {"local_icon_path": root / "icons" / "old-game.png"})

        quoted, extra = games["Quoted"]
        self.assertEqual(quoted.executable, "faugus-launcher --game 'weird id; rm -rf'")
        self.assertEqual(extra, {})

    def test_flatpak_install_starts_the_flatpak(self):
        root = shared.flatpak_dir / FLATPAK_ID / "data" / "faugus-launcher"
        shutil.rmtree(shared.flatpak_dir / FLATPAK_ID, ignore_errors=True)
        faugus_data(root, [{"gameid": "hades", "title": "Hades"}])
        shared.schema.set_string("faugus-location", str(root))

        ((game, _),) = run_source(FaugusSource())

        self.assertEqual(
            game.executable,
            f"flatpak run --command=/app/bin/faugus-launcher {FLATPAK_ID} --game hades",
        )
        shutil.rmtree(shared.flatpak_dir / FLATPAK_ID, ignore_errors=True)

    def test_broken_games_json_does_not_stop_the_import(self):
        root = fresh_dir("faugus-broken")
        root.mkdir(exist_ok=True)
        for content in ("{not json", '{"gameid": "a"}', ""):
            (root / "games.json").write_text(content)
            shared.schema.set_string("faugus-location", str(root))
            self.assertEqual(run_source(FaugusSource()), [])

    def test_the_default_location_is_found(self):
        source = FaugusSource()
        candidates = [str(c) for c in source.locations.data.candidates]
        self.assertIn(str(shared.data_dir / "faugus-launcher"), candidates)
        self.assertIn(str(shared.flatpak_dir / FLATPAK_ID / "data" / "faugus-launcher"), candidates)

    def test_launchers_added_as_games_are_not_imported(self):
        root = fresh_dir("faugus-launchers")
        faugus_data(
            root,
            [
                {"gameid": "hades", "title": "Hades"},
                {"gameid": "epic-games-launcher", "title": "Epic Games Launcher"},
                {"gameid": "battle-net", "title": "Battle.net"},
                {"gameid": "ea-app", "title": "EA app"},
            ],
        )
        shared.schema.set_string("faugus-location", str(root))

        class Store(list):
            def add_game(self, game, _extra):
                self.append(game)

        old_store = getattr(shared, "store", None)
        shared.store = Store()
        self.addCleanup(setattr, shared, "store", old_store)
        importer = Importer.__new__(Importer)
        importer.game_pipelines = set()
        importer.source_task_thread_func((FaugusSource(),))

        self.assertEqual([g.name for g in shared.store], ["Hades"])


def lutris_db(root, games, categories=(), links=()) -> None:
    """A pga.db with the tables and columns Lutris creates"""
    root.mkdir(parents=True, exist_ok=True)
    (root / "coverart").mkdir(exist_ok=True)
    connection = sqlite3.connect(root / "pga.db")
    connection.executescript(
        """
        CREATE TABLE games (id INTEGER PRIMARY KEY, name TEXT, sortname TEXT, slug TEXT,
            installer_slug TEXT, parent_slug TEXT, platform TEXT, runner TEXT,
            executable TEXT, directory TEXT, updated DATETIME, lastplayed INTEGER,
            installed INTEGER, installed_at INTEGER, year INTEGER, configpath TEXT,
            has_custom_banner INTEGER, has_custom_icon INTEGER,
            has_custom_coverart_big INTEGER, playtime REAL, service TEXT,
            service_id TEXT, discord_id TEXT);
        CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT UNIQUE);
        CREATE TABLE games_categories (game_id INTEGER, category_id INTEGER);
        """
    )
    for game_id, name, slug, runner, installed, configpath in games:
        connection.execute(
            "INSERT INTO games (id, name, slug, runner, installed, configpath) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (game_id, name, slug, runner, installed, configpath),
        )
    connection.executemany("INSERT INTO categories VALUES (?, ?)", categories)
    connection.executemany("INSERT INTO games_categories VALUES (?, ?)", links)
    connection.commit()
    connection.close()


class LutrisTests(unittest.TestCase):
    def setUp(self):
        shared.import_time = 1_700_000_000
        for key in ("lutris-location", "lutris-import-steam", "lutris-import-flatpak"):
            self.addCleanup(shared.schema.reset, key)

    def games(self, root):
        shared.schema.set_string("lutris-location", str(root))
        return {game.name: (game, extra) for game, extra in run_source(LutrisSource())}

    def test_installed_games_are_read_from_the_database(self):
        root = fresh_dir("lutris-basic")
        lutris_db(
            root,
            [
                (1, "Diablo II", "diablo-ii", "wine", 1, "diablo-ii-1700000000"),
                (2, "Not Installed", "not-installed", "wine", 0, "x"),
                (3, "No Config", "no-config", "linux", 1, None),
                (4, "Steam Thing", "steam-thing", "steam", 1, "steam-thing"),
                (5, "Flatpak Thing", "flatpak-thing", "flatpak", 1, "flatpak-thing"),
            ],
        )
        (root / "coverart" / "diablo-ii.jpg").write_bytes(b"jpg")

        games = self.games(root)

        self.assertEqual(sorted(games), ["Diablo II"])  # Steam/Flatpak are opt-in
        game, extra = games["Diablo II"]
        self.assertEqual(game.game_id, "lutris_wine_1")
        self.assertEqual(game.source, "lutris_wine")
        self.assertEqual(game.executable, "xdg-open lutris:rungameid/1")
        self.assertFalse(game.hidden)
        self.assertEqual(extra, {"local_image_path": root / "coverart" / "diablo-ii.jpg"})

    def test_steam_and_flatpak_games_when_asked_for(self):
        root = fresh_dir("lutris-optional")
        lutris_db(
            root,
            [
                (4, "Steam Thing", "steam-thing", "steam", 1, "a"),
                (5, "Flatpak Thing", "flatpak-thing", "flatpak", 1, "b"),
            ],
        )
        shared.schema.set_boolean("lutris-import-steam", True)
        shared.schema.set_boolean("lutris-import-flatpak", True)
        self.assertEqual(sorted(self.games(root)), ["Flatpak Thing", "Steam Thing"])

    def test_hidden_category_and_several_categories(self):
        root = fresh_dir("lutris-categories")
        lutris_db(
            root,
            [
                (1, "Hidden Game", "hidden-game", "linux", 1, "a"),
                (2, "Favorite Game", "favorite-game", "linux", 1, "b"),
                (3, "Favorite And Hidden", "fav-hidden", "linux", 1, "c"),
                (4, "Plain Game", "plain-game", "linux", 1, "d"),
            ],
            categories=[(1, ".hidden"), (2, "favorite")],
            links=[(1, 1), (2, 2), (3, 2), (3, 1)],
        )
        shared.schema.set_string("lutris-location", str(root))

        rows = [game for game, _extra in run_source(LutrisSource())]

        # A game in several categories is listed once, hidden if any of them is
        self.assertEqual(
            sorted((game.name, game.hidden) for game in rows),
            [
                ("Favorite And Hidden", True),
                ("Favorite Game", False),
                ("Hidden Game", True),
                ("Plain Game", False),
            ],
        )

    def test_lutris_wrappers_for_launchers_are_not_imported(self):
        root = fresh_dir("lutris-launchers")
        lutris_db(
            root,
            [
                (1, "Hades", "hades", "wine", 1, "a"),
                (2, "Epic Games Store", "epic", "wine", 1, "b"),
                (3, "Battle.net", "battlenet", "wine", 1, "c"),
            ],
        )
        shared.schema.set_string("lutris-location", str(root))

        class Store(list):
            def add_game(self, game, _extra):
                self.append(game)

        old_store = getattr(shared, "store", None)
        shared.store = Store()
        self.addCleanup(setattr, shared, "store", old_store)
        importer = Importer.__new__(Importer)
        importer.game_pipelines = set()
        importer.source_task_thread_func((LutrisSource(),))

        self.assertEqual([g.name for g in shared.store], ["Hades"])

    def test_no_database_means_the_source_is_skipped(self):
        root = fresh_dir("lutris-empty")
        shared.schema.set_string("lutris-location", str(root))
        source = LutrisSource()
        source.locations.data.candidates = ()  # nothing else to find on this machine
        from cartridges.importer.location import UnresolvableLocationError

        with self.assertRaises(UnresolvableLocationError):
            iter(source)

    def test_game_is_a_model(self):
        self.assertIsInstance(Game({"game_id": "x", "source": "faugus", "name": "X", "executable": "x"}), Game)


if __name__ == "__main__":
    unittest.main()
