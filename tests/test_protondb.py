"""Tests for ProtonDB ratings: lookup, cache, failures and the badges.

No test touches the network: the HTTP function is a fake with the shape of the
answers of the Steam store and ProtonDB (checked by hand against the real
services).
"""

# pylint: disable=missing-function-docstring,protected-access
import json
import shutil
import unittest
from unittest import mock

from tests.support import TMP

import requests  # noqa: E402
from gi.repository import Adw  # noqa: E402

from cartridges import shared  # noqa: E402
from cartridges.game import Game  # noqa: E402
from cartridges.utils import protondb  # noqa: E402
from cartridges.utils.protondb import ProtonDBRatings, Rating  # noqa: E402


def make_game(source: str, name: str, game_id: str = "") -> Game:
    return Game(
        {
            "game_id": game_id or f"{source}_{name}",
            "source": source,
            "name": name,
            "executable": "true",
        }
    )


class FakeWeb:
    """The Steam store search and the ProtonDB summaries"""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.summaries = {
            "1245620": {"tier": "gold", "bestReportedTier": "platinum", "total": 2107},
            "1364780": {"tier": "platinum", "total": 880},
            "999": {"tier": "weird-new-tier", "total": 3},
        }
        self.store = [
            {"type": "app", "id": 1245620, "name": "ELDEN RING"},
            {"type": "app", "id": 2622380, "name": "ELDEN RING NIGHTREIGN"},
            {"type": "app", "id": 1145360, "name": "Hades"},
            {"type": "dlc", "id": 5, "name": "Soundtrack"},
        ]
        self.fail_with: Exception | None = None
        self.status_override: int | None = None

    def __call__(self, url, params=None):
        self.calls.append((url, params or {}))
        if self.fail_with:
            raise self.fail_with
        if self.status_override:
            return self.status_override, None
        if url.startswith(protondb.STEAM_SEARCH_URL):
            term = protondb.normalize_title(params["term"])
            items = [i for i in self.store if term in protondb.normalize_title(i["name"])]
            return 200, {"total": len(items), "items": items}
        appid = url.rsplit("/", 1)[1].removesuffix(".json")
        if appid in self.summaries:
            return 200, self.summaries[appid]
        return 404, None

    def urls(self, prefix: str) -> list[str]:
        return [u for u, _p in self.calls if u.startswith(prefix)]


