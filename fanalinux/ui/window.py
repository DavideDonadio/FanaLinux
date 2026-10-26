"""
Main Application Window using Libadwaita.
Integrates Hardware Device, Evdev Listener, Telemetry Manager, and Auto-Profile Game Detector.
"""

import logging
import os
import time

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gdk', '4.0')
from gi.repository import Adw, Gdk, GLib, Gtk

from fanalinux.core.detector import GameDetector
from fanalinux.core.device import FanatecDevice
from fanalinux.core.evdev_listener import EvdevListener, query_ff_effects
from fanalinux.core.presets import load_preset
from fanalinux.core.telemetry.manager import TelemetryManager
from fanalinux.ui.helpers import widen_page_clamp
from fanalinux.ui.views.calibration import CalibrationView
from fanalinux.ui.views.dynamic_ffb import DynamicFFBView
from fanalinux.ui.views.leds import LedsView
from fanalinux.ui.views.overview import OverviewView
from fanalinux.ui.views.profiles import ProfilesView
from fanalinux.ui.views.tuning import TuningView
from fanalinux.ui.views.vibration import VibrationView

logger = logging.getLogger("fanalinux.window")


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_title("FanaLinux")
        self.set_icon_name("io.github.davidedonadio.fanalinux")
        self.set_default_size(1220, 880)
        self.maximize()

        # Load Custom Stylesheet
        self._load_stylesheet()

        # Initialize Hardware & Telemetry Engine
        self.device = FanatecDevice()
        self.device.connect()
        self.telemetry_mgr = TelemetryManager(self.device)

        # Initialize Auto-Profile Detector
        self.detector = GameDetector(
            on_game_started=self._on_game_started,
            on_game_stopped=self._on_game_stopped
        )
        # Last game that owned telemetry (guards direct A->B switches)
        self._last_game_id = None

        # Toast Overlay
        self.toast_overlay = Adw.ToastOverlay()

        # Main Layout
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Header Bar
        header = Adw.HeaderBar()
        title_widget = Adw.WindowTitle(title="FanaLinux", subtitle="Fanatec Control Suite &amp; Telemetry")
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
        self.overview_view = OverviewView(self.device, on_rim_changed=self._on_rim_changed)
        self.tuning_view = TuningView(
            self.device,
            on_toast_requested=self.show_toast,
            on_presets_changed=self._on_presets_changed
        )
        self.vibration_view = VibrationView(
            self.device,
            haptic_engine=self.telemetry_mgr.haptic_engine,
            on_toast_requested=self.show_toast
        )
        self.dynamic_ffb_view = DynamicFFBView(
            self.device,
            telemetry_mgr=self.telemetry_mgr,
            on_toast_requested=self.show_toast
        )
        self.leds_view = LedsView(
            self.device,
            telemetry_mgr=self.telemetry_mgr,
            on_toast_requested=self.show_toast
        )
        self.profiles_view = ProfilesView(
            self.device,
            telemetry_mgr=self.telemetry_mgr,
            detector=self.detector,
            on_toast_requested=self.show_toast,
            on_preset_applied=self._on_preset_applied
        )
        self.calibration_view = CalibrationView(self.device, on_toast_requested=self.show_toast)

        self.view_stack.add_titled_with_icon(
            self.overview_view, "overview", "Overview", "input-gaming-symbolic"
        )
        self.view_stack.add_titled_with_icon(
            self.tuning_view, "tuning", "Tuning Menu", "preferences-system-symbolic"
        )
        self.view_stack.add_titled_with_icon(
            self.vibration_view, "vibration", "Vibration", "audio-volume-high-symbolic"
        )
        self.view_stack.add_titled_with_icon(
            self.dynamic_ffb_view, "dynamic_ffb", "Dynamic FFB", "power-profile-performance-symbolic"
        )
        self.view_stack.add_titled_with_icon(
            self.leds_view, "leds", "LEDs & Display", "weather-clear-symbolic"
        )
        self.view_stack.add_titled_with_icon(
            self.profiles_view, "profiles", "Game Profiles", "applications-games-symbolic"
        )
        self.view_stack.add_titled_with_icon(
            self.calibration_view, "calibration", "Calibration", "emblem-system-symbolic"
        )

        main_box.append(self.view_stack)
        self.toast_overlay.set_child(main_box)
        self.set_content(self.toast_overlay)

        # Start Evdev Listener
        def _on_steering_event(norm_val: float, raw_val: int):
            self.overview_view.update_steering(norm_val, raw_val)
            self.calibration_view.update_steering(norm_val, raw_val)

        self.evdev_listener = EvdevListener(
            on_steering=_on_steering_event,
            on_throttle=self.overview_view.update_throttle,
            on_brake=self.overview_view.update_brake,
            on_clutch=self.overview_view.update_clutch,
            on_button=self.overview_view.update_button,
        )
        self.evdev_listener.start()
        self.calibration_view.set_evdev_listener(self.evdev_listener)

        # Start Auto-Profile Detector
        self.detector.start()

        # Hardware connection state & live hotplug/unplug monitor (1 sec interval)
        self._hardware_online = self.device.connected if self.device else False
        self._last_evdev_retry = 0.0
        self.overview_view.set_connection_status(self._hardware_online)
        GLib.timeout_add_seconds(1, self._check_hardware_connection)

        # Ensure all preference pages utilize the full window width (1040px)
        GLib.idle_add(self._widen_all_clamps)

        self.connect("close-request", self._on_close)

    def _widen_all_clamps(self):
        views = [
            self.overview_view,
            self.tuning_view,
            self.vibration_view,
            self.leds_view,
            self.profiles_view,
            self.calibration_view,
        ]
        for page in views:
            widen_page_clamp(page)
        # Tuning content outgrew the shared width: give that tab alone more room
        widen_page_clamp(self.tuning_view, 1440)
        return False

    def _load_stylesheet(self):
        try:
            css_provider = Gtk.CssProvider()
            css_path = os.path.join(os.path.dirname(__file__), "style.css")
            if os.path.exists(css_path):
                css_provider.load_from_path(css_path)
                display = Gdk.Display.get_default()
                if display:
                    Gtk.StyleContext.add_provider_for_display(
                        display,
                        css_provider,
                        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                    )
        except Exception as e:
            print(f"Notice: CSS provider error: {e}")

    def show_toast(self, message: str):
        # Escape any raw ampersands for Pango markup safety
        escaped = message.replace("&", "&amp;") if "&amp;" not in message else message
        toast = Adw.Toast(title=escaped)
        toast.set_timeout(3)
        self.toast_overlay.add_toast(toast)

    def _on_game_started(self, game_info, preset_name, auto_telem):
        GLib.idle_add(self._apply_game_started, game_info, preset_name, auto_telem)

    def _apply_game_started(self, game_info, preset_name, auto_telem):
        profile = load_preset(preset_name)
        if profile and self.device and self.device.connected:
            self.device.apply_tuning_profile(profile)
            self.tuning_view.set_active_profile(profile)

        # The detector fires started directly on A->B switches with no
        # stopped event in between: stop the previous game's session first.
        # Only game-owned sessions are touched, manual telemetry survives.
        new_game_id = game_info.get("id")
        if (self.telemetry_mgr.enabled and self._last_game_id is not None
                and self._last_game_id != new_game_id):
            self.telemetry_mgr.stop()
            self.leds_view.set_telemetry_active(False)
        self._last_game_id = new_game_id

        if auto_telem:
            telem_type = game_info.get("telemetry_type") or "ac_udp"
            self.telemetry_mgr.start(telemetry_type=telem_type)
            self.leds_view.set_telemetry_active(True)

        self.profiles_view.update_status(game_info)
        toast_msg = f"Game Detected: {game_info['name']} → Loaded '{preset_name}'"
        if auto_telem:
            toast_msg += " & Telemetry started"
        self.show_toast(toast_msg)
        return False

    def _on_game_stopped(self, game_info, fallback_preset):
        GLib.idle_add(self._apply_game_stopped, game_info, fallback_preset)

    def _apply_game_stopped(self, game_info, fallback_preset):
        self._last_game_id = None
        if self.telemetry_mgr.enabled:
            self.telemetry_mgr.stop()
            self.leds_view.set_telemetry_active(False)

        profile = load_preset(fallback_preset)
        if profile and self.device and self.device.connected:
            self.device.apply_tuning_profile(profile)
            self.tuning_view.set_active_profile(profile)

        self.profiles_view.update_status(None)
        self.show_toast(f"{game_info['name']} exited → Restored '{fallback_preset}' preset")
        return False

    def _on_rim_changed(self, rim_info: dict):
        if hasattr(self, "calibration_view") and self.calibration_view:
            self.calibration_view.update_rim(rim_info)

    def _on_presets_changed(self):
        self.profiles_view.refresh_preset_lists()

    def _check_hardware_connection(self) -> bool:
        """Periodic hardware health monitor: handles unplug and hotplug reconnect."""
        was_online = self._hardware_online
        is_online = self.device.check_connection() if self.device else False
        self._hardware_online = is_online

        # Kernel FFB driver state from probed evdev effects (empty = missing)
        node = self.evdev_listener.device_node if self.evdev_listener else None
        self.overview_view.set_ff_driver(query_ff_effects(node) if is_online else [])

        if was_online != is_online:
            self.overview_view.set_connection_status(is_online)
            if is_online:
                if not self.evdev_listener.is_running():
                    self.evdev_listener.start()
                    self.calibration_view.set_evdev_listener(self.evdev_listener)
                self._last_evdev_retry = time.monotonic()
                self.show_toast("Fanatec CSL DD connected and online!")
                # Only re-apply profile if an auto-profile sim session is actively in progress
                active_game = getattr(self.detector, "active_game", None) if self.detector else None
                if active_game:
                    active_profile = getattr(self.tuning_view, "profile", None)
                    if active_profile and self.device:
                        logger.info(f"Restoring profile '{active_profile.name}' (Slot {active_profile.slot}) for '{active_game['name']}' after reconnect")
                        self.device.apply_tuning_profile(active_profile)
            else:
                self.evdev_listener.stop()
                self.show_toast("Fanatec hardware disconnected!")

        # Watchdog: evdev may have failed to open at startup or its worker
        # may have died while HID stayed healthy. Retry with backoff.
        if is_online and not self.evdev_listener.is_running():
            now = time.monotonic()
            if now - self._last_evdev_retry >= 5.0:
                self._last_evdev_retry = now
                if self.evdev_listener.start():
                    self.calibration_view.set_evdev_listener(self.evdev_listener)

        return True

    def _on_preset_applied(self, preset_name):
        profile = load_preset(preset_name)
        if profile:
            self.tuning_view.set_active_profile(profile)

    def _on_close(self, *args):
        if self.detector:
            self.detector.stop()
        if self.telemetry_mgr:
            self.telemetry_mgr.stop()
        if self.evdev_listener:
            self.evdev_listener.stop()
        if self.device and self.device.connected:
            try:
                self.device.clear_display()
                self.device.set_revleds([(0, 0, 0)] * 9)
                self.device.set_flagleds([(0, 0, 0)] * 6)
            except Exception:
                pass
            self.device.disconnect()
        return False
