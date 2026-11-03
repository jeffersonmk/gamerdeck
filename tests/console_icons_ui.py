"""Renders every console badge as the cards draw it, on a dark and a light cover.

Run with GAMERDECK_UI_MODULE=tests.console_icons_ui tests/run_gamepad_ui.sh <dir>
"""

# pylint: disable=missing-function-docstring
import os
from pathlib import Path

from tests.support import iterate_main_loop  # noqa: F401  (sets the environment)

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from cartridges import shared  # noqa: E402
from cartridges.emulators import CONSOLE_ICONS  # noqa: E402
from tests.gamepad_ui import render  # noqa: E402


def main() -> None:
    out = Path(os.environ.get("GAMEPAD_UI_SHOTS", "."))
    out.mkdir(parents=True, exist_ok=True)
    Adw.init()
    css = Gtk.CssProvider()
    css.load_from_resource(f"{shared.PREFIX}/gtk/style.css")
    Gtk.StyleContext.add_provider_for_display(
        Gtk.Widget.get_display(Gtk.Window()), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    win = Gtk.Window(default_width=980, default_height=300)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    for color in ("#1c1415", "#f5f5f5"):
        row = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=9)
        provider = Gtk.CssProvider()
        provider.load_from_string(f"flowbox {{ background: {color}; padding: 8px; }}")
        row.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        for console, icon_file in CONSOLE_ICONS.items():
            cell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            button = Gtk.Button(halign=Gtk.Align.CENTER)
            for name in ("circular", "osd", "platform-badge"):
                button.add_css_class(name)
            image = Gtk.Image.new_from_resource(f"{shared.PREFIX}/icons/consoles/{icon_file}")
            image.set_pixel_size(16)
            button.set_child(image)
            label = Gtk.Label(label=console)
            label.add_css_class("caption")
            cell.append(button)
            cell.append(label)
            row.append(cell)
        box.append(row)
    win.set_child(box)
    win.present()
    loop = GLib.MainLoop()

    def finish() -> bool:
        ok = render(win, out / "console-icons.png")
        print("RESULT", '{"rendered": %s}' % str(ok).lower())
        loop.quit()
        return False

    GLib.timeout_add(1200, finish)
    loop.run()


main()
