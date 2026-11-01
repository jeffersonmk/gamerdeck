# protondb.py
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

"""How well games run on Linux, according to ProtonDB

ProtonDB rates games by their Steam app id. Steam games already have one; for
the others the id is found by title on the Steam store, and only an exact
title match counts (a wrong rating is worse than none). Answers are kept for a
while in the cache directory, and a failing network is not asked again for a
few minutes.
"""

import logging
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import requests
from gi.repository import Gio, GLib, Gtk

from cartridges import shared
from cartridges.game import Game
from cartridges.utils.json_file import read_json, write_json_atomic

SUMMARY_URL = "https://www.protondb.com/api/v1/reports/summaries/{appid}.json"
PAGE_URL = "https://www.protondb.com/app/{appid}"
STEAM_SEARCH_URL = "https://store.steampowered.com/api/storesearch/"

TIERS = ("platinum", "gold", "silver", "bronze", "borked", "pending")
TIER_NAMES = {
    "platinum": _("Platinum"),
    "gold": _("Gold"),
    "silver": _("Silver"),
    "bronze": _("Bronze"),
    "borked": _("Borked"),
    "pending": _("Pending"),
}

FOUND_TTL = 7 * 24 * 3600  # A rating changes slowly
NOT_FOUND_TTL = 24 * 3600  # Games nobody reported yet may get reports
FAILURES_BEFORE_PAUSE = 5
PAUSE_SECONDS = 600
REQUEST_TIMEOUT = 6

# Sources whose games are not PC games that Proton could run
NOT_PC_SOURCES = frozenset({"retroarch"})


@dataclass(frozen=True)
class Rating:
    appid: str
    tier: str
    total: int = 0

    @property
    def name(self) -> str:
        return TIER_NAMES[self.tier]

    @property
    def url(self) -> str:
        return PAGE_URL.format(appid=self.appid)


