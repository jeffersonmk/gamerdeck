"""Recognize common emulator commands in custom desktop game launchers."""

from dataclasses import dataclass
from pathlib import PurePath
import shlex
from typing import Optional


@dataclass(frozen=True)
class Emulator:
    """An emulator identified in a desktop entry's Exec command."""

    id: str
    name: str
    console: str
    command: str
    flatpak_id: Optional[str] = None


# id, label, console id, preferred binary, optional Flatpak application ID
_EMULATORS = {
    "pcsx2": Emulator("pcsx2", "PCSX2", "ps2", "pcsx2-qt", "net.pcsx2.PCSX2"),
    "dolphin": Emulator("dolphin", "Dolphin", "gamecube", "dolphin", "org.DolphinEmu.dolphin-emu"),
    "rpcs3": Emulator("rpcs3", "RPCS3", "ps3", "rpcs3", "net.rpcs3.RPCS3"),
    "ppsspp": Emulator("ppsspp", "PPSSPP", "psp", "ppsspp", "org.ppsspp.PPSSPP"),
    "cemu": Emulator("cemu", "Cemu", "wiiu", "cemu", "info.cemu.Cemu"),
    "ryujinx": Emulator("ryujinx", "Ryujinx", "switch", "ryujinx", "org.ryujinx.Ryujinx"),
    "yuzu": Emulator("yuzu", "Yuzu", "switch", "yuzu", "org.yuzu_emu.yuzu"),
    "xemu": Emulator("xemu", "xemu", "xbox", "xemu", "app.xemu.xemu"),
    "duckstation": Emulator("duckstation", "DuckStation", "ps1", "duckstation", "org.duckstation.DuckStation"),
    "melonds": Emulator("melonds", "melonDS", "nds", "melonDS", "net.kuribo64.melonDS"),
    "citra": Emulator("citra", "Citra", "3ds", "citra-qt", "org.citra_emu.citra"),
    "mgba": Emulator("mgba", "mGBA", "gba", "mgba-qt", "io.mgba.mGBA"),
    "snes9x": Emulator("snes9x", "Snes9x", "snes", "snes9x-gtk", "com.snes9x.Snes9x"),
    "mesen": Emulator("mesen", "Mesen", "nes", "Mesen", "com.github.toyvan.mesen"),
}

_ALIASES = {
    "pcsx2-qt": "pcsx2", "pcsx2": "pcsx2",
    "dolphin-emu": "dolphin", "dolphin": "dolphin",
    "rpcs3": "rpcs3", "ppsspp": "ppsspp", "ppsspp-qt": "ppsspp",
    "cemu": "cemu", "ryujinx": "ryujinx", "yuzu": "yuzu", "xemu": "xemu",
    "duckstation": "duckstation", "melonds": "melonds", "melonds-qt": "melonds",
    "citra": "citra", "citra-qt": "citra", "mgba": "mgba", "mgba-qt": "mgba",
    "snes9x": "snes9x", "snes9x-gtk": "snes9x", "mesen": "mesen",
}

_FLATPAK_IDS = {emulator.flatpak_id: emulator.id for emulator in _EMULATORS.values() if emulator.flatpak_id}
_WRAPPERS = {"mangohud", "gamemoderun", "prime-run", "gamescope"}

CONSOLE_ICONS = {
    "ps1": "playstation.svg",
    "ps2": "playstation.svg",
    "ps3": "playstation.svg",
    "psp": "playstation.svg",
    "xbox": "xbox.svg",
    "dreamcast": "sega.svg",
    "megadrive": "sega.svg",
    "gamecube": "gamecube.png",
    "wiiu": "wiiu.png",
    "switch": "switch.png",
    "n64": "n64.png",
    "nds": "nds.png",
    "3ds": "3ds.png",
    "gba": "gba.png",
    "gbc": "gbc.png",
    "snes": "snes.png",
    "nes": "nes.png",
}


def get_emulator(emulator_id: Optional[str]) -> Optional[Emulator]:
    """Look up a recognized emulator by its persisted identifier."""
    return _EMULATORS.get(emulator_id or "")


def console_icon(console: Optional[str]) -> Optional[str]:
    """Return the bundled icon filename for a console, if available."""
    return CONSOLE_ICONS.get(console or "")


def detect_emulator(exec_line: str) -> Optional[Emulator]:
    """Find an emulator in a desktop Exec line, even behind common wrappers."""
    try:
        args = shlex.split(exec_line, posix=True)
    except ValueError:
        return None

    index = 0
    while index < len(args):
        token = args[index]
        if token == "env":
            index += 1
            while index < len(args) and ("=" in args[index] or args[index].startswith("-")):
                index += 1
            continue
        if PurePath(token).name in _WRAPPERS:
            index += 1
            continue
        if PurePath(token).name == "flatpak":
            try:
                run_index = args.index("run", index + 1)
            except ValueError:
                return None
            index = run_index + 1
            while index < len(args) and args[index].startswith("-"):
                index += 1
            if index >= len(args):
                return None
            emulator_id = _FLATPAK_IDS.get(args[index])
            return _EMULATORS.get(emulator_id) if emulator_id else None

        emulator_id = _ALIASES.get(PurePath(token).name.lower())
        if emulator_id:
            return _EMULATORS[emulator_id]
        # Stop at the first non-wrapper command; later args may be a ROM path.
        return None
    return None
