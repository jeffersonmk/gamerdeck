> [!NOTE]
> Gamerdeck is a fork of [Cartridges](https://apps.gnome.org/Cartridges/) by kramo, which is no longer actively maintained upstream. This fork keeps the application id and the data folders of Cartridges, so an existing library and its settings keep working.

<div align="center">
  <img src="data/icons/hicolor/scalable/apps/page.kramo.Cartridges.svg" width="128" height="128">

  # Gamerdeck

  A GTK4 + Libadwaita game launcher, for big libraries and for the couch

  <img src="data/screenshots/1.png">
</div>

# The Project

Gamerdeck is an easy-to-use, elegant game launcher written in Python using GTK4 and Libadwaita. It is a fork of Cartridges, made to run well with big libraries and with a controller.

## What is different from Cartridges

| Area | What Gamerdeck does |
|---|---|
| Speed and memory | A virtualized grid, an O(1) game index, background cover work and a bounded cover cache: a library of 2000 games opens in 0.7 s using 189 MB instead of 4.0 s and 682 MB ([numbers](#performance)) |
| Robustness | Atomic JSON writes, corrupt game files and covers are skipped instead of stopping the library, no GTK calls from worker threads, no temporary file leaks |
| Only games | The importers skip launchers (Steam, Epic, Heroic...), tools (Proton, Goverlay, ProtonUp-Qt...) and emulators |
| More sources | [Faugus Launcher](https://github.com/Faugus/faugus-launcher), and a Lutris importer that no longer duplicates games or loses the hidden state |
| Platform badge | Each cover shows where the game came from; clicking it opens that app |
| ProtonDB | The rating of each game on its cover and on its page |
| Vitrine layout | A banner with the game in focus and a "Continue Playing" row, in the colors of the system theme |
| Controller | The whole app works with an Xbox or PlayStation controller, with a legend of what each button does |

## Features

- Manually adding and editing games
- Importing games from various sources (only games: launchers like Steam or Heroic, tools like Proton, Goverlay or ProtonUp-Qt, and emulators are skipped):
  - Steam
  - Lutris
  - Faugus Launcher
  - Heroic
  - Bottles
  - itch
  - Legendary
  - RetroArch
  - Flatpak
  - Desktop Entries
- Filtering games by source
- A badge on each cover with the platform the game came from (Steam, Epic, GOG, Amazon, Lutris, Faugus...); clicking it opens that app (the page of the game on Steam). The game menu has "Open Steam" (or the right app) too
- ProtonDB ratings (Platinum, Gold, Silver, Bronze, Borked) on each cover and on the details page, for Steam games and for games of the other platforms whose title matches a Steam game exactly. Ratings are cached for a week and can be turned off in the preferences (the Steam ID or the title of each game is sent to Steam and ProtonDB)
- A banner on top of the library and a row of the games played last
- Searching and sorting by title, date added and last played
- Hiding games
- Automatically downloading cover art from [SteamGridDB](https://www.steamgriddb.com/)
- Searching for games on various databases
- Animated covers
- A search provider for GNOME
- Navigating with an Xbox or PlayStation controller

### Only games

Desktop entries are not imported when their categories say they are not games (Network, Utility, Package Manager, Emulator...), when they are a known launcher, store, tool or emulator, or when they are this app itself. Steam's Proton versions and runtimes are not imported either. Wrappers such as `gamemoderun` or `mangohud` are looked through, so a game started through them is still a game. Games added by hand are never filtered.

### Platform badge

The platform comes from the source of the game: Steam, Lutris, Faugus, Bottles, itch and RetroArch open their own app; Heroic shows the store of the game (Epic, GOG or Amazon) and opens Heroic. Games added by hand, from desktop entries, Flatpak or Legendary have no badge.

### Banner and button legend

The top of the library shows a banner with the game that has the focus (or the pointer): its cover, developer, last played date, the platform it came from (click to open the app), its ProtonDB rating, and **Play** and **Details** buttons. Below it, **Continue Playing** lists the games played last. The banner follows the system accent color, in light and dark mode, and gives way to the search results while you search. Windows shorter than 860 px hide the recent games row, and narrow ones (below 565 px) use a compact banner.

At the bottom of the window, a legend shows what each controller button does right now (library, sidebar, card menu, dialog, search, details page), drawn with the symbols of the controller you are using: A B X Y for Xbox, ✕ ○ □ △ for PlayStation. In the preferences, **Controller** lets you show it only when a controller is connected (the default), always, or never, and choose the Xbox or PlayStation symbols instead of following the controller in use.

## Controller support

Xbox and PlayStation controllers (wired or Bluetooth) can navigate the whole app through [libmanette](https://gnome.pages.gitlab.gnome.org/libmanette/). The buttons are named by position, so the same layout works on both:

| Xbox | PlayStation | Action |
|---|---|---|
| D-pad or left stick | D-pad or left stick | Move the focus (hold to repeat) |
| A | ✕ | Launch the game, or press the focused button |
| B | ○ | Close the menu or dialog, leave the search, go back |
| X | □ | Open the menu of the focused game (Details, Edit, Hide, Remove, Open the app it came from) |
| Y | △ | Search |
| LB / RB | L1 / R1 | Previous / next source in the sidebar |
| Menu | Options | Show or hide the sidebar |

The controller only works while the app window has the focus, so it never reacts while you are playing. If libmanette is not installed, the app works as before. The Flatpak needs `--device=input` to see controllers.

To try it without a controller, `tests/gamepad_uinput.py` creates virtual Xbox and DualSense controllers (see the file for how to run it).

## Performance

Measured with `tests/bench` on a synthetic library of 2000 games (1600 with a cover), with a release build, in a headless environment (median of 3 to 5 runs).

| Metric, 2000 games | Cartridges | Gamerdeck |
|---|---:|---:|
| Window ready | 4.00 s | **0.71 s** |
| All visible covers ready | 5.29 s | **0.80 s** |
| Memory after startup | 682 MB | **189 MB** |
| Card widgets alive | 2000 | **129** |
| Search, one keystroke | 795 ms | **23 ms** |
| Longest UI freeze while importing 300 games | 2608 ms | **138 ms** |
| Temporary files left behind by 300 imports | 600 | **0** |

The first round of fixes also cut the import of 300 Steam games from 4.70 s to 1.85 s. On a real display (Hyprland, same library), the grid brought the first frame from 5.0 s to 1.5 s and the memory from about 890 MB to about 250 MB. A library of 100 games is as fast or faster in every metric.

Memory stays flat in long use: browsing the whole library three times gives 233, 232 and 229 MB, and opening 1000 details pages gives 228 to 241 MB.

What made the difference, by impact:

1. **Algorithms.** Looking a game up scanned the whole library (O(n²) loading), and every game of the search called a function that scanned the library again (795 ms per keystroke). Both are now O(1) or computed once.
2. **The main thread.** Cover downloads (up to 3 retries with a 3 s sleep) and image conversions ran in the UI thread, freezing it up to 2.6 s during an import. They run in workers now, and widgets are only touched on the main thread (0 widgets created off it, down from 50).
3. **A virtualized grid.** The `FlowBox` made one widget and one texture per game. A `Gtk.GridView` over a sorted and filtered `Gio.ListStore` makes cards only for the visible rows and recycles them, and covers are decoded on demand.
4. **A bounded cover cache.** Decoded covers that are off screen are freed (least recently shown first) above 64 MB.

The language was never the bottleneck, so a rewrite in Rust was evaluated and rejected: every measured problem was algorithmic or a threading mistake and was fixed in Python, and the remaining cost (a widget and a texture per game) would be the same in any language.

Not done or not measured: the Flatpak still asks for `--filesystem=host` (read and write; `host:ro` is recommended but was not tested), and cold start (it needs root to drop the caches), the Flatpak build and real GPU rendering were not measured. `tests/bench/README.md` has the procedures.

## Development

The tests need an installed build. From the source folder:

```sh
meson setup _build --prefix="$PWD/_install" -Dprofile=release
meson install -C _build
python3 -m unittest discover -s tests -t .
```

- Set `GAMERDECK_PREFIX` to test another prefix.
- The tests that drive the real window (`tests/test_gamepad_ui.py`: controller navigation, banner, legend, symbol alignment) use `kwin_wayland` and `dbus-run-session` as a virtual screen, or `gtk4-broadwayd` and a Chromium binary in `GAMERDECK_BROWSER`. They are skipped when neither is available, and nothing opens on your screen.
- `tests/bench/bench.py` is the benchmark (see its README).
- `tests/test_sources.py` and `tests/test_only_games.py` cover the importers, and `tests/test_protondb.py` the ProtonDB lookup, with a fake web: no test uses the network.

Blueprint files are not recompiled by `ninja` after an edit: run `rm -rf _build` and set it up again.

# Installation

Gamerdeck is installed as a **Flatpak**. It has its own id, `io.github.jeffersonmk.Gamerdeck`, so it never mixes with Cartridges: you can have both, and each one keeps its own library and settings. Gamerdeck has no packaged releases yet, so first you get the file `Gamerdeck.flatpak` (step 1).

You need Flatpak with the Flathub repository (most distributions have it; see [flatpak.org/setup](https://flatpak.org/setup/)). Nothing here needs `sudo`: everything is installed for your user only.

## 1. Get the `Gamerdeck.flatpak` file

Build it from the source code. The first time it downloads about 1 GB (the GNOME SDK, once) and takes a few minutes; the next builds are much faster.

```sh
git clone https://github.com/jeffersonmk/gamerdeck.git
cd gamerdeck
flatpak install --user flathub org.flatpak.Builder   # only the first time
scripts/build-flatpak.sh
```

This creates `Gamerdeck.flatpak` in the project folder (about 2 MB). The file can be copied to another computer with Flatpak.

## 2. Install

```sh
scripts/install-flatpak.sh
```

(Without the project folder, `flatpak install --user Gamerdeck.flatpak` does the same.)

Gamerdeck appears in the applications menu, with its icon. Flatpak creates that shortcut by itself. You can also start it from a terminal:

```sh
flatpak run io.github.jeffersonmk.Gamerdeck
```

### Bring your library from Cartridges (optional)

Gamerdeck starts with an empty library. To keep the one you already have from Cartridges, close both apps and copy its data folder into the one of Gamerdeck:

```sh
mkdir -p ~/.var/app/io.github.jeffersonmk.Gamerdeck/data/cartridges
cp -a ~/.local/share/cartridges/. ~/.var/app/io.github.jeffersonmk.Gamerdeck/data/cartridges/
```

If you used the Flatpak of Cartridges, copy from `~/.var/app/page.kramo.Cartridges/data/cartridges/.` instead. The games and covers come along; the settings (like the SteamGridDB key) do not, so set them again in the preferences. The copy leaves the original untouched.

## Update

Get the new `Gamerdeck.flatpak` (`git pull` and `scripts/build-flatpak.sh` again, or the file someone gave you) and run the same install command:

```sh
git pull
scripts/build-flatpak.sh
scripts/install-flatpak.sh
```

Your library and settings stay. If the script says that this exact version is already installed, you already have it.

## Uninstall

```sh
scripts/uninstall-flatpak.sh
```

It removes the app and the shortcut, then asks if you also want to delete the data Gamerdeck saved for itself (library, covers, settings and logs, in `~/.var/app/io.github.jeffersonmk.Gamerdeck`). To skip the question, use `--keep-data` or `--delete-data`. Your games and the data of Steam, Lutris and the other launchers are never touched. Without the script:

```sh
flatpak uninstall --user --delete-data io.github.jeffersonmk.Gamerdeck
```

To also free the space used by what building needed (about 2.7 GB) and by runtimes nobody else uses:

```sh
flatpak uninstall --user org.flatpak.Builder org.gnome.Sdk//50   # only if you will not build again
flatpak uninstall --unused
rm -r .flatpak-builder .flatpak-repo .flatpak-build               # inside the project folder
```

## What the Flatpak can access

- **Your files** (`--filesystem=host`): to read the libraries of Steam, Lutris, Heroic and the others, and to find the games you add.
- **The network:** to download covers and ProtonDB ratings.
- **The input devices:** to read your controller.
- **The Flatpak service of the host** (`--talk-name=org.freedesktop.Flatpak`): to start your games outside the sandbox.

You can see and change these permissions with [Flatseal](https://flathub.org/apps/com.github.tchx84.Flatseal).

## Without Flatpak (for developers)

```sh
meson setup build --prefix="$HOME/.local" -Dapp_id=io.github.jeffersonmk.Gamerdeck
ninja -C build install
```

`-Dapp_id` gives it the same id as the Flatpak instead of the one of Cartridges, so it has its own launcher, icon and settings. Without Flatpak the library is the same folder Cartridges uses, `~/.local/share/cartridges`. It needs the requirements below. To remove it, delete the files listed in `build/meson-logs/install-log.txt` (Meson has no `uninstall`).

**Requirements:** Meson and Ninja, [blueprint-compiler](https://gitlab.gnome.org/jwestman/blueprint-compiler), GTK 4 ≥ 4.15, libadwaita ≥ 1.6, PyGObject, PyYAML, requests and Pillow. Optional: libmanette (controller support) and pycairo (the PlayStation symbols; without it the app uses font symbols).

See [CONTRIBUTING.md](CONTRIBUTING.md#building) for GNOME Builder, Windows and macOS. The Windows and macOS installers are built by the workflows in `.github/workflows`, which have not been run for this fork.

# Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

Thanks to [Weblate](https://weblate.org/) for hosting the translations of Cartridges!

# Code of Conduct

The project follows the [GNOME Code of Conduct](https://conduct.gnome.org/). See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

Cartridges' contributors stand with Palestine, Ukraine and all other victims of imperialism and war, and believe trans rights are human rights. If this bothers you, this is probably not the best project for you to contribute to.

# Credits and license

Gamerdeck is based on [Cartridges](https://apps.gnome.org/Cartridges/) by kramo and its contributors, and is licensed under the GPL-3.0-or-later like it (see [LICENSE](LICENSE)). The original author accepts donations through [GitHub Sponsors](https://github.com/sponsors/kra-mo) and [Liberapay](https://liberapay.com/kramo).