def normalize_title(title: str) -> str:
    """Letters and digits only, lowercase, no accents: "Pokémon™ Red" -> "pokemon red" """
    # NFD, not NFKD: NFKD turns the trademark sign into the letters "TM"
    title = unicodedata.normalize("NFD", title).casefold()
    title = "".join(c for c in title if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", title).strip()


def steam_appid(game: Game) -> Optional[str]:
    """The Steam app id of a game imported from Steam"""
    if game.base_source != "steam":
        return None
    appid = game.game_id.removeprefix("steam_")
    return appid if appid.isdigit() else None


def default_http_get(url: str, params: Optional[dict] = None) -> tuple[int, Any]:
    response = requests.get(
        url,
        params=params,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": f"GameDeck/{shared.VERSION}"},
    )
    return response.status_code, (response.json() if response.status_code == 200 else None)


def show_rating(button: Gtk.Button, rating: Optional[Rating], prefix: str = "") -> None:
    """Style a button as the rating badge of a game, or hide it"""
    for tier in TIERS:
        button.remove_css_class(f"protondb-{tier}")
    button.set_visible(rating is not None)
    if rating is None:
        return

    button.add_css_class(f"protondb-{rating.tier}")
    button.set_label(prefix + (rating.name if prefix else rating.name.upper()))
    tooltip = _("ProtonDB: {}").format(rating.name)
    if rating.total:
        tooltip += " · " + ngettext("{} report", "{} reports", rating.total).format(
            rating.total
        )
    button.set_tooltip_text(tooltip)


def open_page(rating: Rating) -> None:
    Gio.AppInfo.launch_default_for_uri(rating.url)


def run_on_main_thread(function: Callable, *args: Any) -> None:
    # The default idle priority is starved for seconds by redraws
    GLib.idle_add(function, *args, priority=GLib.PRIORITY_DEFAULT)


class TransientError(Exception):
    """The network or the server failed: ask again later, do not remember it"""


class ProtonDBRatings:
    """Finds and remembers ProtonDB ratings; `request()` is for the main thread"""

    def __init__(
        self,
        cache_path: Optional[Path] = None,
        http_get: Callable[..., tuple[int, Any]] = default_http_get,
        dispatch: Callable[..., None] = run_on_main_thread,
        clock: Callable[[], float] = time.time,
        workers: int = 3,
    ) -> None:
        self._cache_path = cache_path
        self._http_get = http_get
        self._dispatch = dispatch
        self._clock = clock
        self._executor = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="protondb"
        )
        self._lock = threading.Lock()
        self._cache: Optional[dict] = None
        self._dirty = False
        self._save_queued = False
        self._in_flight: dict[str, list] = {}
        self._failures = 0
        self._paused_until = 0.0

    # Cache

    @property
    def cache_path(self) -> Path:
        return self._cache_path or shared.cache_dir / "cartridges" / "protondb.json"

    def _load(self) -> dict:
        if self._cache is None:
            cache: Any = {}
            try:
                cache = read_json(self.cache_path)
            except (OSError, ValueError):
                pass
            if not isinstance(cache, dict):
                cache = {}
            for key in ("apps", "names"):
                if not isinstance(cache.get(key), dict):
                    cache[key] = {}
            self._cache = cache
        return self._cache

    def save(self) -> None:
        with self._lock:
            if not self._dirty:
                return
            self._dirty = False
            try:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                write_json_atomic(self.cache_path, self._load())
            except OSError as error:
                logging.warning("Couldn't save the ProtonDB cache: %s", error)

    def _remember(self, section: str, key: str, value: dict) -> None:
        with self._lock:
            self._load()[section][key] = {"t": self._clock(), **value}
            self._dirty = True
        self._queue_save()

    def _queue_save(self) -> None:
        """Write the cache a few seconds after the last answer, not on each one"""
        if self._save_queued or self._cache_path is not None:
            return
        self._save_queued = True

        def flush() -> bool:
            self._save_queued = False
            self.save()
            return False

        GLib.timeout_add_seconds(5, flush)

    def _fresh(self, entry: Any, ttl_found: bool) -> bool:
        return (
            isinstance(entry, dict)
            and isinstance(entry.get("t"), (int, float))
            and self._clock() - entry["t"] < (FOUND_TTL if ttl_found else NOT_FOUND_TTL)
        )

    def _cached_appid(self, game: Game) -> tuple[bool, Optional[str]]:
        """(known, appid) for a game; known is False when the title was never looked up"""
        if appid := steam_appid(game):
            return True, appid
        entry = self._load()["names"].get(normalize_title(game.name))
        if not isinstance(entry, dict):
            return False, None
        if self._fresh(entry, bool(entry.get("appid"))):
            appid = entry.get("appid")
            return True, appid if isinstance(appid, str) else None
        return False, None

    def _cached_rating(self, appid: str) -> tuple[bool, Optional[Rating]]:
        """(known, rating) for an app id; known is False when it has to be asked"""
        entry = self._load()["apps"].get(appid)
        if not isinstance(entry, dict) or not self._fresh(entry, bool(entry.get("tier"))):
            return False, None
        tier = entry.get("tier")
        if tier not in TIERS:
            return True, None
        total = entry.get("total")
        return True, Rating(appid, tier, total if isinstance(total, int) else 0)

    def cached(self, game: Game) -> tuple[bool, Optional[Rating]]:
        """What is known without the network: (known, rating)"""
        with self._lock:
            known, appid = self._cached_appid(game)
            if not known:
                return False, None
            if appid is None:
                return True, None
            return self._cached_rating(appid)

    # Network (worker threads)

    def _get(self, url: str, params: Optional[dict] = None) -> Any:
        """The JSON of a page, None when it does not exist"""
        try:
            status, data = self._http_get(url, params=params)
        except (requests.RequestException, ValueError) as error:
            raise TransientError(str(error)) from error
        if status == 404:
            return None
        if status != 200 or data is None:
            raise TransientError(f"HTTP {status}")
        return data

    def find_appid(self, game: Game) -> Optional[str]:
        """The Steam app id of a game, by exact title; None if there is none"""
        with self._lock:
            known, appid = self._cached_appid(game)
        if known:
            return appid

        wanted = normalize_title(game.name)
        data = self._get(
            STEAM_SEARCH_URL, {"term": game.name, "cc": "us", "l": "en"}
        )
        appid = None
        for item in (data or {}).get("items", []):
            if (
                isinstance(item, dict)
                and item.get("type") == "app"
                and isinstance(item.get("name"), str)
                and normalize_title(item["name"]) == wanted
            ):
                appid = str(item.get("id"))
                break
        self._remember("names", wanted, {"appid": appid})
        return appid

    def fetch_rating(self, appid: str) -> Optional[Rating]:
        with self._lock:
            known, rating = self._cached_rating(appid)
        if known:
            return rating

        data = self._get(SUMMARY_URL.format(appid=appid))
        if not isinstance(data, dict) or data.get("tier") not in TIERS:
            self._remember("apps", appid, {"tier": None})
            return None
        total = data.get("total")
        total = total if isinstance(total, int) else 0
        self._remember("apps", appid, {"tier": data["tier"], "total": total})
        return Rating(appid, data["tier"], total)

    def fetch(self, game: Game) -> Optional[Rating]:
        """The rating of a game, asking the network if needed (blocking)"""
        appid = self.find_appid(game)
        return self.fetch_rating(appid) if appid else None

    # Requests (main thread)

    @staticmethod
    def enabled(game: Game) -> bool:
        return (
            shared.schema.get_boolean("protondb")
            and game.base_source not in NOT_PC_SOURCES
        )

    @property
    def paused(self) -> bool:
        return self._clock() < self._paused_until

    def request(self, game: Game, callback: Callable[[Game, Optional[Rating], bool], None]) -> None:
        """Call `callback(game, rating, ok)` on the main thread when the rating is known

        `ok` is False when the network failed: ask again later. Answers that
        are already in the cache come back at once.
        """
        if not self.enabled(game):
            return

        known, rating = self.cached(game)
        if known:
            callback(game, rating, True)
            return
        if self.paused:
            return

        key = normalize_title(game.name) if not steam_appid(game) else f"steam_{steam_appid(game)}"
        with self._lock:
            waiting = self._in_flight.setdefault(key, [])
            waiting.append((game, callback))
            if len(waiting) > 1:
                return  # Same title already on its way
        self._executor.submit(self._work, game, key)

    def _work(self, game: Game, key: str) -> None:
        rating, ok = None, True
        try:
            rating = self.fetch(game)
            self._failures = 0
        except TransientError as error:
            ok = False
            self._failures += 1
            logging.debug("ProtonDB failed for %s: %s", game.name, error)
            if self._failures >= FAILURES_BEFORE_PAUSE:
                self._paused_until = self._clock() + PAUSE_SECONDS
                self._failures = 0
                logging.info("ProtonDB is not answering, pausing for a while")
        except Exception:  # pylint: disable=broad-exception-caught
            ok = False
            logging.exception("Unexpected ProtonDB error for %s", game.name)

        with self._lock:
            waiting = self._in_flight.pop(key, [])
        for waiting_game, callback in waiting:
            self._dispatch(callback, waiting_game, rating, ok)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
        self.save()


ratings = ProtonDBRatings()
