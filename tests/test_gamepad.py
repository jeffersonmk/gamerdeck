"""Tests for controller navigation: input mapping, repeat and gating.

The window-level behaviour (focus moves, menus, dialogs) is covered by
tests/test_gamepad_ui.py, and the libmanette path by tests/gamepad_uinput.py.
"""

# pylint: disable=missing-function-docstring,protected-access
import unittest
from types import SimpleNamespace

from tests.support import iterate_main_loop

from cartridges import gamepad
from cartridges.gamepad import Action, GamepadController, GamepadInput


class InputTests(unittest.TestCase):
    def setUp(self):
        self.actions: list[Action] = []
        # Short timings so the tests are quick
        self.input = GamepadInput(self.actions.append, repeat_delay_ms=60, repeat_interval_ms=25)
        self.addCleanup(self.input.release_all)

    def wait(self, seconds: float) -> None:
        iterate_main_loop(until=lambda: False, timeout=seconds)

    def test_buttons_map_to_actions_once(self):
        for code, action in (
            (gamepad.BTN_SOUTH, Action.ACCEPT),
            (gamepad.BTN_EAST, Action.BACK),
            (gamepad.BTN_WEST, Action.GAME_MENU),
            (gamepad.BTN_NORTH, Action.SEARCH),
            (gamepad.BTN_TL, Action.PREVIOUS_SOURCE),
            (gamepad.BTN_TR, Action.NEXT_SOURCE),
            (gamepad.BTN_START, Action.SIDEBAR),
        ):
            self.actions.clear()
            self.input.button(code, True)
            self.wait(0.15)  # holding a button never repeats it
            self.input.button(code, False)
            self.assertEqual(self.actions, [action])

    def test_unmapped_buttons_do_nothing(self):
        for code in (0x13C, 0x13D, 0x138, 0x139):  # Guide, sticks, triggers
            self.input.button(code, True)
            self.input.button(code, False)
        self.assertEqual(self.actions, [])

    def test_direction_buttons_all_four(self):
        for code in (gamepad.BTN_DPAD_UP, gamepad.BTN_DPAD_DOWN,
                     gamepad.BTN_DPAD_LEFT, gamepad.BTN_DPAD_RIGHT):
            self.input.button(code, True)
            self.input.button(code, False)
        self.assertEqual(self.actions, [Action.UP, Action.DOWN, Action.LEFT, Action.RIGHT])

    def test_held_direction_repeats_until_released(self):
        self.input.button(gamepad.BTN_DPAD_DOWN, True)
        self.assertEqual(self.actions, [Action.DOWN])
        self.wait(0.03)
        self.assertEqual(len(self.actions), 1)  # still inside the delay
        self.wait(0.2)
        self.assertGreaterEqual(len(self.actions), 4)
        self.input.button(gamepad.BTN_DPAD_DOWN, False)
        count = len(self.actions)
        self.wait(0.15)
        self.assertEqual(len(self.actions), count)
        self.assertEqual(set(self.actions), {Action.DOWN})

    def test_short_press_does_not_repeat(self):
        self.input.button(gamepad.BTN_DPAD_UP, True)
        self.wait(0.02)
        self.input.button(gamepad.BTN_DPAD_UP, False)
        self.wait(0.2)
        self.assertEqual(self.actions, [Action.UP])

    def test_hat_is_the_same_as_the_buttons(self):
        for axis, value in ((gamepad.ABS_HAT0Y, 1), (gamepad.ABS_HAT0Y, -1),
                            (gamepad.ABS_HAT0X, -1), (gamepad.ABS_HAT0X, 1)):
            self.input.hat(axis, value)
            self.input.hat(axis, 0)
        self.assertEqual(self.actions, [Action.DOWN, Action.UP, Action.LEFT, Action.RIGHT])

    def test_stick_needs_a_real_push_and_has_hysteresis(self):
        self.input.axis(gamepad.ABS_X, 0.3)  # drift
        self.assertEqual(self.actions, [])
        self.input.axis(gamepad.ABS_X, 0.8)
        self.assertEqual(self.actions, [Action.RIGHT])
        self.input.axis(gamepad.ABS_X, 0.5)  # eased off but not released
        self.input.axis(gamepad.ABS_X, 0.7)
        self.assertEqual(self.actions, [Action.RIGHT])
        self.input.axis(gamepad.ABS_X, 0.2)  # released
        self.input.axis(gamepad.ABS_X, 0.8)
        self.assertEqual(self.actions, [Action.RIGHT, Action.RIGHT])

    def test_stick_uses_the_dominant_axis_and_down_is_positive(self):
        self.input.axis(gamepad.ABS_Y, 0.9)
        self.input.axis(gamepad.ABS_X, -0.4)
        self.assertEqual(self.actions, [Action.DOWN])  # Y still wins
        self.input.axis(gamepad.ABS_Y, -0.1)
        self.assertEqual(self.actions[-1], Action.LEFT)  # X wins now
        self.input.axis(gamepad.ABS_X, 0.0)
        self.input.axis(gamepad.ABS_Y, -0.9)
        self.assertEqual(self.actions[-1], Action.UP)

    def test_other_axes_are_ignored(self):
        self.input.axis(gamepad.ABS_X + 2, 1.0)  # triggers / right stick
        self.input.hat(0x12, 1)
        self.assertEqual(self.actions, [])

    def test_releasing_one_source_keeps_repeating_the_other(self):
        self.input.hat(gamepad.ABS_HAT0Y, 1)  # d-pad down
        self.input.axis(gamepad.ABS_X, 0.9)  # stick right takes over
        self.assertEqual(self.actions, [Action.DOWN, Action.RIGHT])
        self.input.axis(gamepad.ABS_X, 0.0)  # stick released: down still held
        self.wait(0.2)
        self.assertEqual(self.actions[-1], Action.DOWN)
        self.assertGreaterEqual(len(self.actions), 4)

    def test_release_all_stops_everything(self):
        self.input.button(gamepad.BTN_DPAD_LEFT, True)
        self.input.release_all()
        count = len(self.actions)
        self.wait(0.2)
        self.assertEqual(len(self.actions), count)
        self.input.button(gamepad.BTN_DPAD_LEFT, True)  # can be pressed again
        self.assertEqual(self.actions[-1], Action.LEFT)
        self.assertEqual(len(self.actions), count + 1)


