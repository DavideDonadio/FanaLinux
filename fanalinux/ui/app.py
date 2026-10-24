"""
Application Entry for Libadwaita.
"""

import sys
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio

from fanalinux.ui.window import MainWindow


class FanaLinuxApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="io.github.davidedonadio.fanalinux",
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = MainWindow(application=self)
        win.present()
        # Re-assert after present: some compositors ignore pre-map maximize()
        win.maximize()


def run_app():
    app = FanaLinuxApp()
    return app.run(sys.argv)
