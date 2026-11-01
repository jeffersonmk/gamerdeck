"""Check the real libmanette path with virtual controllers (uinput).

Creates a virtual Xbox 360 pad and a virtual DualSense, presses their buttons
and checks that `GamepadController` turns what libmanette reports into the
right actions. No window or display is involved. Needs the python-evdev
module and write access to /dev/uinput (the `input` group on most distros):

    PATH=/usr/local/bin:/usr/bin /usr/bin/python3 -m tests.gamepad_uinput

While it runs, the desktop briefly sees two extra controllers.
"""

# pylint: disable=missing-function-docstring,import-outside-toplevel
import sys
import threading
import time
from types import SimpleNamespace

from tests.support import iterate_main_loop  # noqa: F401  (sets the environment)

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from cartridges import gamepad  # noqa: E402
from cartridges.gamepad import Action  # noqa: E402

try:
    from evdev import AbsInfo, UInput
    from evdev import ecodes as e
except ImportError:
    raise SystemExit("python-evdev is needed: run with /usr/bin/python3") from None

KEYS = [
    e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST, e.BTN_TL, e.BTN_TR,
    e.BTN_SELECT, e.BTN_START, e.BTN_MODE, e.BTN_THUMBL, e.BTN_THUMBR,
]


def make_device(kind: str) -> UInput:
    if kind == "xbox":
        ident = dict(name="Microsoft X-Box 360 pad", vendor=0x045E, product=0x028E, version=0x110)
        stick = AbsInfo(0, -32768, 32767, 16, 128, 0)
    else:  # "dualsense": the SDL database matches on the 0x8111 version
        ident = dict(
            name="Sony Interactive Entertainment DualSense Wireless Controller",
            vendor=0x054C, product=0x0CE6, version=0x8111,
        )
        stick = AbsInfo(128, 0, 255, 0, 0, 0)
    trigger = AbsInfo(0, 0, 255, 0, 0, 0)
    hat = AbsInfo(0, -1, 1, 0, 0, 0)
    axes = [
        (e.ABS_X, stick), (e.ABS_Y, stick), (e.ABS_Z, trigger), (e.ABS_RX, stick),
        (e.ABS_RY, stick), (e.ABS_RZ, trigger), (e.ABS_HAT0X, hat), (e.ABS_HAT0Y, hat),
    ]
    # The SDL mappings address buttons by their index among the device's
    # buttons, so a DualSense needs its L2/R2 buttons to line up
    keys = KEYS + [e.BTN_TL2, e.BTN_TR2] if kind != "xbox" else KEYS
    return UInput({e.EV_KEY: sorted(keys), e.EV_ABS: axes}, bustype=e.BUS_USB, **ident)


def run(kind: str) -> list[str]:
    """Press everything on a virtual controller; return the problems found"""
    actions: list[Action] = []
    controller = gamepad.GamepadController(SimpleNamespace())
    controller.input.callback = actions.append
    controller.input.repeat_delay_ms = 300
    controller.input.repeat_interval_ms = 100

    uinput = make_device(kind)
    time.sleep(0.5)
    if not controller.start():
        return ["libmanette is not available"]
    iterate_main_loop(until=lambda: bool(controller.devices), timeout=3)
    if not controller.devices:
        return ["libmanette did not see the virtual controller"]

    steady = (32767, 0) if kind == "xbox" else (255, 128)  # stick: pushed, centered
    problems: list[str] = []

    def key(code: int, hold: float = 0.1) -> None:
        uinput.write(e.EV_KEY, code, 1)
        uinput.syn()
        time.sleep(hold)
        uinput.write(e.EV_KEY, code, 0)
        uinput.syn()
        time.sleep(0.1)

    def axis(code: int, value: int, hold: float = 0.1, rest: int = 0) -> None:
        uinput.write(e.EV_ABS, code, value)
        uinput.syn()
        time.sleep(hold)
        uinput.write(e.EV_ABS, code, rest)
        uinput.syn()
        time.sleep(0.1)

    # Kernel codes differ per driver: the physical X / Square is BTN_NORTH
    # for xpad but BTN_WEST for hid-playstation. libmanette hides that.
    x_code, y_code = (e.BTN_NORTH, e.BTN_WEST) if kind == "xbox" else (e.BTN_WEST, e.BTN_NORTH)

    def script() -> None:
        key(e.BTN_SOUTH)
        key(e.BTN_EAST)
        key(x_code)
        key(y_code)
        key(e.BTN_TL)
        key(e.BTN_TR)
        key(e.BTN_START)
        for code, value in ((e.ABS_HAT0Y, 1), (e.ABS_HAT0Y, -1), (e.ABS_HAT0X, -1), (e.ABS_HAT0X, 1)):
            axis(code, value)
        axis(e.ABS_X, steady[0], rest=steady[1])
        axis(e.ABS_Y, steady[0], rest=steady[1])
        axis(e.ABS_HAT0Y, 1, hold=0.9)  # held: must repeat

    thread = threading.Thread(target=script, daemon=True)
    thread.start()
    iterate_main_loop(until=lambda: False, timeout=4.5)
    thread.join()
    uinput.close()
    iterate_main_loop(timeout=0.5)

    expected = [
        Action.ACCEPT, Action.BACK, Action.GAME_MENU, Action.SEARCH,
        Action.PREVIOUS_SOURCE, Action.NEXT_SOURCE, Action.SIDEBAR,
        Action.DOWN, Action.UP, Action.LEFT, Action.RIGHT, Action.RIGHT, Action.DOWN,
    ]
    if actions[: len(expected)] != expected:
        problems.append(f"expected {[a.name for a in expected]}\n   got {[a.name for a in actions]}")
    repeats = actions[len(expected):]
    if len(repeats) < 3 or set(repeats) != {Action.DOWN}:
        problems.append(f"holding down should repeat DOWN, got {[a.name for a in repeats]}")
    return problems


def main() -> None:
    failed = False
    for kind in ("xbox", "dualsense"):
        try:
            problems = run(kind)
        except PermissionError:
            raise SystemExit("No write access to /dev/uinput") from None
        print(f"{kind}: {'OK' if not problems else 'FAILED'}")
        for problem in problems:
            print("  -", problem)
        failed |= bool(problems)
    sys.exit(int(failed))


if __name__ == "__main__":
    main()