class FakeDevice:
    def __init__(self, name: str = "Fake pad"):
        self.name = name
        self.handlers: dict = {}

    def get_name(self) -> str:
        return self.name

    def connect(self, signal: str, handler, *args) -> None:
        self.handlers[signal] = (handler, args)

    def emit(self, signal: str, event) -> None:
        handler, args = self.handlers[signal]
        handler(self, event, *args)


class FakeEvent:
    def __init__(self, button=None, hat=None, absolute=None):
        self._values = {"button": button, "hat": hat, "absolute": absolute}

    def get_button(self):
        return (True, self._values["button"]) if self._values["button"] else (False, 0)

    def get_hat(self):
        return (True, *self._values["hat"]) if self._values["hat"] else (False, 0, 0)

    def get_absolute(self):
        return (True, *self._values["absolute"]) if self._values["absolute"] else (False, 0, 0.0)


class ControllerTests(unittest.TestCase):
    def make(self, active: bool = True):
        win = SimpleNamespace(is_active=lambda: active)
        controller = GamepadController(SimpleNamespace(get_active_window=lambda: win))
        self.actions: list[Action] = []
        controller.input.callback = self.actions.append
        self.addCleanup(controller.input.release_all)
        return controller

    def test_device_events_become_actions(self):
        controller = self.make()
        device = FakeDevice()
        controller._device_connected(None, device)
        device.emit("button-press-event", FakeEvent(button=gamepad.BTN_SOUTH))
        device.emit("hat-axis-event", FakeEvent(hat=(gamepad.ABS_HAT0X, 1)))
        device.emit("hat-axis-event", FakeEvent(hat=(gamepad.ABS_HAT0X, 0)))
        device.emit("absolute-axis-event", FakeEvent(absolute=(gamepad.ABS_Y, -1.0)))
        device.emit("absolute-axis-event", FakeEvent(absolute=(gamepad.ABS_Y, 0.0)))
        self.assertEqual(self.actions, [Action.ACCEPT, Action.RIGHT, Action.UP])

    def test_a_device_is_only_connected_once(self):
        controller = self.make()
        device = FakeDevice()
        controller._device_connected(None, device)
        controller._device_connected(None, device)
        self.assertEqual(len(controller.devices), 1)

    def test_disconnecting_releases_held_directions(self):
        controller = self.make()
        device = FakeDevice()
        controller._device_connected(None, device)
        device.emit("button-press-event", FakeEvent(button=gamepad.BTN_DPAD_DOWN))
        controller._device_disconnected(None, device)
        count = len(self.actions)
        iterate_main_loop(until=lambda: False, timeout=0.6)
        self.assertEqual(len(self.actions), count)
        self.assertFalse(controller.devices)

    def test_the_controller_is_in_use_after_it_moves_something(self):
        refreshed = []
        win = SimpleNamespace(
            is_active=lambda: True,
            set_focus_visible=lambda _visible: None,
            activate_action=lambda *_args: None,
            update_hints=lambda: refreshed.append(True),
        )
        controller = GamepadController(SimpleNamespace(get_active_window=lambda: win))
        self.assertFalse(controller.in_use)
        controller.dispatch(Action.SEARCH)
        self.assertTrue(controller.in_use)
        self.assertGreater(controller.last_input, 0)
        self.assertEqual(len(refreshed), 1)
        controller.dispatch(Action.SEARCH)  # already in use: the legend is not redone
        self.assertEqual(len(refreshed), 1)
        controller.set_in_use(False)  # the mouse or the keyboard took over
        self.assertFalse(controller.in_use)
        self.assertEqual(len(refreshed), 2)
        controller.set_in_use(False)
        self.assertEqual(len(refreshed), 2)

    def test_a_window_without_the_focus_does_not_put_the_controller_in_use(self):
        controller = self.make(active=False)
        controller.dispatch(Action.SEARCH)
        self.assertFalse(controller.in_use)

    def test_the_last_controller_leaving_ends_the_use(self):
        controller = self.make()
        device = FakeDevice()
        controller._device_connected(None, device)
        controller.in_use = True
        controller._device_disconnected(None, device)
        self.assertFalse(controller.in_use)

    def test_window_without_the_focus_is_ignored(self):
        controller = self.make(active=False)
        self.assertIsNone(controller.get_window())
        # dispatch() must not touch the window at all (a game may be running)
        controller.dispatch(Action.ACCEPT)

    def test_no_window_is_ignored(self):
        controller = GamepadController(SimpleNamespace(get_active_window=lambda: None))
        self.assertIsNone(controller.get_window())
        controller.dispatch(Action.BACK)

    def test_missing_libmanette_disables_the_feature(self):
        original = gamepad.Manette
        gamepad.Manette = None
        try:
            self.assertFalse(self.make().start())
        finally:
            gamepad.Manette = original


if __name__ == "__main__":
    unittest.main()
