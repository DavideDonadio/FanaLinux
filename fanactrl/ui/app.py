"""
Application Entry for Libadwaita.
"""

import sys
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio

from fanactrl.ui.window import MainWindow


class OpenFanaApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="io.github.openfanactrl.App",
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = MainWindow(application=self)
        win.present()


def run_app():
    app = OpenFanaApp()
    return app.run(sys.argv)
