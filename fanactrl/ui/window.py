"""
Main Application Window using Libadwaita.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib

from fanactrl.core.device import FanatecDevice
from fanactrl.core.evdev_listener import EvdevListener
from fanactrl.ui.views.overview import OverviewView
from fanactrl.ui.views.tuning import TuningView
from fanactrl.ui.views.leds import LedsView
from fanactrl.ui.views.calibration import CalibrationView


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_title("OpenFana Control")
        self.set_default_size(960, 800)

        # Initialize Hardware & Evdev Monitor
        self.device = FanatecDevice()
        self.device.connect()

        # Toast Overlay
        self.toast_overlay = Adw.ToastOverlay()

        # Main Layout
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Header Bar
        header = Adw.HeaderBar()
        title_widget = Adw.WindowTitle(title="OpenFana Control", subtitle="Fanatec Linux Suite")
        header.set_title_widget(title_widget)

        # View Switcher in Header
        self.view_stack = Adw.ViewStack()
        self.view_stack.set_vexpand(True)
        self.view_stack.set_hexpand(True)

        view_switcher = Adw.ViewSwitcher()
        view_switcher.set_stack(self.view_stack)
        view_switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(view_switcher)

        main_box.append(header)

        # Create Views (All are Adw.PreferencesPage with built-in scrolling & clamping)
        self.overview_view = OverviewView(self.device)
        self.tuning_view = TuningView(self.device, on_toast_requested=self.show_toast)
        self.leds_view = LedsView(self.device, on_toast_requested=self.show_toast)
        self.calibration_view = CalibrationView(self.device, on_toast_requested=self.show_toast)

        self.view_stack.add_titled_with_icon(
            self.overview_view, "overview", "Overview", "input-gaming-symbolic"
        )
        self.view_stack.add_titled_with_icon(
            self.tuning_view, "tuning", "Tuning Menu", "preferences-system-symbolic"
        )
        self.view_stack.add_titled_with_icon(
            self.leds_view, "leds", "LEDs & Display", "weather-clear-symbolic"
        )
        self.view_stack.add_titled_with_icon(
            self.calibration_view, "calibration", "Calibration", "emblem-system-symbolic"
        )

        main_box.append(self.view_stack)
        self.toast_overlay.set_child(main_box)
        self.set_content(self.toast_overlay)

        # Start Evdev Listener
        self.evdev_listener = EvdevListener(
            on_steering=self.overview_view.update_steering,
            on_throttle=self.overview_view.update_throttle,
            on_brake=self.overview_view.update_brake,
            on_clutch=self.overview_view.update_clutch,
            on_button=self.overview_view.update_button,
        )
        self.evdev_listener.start()

        self.connect("close-request", self._on_close)

    def show_toast(self, message: str):
        toast = Adw.Toast(title=message)
        toast.set_timeout(3)
        self.toast_overlay.add_toast(toast)

    def _on_close(self, *args):
        if self.evdev_listener:
            self.evdev_listener.stop()
        if self.device:
            self.device.disconnect()
        return False
