"""
LEDs & Display Telemetry View (FanaLab Equivalent).
Includes Native Assetto Corsa UDP Telemetry Ingestion.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
import threading
import time

from fanalinux.core.telemetry.manager import TelemetryManager


class LedsView(Adw.PreferencesPage):
    def __init__(self, device, telemetry_mgr=None, on_toast_requested=None):
        super().__init__()
        self.device = device
        self.on_toast_requested = on_toast_requested
        self._led_dots = []

        # Initialize In-Game Telemetry Manager
        self.telemetry_mgr = telemetry_mgr if telemetry_mgr is not None else TelemetryManager(self.device)

        # Ensure wide clamp so RevLEDs and descriptions have ample horizontal room
        GLib.idle_add(self._widen_page_clamp)
        self._build_ui()

    def _widen_page_clamp(self):
        try:
            sw = self.get_first_child()
            if sw:
                vp = sw.get_first_child()
                if vp:
                    clamp = vp.get_first_child()
                    if isinstance(clamp, Adw.Clamp):
                        clamp.set_maximum_size(1180)
                        clamp.set_tightening_threshold(1080)
        except Exception:
            pass
        return False

    def _build_ui(self):
        # 1. Live In-Game Telemetry Configuration
        telem_group = Adw.PreferencesGroup()
        telem_group.set_title("In-Game Telemetry &amp; Shift Indicators")
        telem_group.set_description(
            "Configure OLED rim display mode and RPM shift points driven automatically "
            "by the background telemetry engine during racing sessions."
        )

        mode_row = Adw.ActionRow()
        mode_row.set_title("OLED In-Game Display Mode")
        mode_row.set_subtitle("Choose what information appears on your rim display while driving")

        self.mode_dropdown = Gtk.DropDown.new_from_strings(["Current Gear (1, 2, 3, N, R)", "Speed (KM/H)"])
        self.mode_dropdown.set_valign(Gtk.Align.CENTER)
        self.mode_dropdown.connect("notify::selected", self._on_mode_changed)
        mode_row.add_suffix(self.mode_dropdown)
        telem_group.add(mode_row)

        redline_row = Adw.ActionRow()
        redline_row.set_title("Shift Point / Redline RPM")
        redline_row.set_subtitle("Type exact RPM limit or click +/- (Formula 4: ~6,300 RPM)")

        redline_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        redline_box.set_valign(Gtk.Align.CENTER)

        redline_adj = Gtk.Adjustment(value=6500, lower=2000, upper=22000, step_increment=50, page_increment=500)
        self.redline_spin = Gtk.SpinButton(adjustment=redline_adj, climb_rate=50, digits=0)
        self.redline_spin.set_valign(Gtk.Align.CENTER)
        self.redline_spin.set_numeric(True)
        self.redline_spin.set_size_request(130, 38)
        self.redline_spin.add_css_class("val-badge")

        def _on_redline_changed(spin):
            val = int(spin.get_value())
            self.telemetry_mgr.max_rpm = val
            self.telemetry_mgr.auto_detect_rpm = False

        self.redline_spin.connect("value-changed", _on_redline_changed)

        redline_box.append(self.redline_spin)
        redline_row.add_suffix(redline_box)
        telem_group.add(redline_row)

        sim_row = Adw.ActionRow()
        sim_row.set_title("Simulate AC Race Lap (Demo Mode)")
        sim_row.set_subtitle("Runs a realistic 12-second acceleration, shifting, and braking sequence without needing pedals")

        sim_btn = Gtk.Button(label="Simulate Race Lap")
        sim_btn.set_size_request(160, 42)
        sim_btn.set_valign(Gtk.Align.CENTER)
        sim_btn.add_css_class("suggested-action")
        sim_btn.add_css_class("pill")
        sim_btn.connect("clicked", self._on_simulate_lap)
        sim_row.add_suffix(sim_btn)
        telem_group.add(sim_row)

        self.add(telem_group)

        # 2. 1-inch OLED Display Manual Controls
        oled_group = Adw.PreferencesGroup()
        oled_group.set_title("OLED Rim Display (Manual Override)")
        oled_group.set_description("Write custom strings directly to the Formula V2.5 center display")

        disp_row = Adw.ActionRow()
        disp_row.set_title("Display String")
        disp_row.set_subtitle("Supports up to 3 alphanumeric characters")

        disp_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        disp_box.set_valign(Gtk.Align.CENTER)

        self.disp_entry = Gtk.Entry()
        self.disp_entry.set_max_length(3)
        self.disp_entry.set_placeholder_text("F1")
        self.disp_entry.set_text("F1")
        self.disp_entry.set_width_chars(6)
        self.disp_entry.set_valign(Gtk.Align.CENTER)
        disp_box.append(self.disp_entry)

        send_btn = Gtk.Button(label="Send")
        send_btn.set_size_request(80, 38)
        send_btn.set_valign(Gtk.Align.CENTER)
        send_btn.add_css_class("suggested-action")
        send_btn.connect("clicked", self._on_send_display)
        disp_box.append(send_btn)

        clear_btn = Gtk.Button(label="Clear")
        clear_btn.set_size_request(80, 38)
        clear_btn.set_valign(Gtk.Align.CENTER)
        clear_btn.connect("clicked", self._on_clear_display)
        disp_box.append(clear_btn)

        disp_row.add_suffix(disp_box)
        oled_group.add(disp_row)
        self.add(oled_group)

        # 3. RevLEDs (9 Multi-Color LEDs) Group
        rev_group = Adw.PreferencesGroup()
        rev_group.set_title("RPM RevLEDs (9 LEDs)")
        rev_group.set_description("Sequential multi-color shift indicators (Green -> Yellow -> Red / Blue)")

        rev_row = Adw.ActionRow()
        rev_row.set_title("RevLED Light Strip")
        rev_row.set_subtitle("Interactive hardware test pattern")

        rev_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        rev_box.set_valign(Gtk.Align.CENTER)

        dots_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        dots_box.set_valign(Gtk.Align.CENTER)
        self._led_dots = []
        for _ in range(9):
            dot = Gtk.Box()
            dot.add_css_class("led-preview-dot")
            dots_box.append(dot)
            self._led_dots.append(dot)
        rev_box.append(dots_box)

        test_rev_btn = Gtk.Button(label="Test RPM Climb")
        test_rev_btn.set_size_request(140, 38)
        test_rev_btn.set_valign(Gtk.Align.CENTER)
        test_rev_btn.add_css_class("pill")
        test_rev_btn.connect("clicked", self._on_test_revleds)
        rev_box.append(test_rev_btn)

        rev_row.add_suffix(rev_box)
        rev_group.add(rev_row)
        self.add(rev_group)

        # 4. Flag LEDs (6 Multi-Color LEDs: 3 Left, 3 Right)
        flag_group = Adw.PreferencesGroup()
        flag_group.set_title("Side Flag LEDs (6 LEDs)")
        flag_group.set_description("Cluster alerts for marshaling flags, pit limiter, and ABS warnings")

        flag_row = Adw.ActionRow()
        flag_row.set_title("Flag Simulation")
        flag_row.set_subtitle("Triggers the left and right multi-color flag clusters")

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_valign(Gtk.Align.CENTER)

        yellow_btn = Gtk.Button(label="Yellow Flag")
        yellow_btn.set_size_request(105, 38)
        yellow_btn.connect("clicked", lambda b: self._flash_flags((255, 255, 0), "Yellow Flag"))
        btn_box.append(yellow_btn)

        blue_btn = Gtk.Button(label="Blue Flag")
        blue_btn.set_size_request(105, 38)
        blue_btn.connect("clicked", lambda b: self._flash_flags((0, 100, 255), "Blue Flag"))
        btn_box.append(blue_btn)

        red_btn = Gtk.Button(label="Red Flag")
        red_btn.set_size_request(105, 38)
        red_btn.connect("clicked", lambda b: self._flash_flags((255, 0, 0), "Red Flag"))
        btn_box.append(red_btn)

        off_btn = Gtk.Button(label="All Off")
        off_btn.set_size_request(90, 38)
        off_btn.connect("clicked", lambda b: self._turn_off_all_leds())
        btn_box.append(off_btn)

        flag_row.add_suffix(btn_box)
        flag_group.add(flag_row)
        self.add(flag_group)

    def set_telemetry_active(self, active: bool):
        """Telemetry engine state is managed autonomously by Auto-Profile."""
        pass

    def _on_mode_changed(self, dropdown, param):
        idx = dropdown.get_selected()
        self.telemetry_mgr.display_mode = "gear" if idx == 0 else "speed"

    def _on_simulate_lap(self, btn):
        if not self.device or not self.device.connected:
            if self.on_toast_requested:
                self.on_toast_requested("Device not connected!")
            return

        def _sim_worker():
            self.telemetry_mgr.enabled = True

            # 1. Idle in Neutral
            self.telemetry_mgr._handle_telemetry(rpm=1800, gear=0, speed_kmh=0, abs_active=False, tc_active=False)
            GLib.idle_add(self._set_gui_dots, 0)
            time.sleep(1.2)

            # 2. Acceleration Gear 1
            for r in range(2500, 8950, 160):
                pct = r / 9000.0
                dots = max(0, min(9, int(((pct - 0.65) / 0.33) * 9))) if pct >= 0.65 else 0
                self.telemetry_mgr._handle_telemetry(rpm=r, gear=1, speed_kmh=r * 0.012, abs_active=False, tc_active=False)
                GLib.idle_add(self._set_gui_dots, dots)
                time.sleep(0.04)

            time.sleep(0.25)

            # 3. Acceleration Gear 2
            for r in range(6200, 8950, 170):
                pct = r / 9000.0
                dots = max(0, min(9, int(((pct - 0.65) / 0.33) * 9))) if pct >= 0.65 else 0
                self.telemetry_mgr._handle_telemetry(rpm=r, gear=2, speed_kmh=r * 0.018, abs_active=False, tc_active=False)
                GLib.idle_add(self._set_gui_dots, dots)
                time.sleep(0.04)

            time.sleep(0.25)

            # 4. Acceleration Gear 3
            for r in range(6400, 8950, 170):
                pct = r / 9000.0
                dots = max(0, min(9, int(((pct - 0.65) / 0.33) * 9))) if pct >= 0.65 else 0
                self.telemetry_mgr._handle_telemetry(rpm=r, gear=3, speed_kmh=r * 0.024, abs_active=False, tc_active=False)
                GLib.idle_add(self._set_gui_dots, dots)
                time.sleep(0.04)

            # 5. Heavy Braking into Hairpin (ABS Yellow Flag Trigger)
            self.telemetry_mgr._handle_telemetry(rpm=5200, gear=2, speed_kmh=90, abs_active=True, tc_active=False)
            time.sleep(0.8)
            self.telemetry_mgr._handle_telemetry(rpm=3200, gear=1, speed_kmh=45, abs_active=True, tc_active=False)
            time.sleep(0.8)

            # 6. Idle in Neutral & Clear Flags
            self.telemetry_mgr._handle_telemetry(rpm=1800, gear=0, speed_kmh=0, abs_active=False, tc_active=False)
            self.device.set_flagleds([(0, 0, 0)] * 6)
            GLib.idle_add(self._set_gui_dots, 0)

        threading.Thread(target=_sim_worker, daemon=True).start()
        if self.on_toast_requested:
            self.on_toast_requested("Running Simulated AC Race Lap...")

    def _on_send_display(self, btn):
        text = self.disp_entry.get_text()
        if self.device and self.device.connected:
            self.device.set_display_text(text)
            if self.on_toast_requested:
                self.on_toast_requested(f"Sent '{text}' to Formula V2.5 OLED display")

    def _on_clear_display(self, btn):
        if self.device and self.device.connected:
            self.device.clear_display()
            if self.on_toast_requested:
                self.on_toast_requested("OLED display cleared")

    def _set_gui_dots(self, active_count, color_css=None):
        for i, dot in enumerate(self._led_dots):
            if i < active_count:
                dot.set_css_classes(["led-preview-dot"])
                if i < 3:
                    c = "#2ec27e"
                elif i < 6:
                    c = "#f6d32d"
                elif i < 8:
                    c = "#e01b24"
                else:
                    c = "#3584e4"
                dot.set_opacity(1.0)
            else:
                dot.set_css_classes(["led-preview-dot"])
                dot.set_opacity(0.3)

    def _on_test_revleds(self, btn):
        if not self.device or not self.device.connected:
            if self.on_toast_requested:
                self.on_toast_requested("Device not connected!")
            return

        def _worker():
            colors = [
                (0, 255, 0), (0, 255, 0), (0, 255, 0),
                (255, 255, 0), (255, 255, 0), (255, 255, 0),
                (255, 0, 0), (255, 0, 0), (0, 0, 255)
            ]
            for i in range(1, 10):
                current = colors[:i] + [(0, 0, 0)] * (9 - i)
                self.device.set_revleds(current)
                GLib.idle_add(self._set_gui_dots, i)
                time.sleep(0.1)

            for _ in range(2):
                self.device.set_revleds([(255, 255, 255)] * 9)
                GLib.idle_add(self._set_gui_dots, 9)
                time.sleep(0.12)
                self.device.set_revleds([(0, 0, 0)] * 9)
                GLib.idle_add(self._set_gui_dots, 0)
                time.sleep(0.12)

        threading.Thread(target=_worker, daemon=True).start()
        if self.on_toast_requested:
            self.on_toast_requested("Testing RevLED RPM climb sequence")

    def _flash_flags(self, rgb, label):
        if not self.device or not self.device.connected:
            return
        def _worker():
            for _ in range(3):
                self.device.set_flagleds([rgb] * 6)
                time.sleep(0.2)
                self.device.set_flagleds([(0, 0, 0)] * 6)
                time.sleep(0.15)
        threading.Thread(target=_worker, daemon=True).start()
        if self.on_toast_requested:
            self.on_toast_requested(f"Triggered {label} simulation")

    def _turn_off_all_leds(self):
        if self.device and self.device.connected:
            self.device.set_revleds([(0, 0, 0)] * 9)
            self.device.set_flagleds([(0, 0, 0)] * 6)
            self._set_gui_dots(0)
            if self.on_toast_requested:
                self.on_toast_requested("All rim LEDs turned off")