class RatingsTests(unittest.TestCase):
    def setUp(self):
        self.web = FakeWeb()
        self.now = 1_700_000_000.0
        self.cache = TMP / "protondb-cache.json"
        self.cache.unlink(missing_ok=True)
        self.results: list[tuple[str, object, bool]] = []
        self.ratings = self.make_ratings()
        shared.schema.set_boolean("protondb", True)
        self.addCleanup(shared.schema.reset, "protondb")
        self.addCleanup(self.ratings.shutdown)

    def make_ratings(self) -> ProtonDBRatings:
        return ProtonDBRatings(
            cache_path=self.cache,
            http_get=self.web,
            dispatch=lambda fn, *args: fn(*args),  # no main loop in tests
            clock=lambda: self.now,
            workers=1,
        )

    def ask(self, game) -> None:
        """request() and wait for the worker (the answer is recorded)"""
        self.results.clear()
        self.ratings.request(game, lambda g, r, ok: self.results.append((g.name, r, ok)))
        self.ratings._executor.submit(lambda: None).result(timeout=5)

    # Titles

    def test_titles_are_normalized(self):
        for a, b in (
            ("Street Fighter™ 6", "street fighter 6"),
            ("Pokémon Red", "pokemon red"),
            ("The Witcher® 3: Wild Hunt", "the witcher 3 wild hunt"),
            ("  Hades  ", "hades"),
        ):
            self.assertEqual(protondb.normalize_title(a), b)

    # Steam games

    def test_steam_games_use_their_own_app_id(self):
        self.ask(make_game("steam", "Elden Ring", "steam_1245620"))
        self.assertEqual(self.results, [("Elden Ring", Rating("1245620", "gold", 2107), True)])
        self.assertEqual(self.web.urls(protondb.STEAM_SEARCH_URL), [])  # no title lookup

    def test_a_game_with_no_reports_has_no_rating(self):
        self.ask(make_game("steam", "Unknown", "steam_424242"))
        self.assertEqual(self.results, [("Unknown", None, True)])

    def test_unknown_tiers_are_ignored(self):
        self.ask(make_game("steam", "Odd", "steam_999"))
        self.assertEqual(self.results, [("Odd", None, True)])

    def test_url_and_names(self):
        rating = Rating("1245620", "gold", 2107)
        self.assertEqual(rating.url, "https://www.protondb.com/app/1245620")
        self.assertEqual(rating.name, "Gold")

    # Other platforms: the Steam id comes from the exact title

    def test_other_platforms_are_found_by_exact_title(self):
        self.ask(make_game("lutris_wine", "ELDEN RING™"))
        self.assertEqual(self.results[0][1], Rating("1245620", "gold", 2107))

    def test_a_title_that_only_contains_the_name_is_not_a_match(self):
        self.ask(make_game("faugus", "Elden Ring Nightreign Demo"))
        self.assertEqual(self.results, [("Elden Ring Nightreign Demo", None, True)])
        self.assertEqual(self.web.urls(protondb.SUMMARY_URL.split("{")[0]), [])

    def test_only_apps_count_not_dlc(self):
        self.ask(make_game("heroic_gog", "Soundtrack"))
        self.assertEqual(self.results[0][1], None)

    def test_hades_on_gog_is_found(self):
        self.web.summaries["1145360"] = {"tier": "platinum", "total": 5000}
        self.ask(make_game("heroic_gog", "Hades"))
        self.assertEqual(self.results[0][1], Rating("1145360", "platinum", 5000))

    def test_retroarch_games_are_not_looked_up(self):
        self.ask(make_game("retroarch", "Super Mario World"))
        self.assertEqual(self.results, [])
        self.assertEqual(self.web.calls, [])

    # Cache

    def test_answers_are_cached_and_used_without_the_network(self):
        game = make_game("lutris_wine", "Hades")
        self.web.summaries["1145360"] = {"tier": "gold", "total": 10}
        self.ask(game)
        calls = len(self.web.calls)
        self.assertEqual(calls, 2)  # one title search, one summary

        self.results.clear()
        self.ratings.request(game, lambda g, r, ok: self.results.append((r, ok)))
        self.assertEqual(self.results, [(Rating("1145360", "gold", 10), True)])  # at once
        self.assertEqual(len(self.web.calls), calls)

    def test_the_cache_survives_a_restart(self):
        self.web.summaries["1145360"] = {"tier": "silver", "total": 7}
        self.ask(make_game("faugus", "Hades"))
        self.ratings.save()
        self.assertTrue(self.cache.is_file())

        again = self.make_ratings()
        self.addCleanup(again.shutdown)
        known, rating = again.cached(make_game("faugus", "Hades"))
        self.assertEqual((known, rating), (True, Rating("1145360", "silver", 7)))

    def test_ratings_expire_after_a_week(self):
        game = make_game("steam", "Elden Ring", "steam_1245620")
        self.ask(game)
        self.assertEqual(self.ratings.cached(game)[0], True)
        self.now += protondb.FOUND_TTL - 1
        self.assertEqual(self.ratings.cached(game)[0], True)
        self.now += 2
        self.assertEqual(self.ratings.cached(game)[0], False)

    def test_games_without_reports_are_asked_again_after_a_day(self):
        game = make_game("steam", "Unknown", "steam_424242")
        self.ask(game)
        self.assertEqual(self.ratings.cached(game), (True, None))
        self.now += protondb.NOT_FOUND_TTL + 1
        self.assertEqual(self.ratings.cached(game)[0], False)

    def test_a_broken_cache_file_is_ignored(self):
        for content in ("{not json", "[1, 2]", '{"apps": 5, "names": []}', ""):
            self.cache.write_text(content)
            ratings = self.make_ratings()
            self.addCleanup(ratings.shutdown)
            self.assertEqual(ratings.cached(make_game("steam", "X", "steam_1")), (False, None))

    def test_garbage_entries_in_the_cache_are_ignored(self):
        self.cache.write_text(
            json.dumps({"apps": {"1": "oops", "2": {"t": "x"}, "3": {"t": self.now, "tier": "nope"}},
                        "names": {}})
        )
        ratings = self.make_ratings()
        self.addCleanup(ratings.shutdown)
        self.assertEqual(ratings.cached(make_game("steam", "A", "steam_1")), (False, None))
        self.assertEqual(ratings.cached(make_game("steam", "B", "steam_2")), (False, None))
        self.assertEqual(ratings.cached(make_game("steam", "C", "steam_3")), (True, None))

    # Failures

    def test_a_failing_network_is_not_remembered(self):
        self.web.fail_with = requests.ConnectionError("offline")
        game = make_game("steam", "Elden Ring", "steam_1245620")
        self.ask(game)
        self.assertEqual(self.results, [("Elden Ring", None, False)])
        self.assertEqual(self.ratings.cached(game), (False, None))

        self.web.fail_with = None
        self.ask(game)
        self.assertEqual(self.results[0][1], Rating("1245620", "gold", 2107))

    def test_server_errors_are_failures_too(self):
        self.web.status_override = 503
        self.ask(make_game("steam", "Elden Ring", "steam_1245620"))
        self.assertEqual(self.results[0][2], False)

    def test_invalid_json_is_a_failure(self):
        self.web.fail_with = ValueError("bad json")
        self.ask(make_game("steam", "Elden Ring", "steam_1245620"))
        self.assertEqual(self.results[0][2], False)

    def test_repeated_failures_pause_the_requests(self):
        self.web.fail_with = requests.Timeout("slow")
        for i in range(protondb.FAILURES_BEFORE_PAUSE):
            self.ask(make_game("steam", f"G{i}", f"steam_{100 + i}"))
        self.assertTrue(self.ratings.paused)

        calls = len(self.web.calls)
        self.ask(make_game("steam", "Next", "steam_200"))
        self.assertEqual(len(self.web.calls), calls)  # not even tried
        self.assertEqual(self.results, [])

        self.now += protondb.PAUSE_SECONDS + 1
        self.assertFalse(self.ratings.paused)

    def test_a_success_resets_the_failure_count(self):
        self.web.fail_with = requests.Timeout("slow")
        for i in range(protondb.FAILURES_BEFORE_PAUSE - 1):
            self.ask(make_game("steam", f"G{i}", f"steam_{100 + i}"))
        self.web.fail_with = None
        self.ask(make_game("steam", "Elden Ring", "steam_1245620"))
        self.web.fail_with = requests.Timeout("slow")
        self.ask(make_game("steam", "Other", "steam_300"))
        self.assertFalse(self.ratings.paused)

    # Setting

    def test_nothing_is_asked_when_the_setting_is_off(self):
        shared.schema.set_boolean("protondb", False)
        self.ask(make_game("steam", "Elden Ring", "steam_1245620"))
        self.assertEqual(self.results, [])
        self.assertEqual(self.web.calls, [])

    def test_the_same_title_is_only_asked_once_at_a_time(self):
        import threading

        gate = threading.Event()
        original = self.web.__call__

        def slow(url, params=None):
            gate.wait(5)
            return original(url, params)

        self.ratings._http_get = slow
        a = make_game("faugus", "Hades", "faugus_a")
        b = make_game("lutris_wine", "Hades", "lutris_b")
        answers = []
        self.ratings.request(a, lambda g, r, ok: answers.append(g.game_id))
        self.ratings.request(b, lambda g, r, ok: answers.append(g.game_id))
        gate.set()
        self.ratings._executor.submit(lambda: None).result(timeout=5)
        self.assertEqual(sorted(answers), ["faugus_a", "lutris_b"])
        self.assertEqual(len(self.web.urls(protondb.STEAM_SEARCH_URL)), 1)


