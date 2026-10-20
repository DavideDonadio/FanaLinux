"""
LEDs & Display Telemetry View (FanaLab Equivalent).
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
import threading
import time


class LedsView(Adw.PreferencesPage):
    def __init__(self, device, on_toast_requested=None):
        super().__init__()
        self.device = device
        self.on_toast_requested = on_toast_requested
        self._led_dots = []

        self._build_ui()

    def _build_ui(self):
        # 1. 1-inch OLED Display Group
        oled_group = Adw.PreferencesGroup()
        oled_group.set_title("OLED Rim Display")
        oled_group.set_description("Write custom strings or simulated telemetry to the Formula V2.5 center display")

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

        # 2. RevLEDs (9 Multi-Color LEDs) Group
        rev_group = Adw.PreferencesGroup()
        rev_group.set_title("RPM RevLEDs (9 LEDs)")
        rev_group.set_description("Sequential multi-color shift indicators (Green -> Yellow -> Red / Blue)")

        rev_row = Adw.ActionRow()
        rev_row.set_title("RevLED Light Strip")
        rev_row.set_subtitle("Interactive hardware test pattern")

        rev_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        rev_box.set_valign(Gtk.Align.CENTER)

        # Visual preview dots
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

        # 3. Flag LEDs (6 Multi-Color LEDs: 3 Left, 3 Right)
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
                # Color based on index
                if i < 3:
                    c = "#2ec27e" # Green
                elif i < 6:
                    c = "#f6d32d" # Yellow
                elif i < 8:
                    c = "#e01b24" # Red
                else:
                    c = "#3584e4" # Blue
                if color_css:
                    c = color_css
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

            # Flash all white twice
            for _ in range(2):
                self.device.set_revleds([(255, 255, 255)] * 9)
                GLib.idle_add(self._set_gui_dots, 9, "#ffffff")
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
