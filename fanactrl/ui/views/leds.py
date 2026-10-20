"""
LEDs & Display Telemetry View (FanaLab Equivalent).
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
import threading
import time


class LedsView(Gtk.Box):
    def __init__(self, device, on_toast_requested=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.device = device
        self.on_toast_requested = on_toast_requested

        self.set_margin_top(24)
        self.set_margin_bottom(24)
        self.set_margin_start(24)
        self.set_margin_end(24)

        self._build_ui()

    def _build_ui(self):
        # 1. 1-inch OLED Display Group
        oled_group = Adw.PreferencesGroup()
        oled_group.set_title("OLED Rim Display")

        disp_row = Adw.ActionRow()
        disp_row.set_title("Display String (1 - 3 Characters)")
        disp_row.set_subtitle("Writes directly to the Formula V2.5 center OLED screen")

        self.disp_entry = Gtk.Entry()
        self.disp_entry.set_max_length(3)
        self.disp_entry.set_placeholder_text("GEA")
        self.disp_entry.set_text("F1")
        self.disp_entry.set_width_chars(5)
        disp_row.add_suffix(self.disp_entry)

        send_btn = Gtk.Button(label="Send")
        send_btn.add_css_class("suggested-action")
        send_btn.connect("clicked", self._on_send_display)
        disp_row.add_suffix(send_btn)

        clear_btn = Gtk.Button(label="Clear")
        clear_btn.connect("clicked", self._on_clear_display)
        disp_row.add_suffix(clear_btn)

        oled_group.add(disp_row)
        self.append(oled_group)

        # 2. RevLEDs (9 Multi-Color LEDs) Group
        rev_group = Adw.PreferencesGroup()
        rev_group.set_title("RPM RevLEDs (9 LEDs)")

        rev_row = Adw.ActionRow()
        rev_row.set_title("RevLED Light Pattern")
        rev_row.set_subtitle("RGB Multi-Color Spectrum (Green -> Yellow -> Red / Blue)")

        test_rev_btn = Gtk.Button(label="Test RPM Climb")
        test_rev_btn.add_css_class("pill")
        test_rev_btn.connect("clicked", self._on_test_revleds)
        rev_row.add_suffix(test_rev_btn)
        rev_group.add(rev_row)

        self.append(rev_group)

        # 3. Flag LEDs (6 Multi-Color LEDs: 3 Left, 3 Right)
        flag_group = Adw.PreferencesGroup()
        flag_group.set_title("Side Flag LEDs (6 LEDs)")

        flag_row = Adw.ActionRow()
        flag_row.set_title("Simulated Race Flag Alerts")
        flag_row.set_subtitle("Triggers the left and right multi-color flag clusters")

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        yellow_btn = Gtk.Button(label="Yellow Flag")
        yellow_btn.connect("clicked", lambda b: self._flash_flags((255, 255, 0), "Yellow Flag"))
        btn_box.append(yellow_btn)

        blue_btn = Gtk.Button(label="Blue Flag")
        blue_btn.connect("clicked", lambda b: self._flash_flags((0, 100, 255), "Blue Flag"))
        btn_box.append(blue_btn)

        red_btn = Gtk.Button(label="Red Flag")
        red_btn.connect("clicked", lambda b: self._flash_flags((255, 0, 0), "Red Flag"))
        btn_box.append(red_btn)

        off_btn = Gtk.Button(label="All Off")
        off_btn.connect("clicked", lambda b: self._turn_off_all_leds())
        btn_box.append(off_btn)

        flag_row.add_suffix(btn_box)
        flag_group.add(flag_row)

        self.append(flag_group)

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
                time.sleep(0.1)

            # Flash all white
            for _ in range(2):
                self.device.set_revleds([(255, 255, 255)] * 9)
                time.sleep(0.12)
                self.device.set_revleds([(0, 0, 0)] * 9)
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
            if self.on_toast_requested:
                self.on_toast_requested("All rim LEDs turned off")