class BadgeTests(unittest.TestCase):
    def setUp(self):
        Adw.init()
        from cartridges.game_widget import GameWidget

        self.card = GameWidget()
        shared.schema.set_boolean("protondb", True)
        self.addCleanup(shared.schema.reset, "protondb")
        # Never ask the network from a widget test
        patcher = mock.patch.object(Game, "request_protondb", lambda self: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_badge_follows_the_bound_game(self):
        rated = make_game("steam", "Elden Ring", "steam_1245620")
        rated.protondb = Rating("1245620", "gold", 2107)
        unrated = make_game("steam", "Nothing", "steam_1")

        button = self.card.protondb_button
        self.assertFalse(button.get_visible())

        self.card.bind(rated)
        self.assertTrue(button.get_visible())
        self.assertEqual(button.get_label(), "GOLD")
        self.assertTrue(button.has_css_class("protondb-gold"))
        self.assertEqual(button.get_tooltip_text(), "ProtonDB: Gold · 2107 reports")

        self.card.unbind()
        self.assertFalse(button.get_visible())

        self.card.bind(unrated)  # recycled card for a game with no rating
        self.assertFalse(button.get_visible())

        rated.protondb = Rating("1", "borked", 0)
        self.card.unbind()
        self.card.bind(rated)
        self.assertTrue(button.has_css_class("protondb-borked"))
        self.assertFalse(button.has_css_class("protondb-gold"))
        self.assertEqual(button.get_tooltip_text(), "ProtonDB: Borked")

    def test_the_answer_updates_the_card_that_shows_the_game(self):
        game = make_game("steam", "Elden Ring", "steam_1245620")
        self.card.bind(game)
        self.assertFalse(self.card.protondb_button.get_visible())

        old_win = getattr(shared, "win", None)
        self.addCleanup(setattr, shared, "win", old_win)
        shared.win = mock.Mock()
        game.protondb_ready(game, Rating("1245620", "platinum", 5), True)
        self.assertTrue(self.card.protondb_button.get_visible())
        self.assertTrue(game.protondb_checked)

        # A failed lookup is tried again the next time the card is bound
        other = make_game("steam", "Other", "steam_2")
        other.protondb_ready(other, None, False)
        self.assertFalse(other.protondb_checked)

    def test_the_setting_hides_the_badge(self):
        game = make_game("steam", "Elden Ring", "steam_1245620")
        game.protondb = Rating("1245620", "gold", 1)
        self.card.bind(game)
        self.assertTrue(self.card.protondb_button.get_visible())
        shared.schema.set_boolean("protondb", False)
        self.card.update_protondb()
        self.assertFalse(self.card.protondb_button.get_visible())

    def test_the_badge_opens_the_page(self):
        game = make_game("steam", "Elden Ring", "steam_1245620")
        game.protondb = Rating("1245620", "gold", 1)
        self.card.bind(game)
        with mock.patch("gi.repository.Gio.AppInfo.launch_default_for_uri") as launch:
            self.card.protondb_button.emit("clicked")
        launch.assert_called_once_with("https://www.protondb.com/app/1245620")


if __name__ == "__main__":
    shutil.rmtree(TMP / "protondb-cache.json", ignore_errors=True)
    unittest.main()
