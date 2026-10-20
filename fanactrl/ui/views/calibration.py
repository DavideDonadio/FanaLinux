"""
Calibration & Diagnostics View: Center Calibration, Hardware Info.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib


class CalibrationView(Adw.PreferencesPage):
    def __init__(self, device, on_toast_requested=None):
        super().__init__()
        self.device = device
        self.on_toast_requested = on_toast_requested

        self._build_ui()

    def _build_ui(self):
        # 1. Wheel Center Calibration
        center_group = Adw.PreferencesGroup()
        center_group.set_title("Wheel Center Calibration")
        center_group.set_description(
            "Recalibrates the optical/magnetic motor index zero point. "
            "Make sure your steering wheel is physically leveled and centered before triggering."
        )

        cal_row = Adw.ActionRow()
        cal_row.set_title("Calibrate Center (0.0° Index)")
        cal_row.set_subtitle("Writes persistent zero-position into base non-volatile flash")

        cal_btn = Gtk.Button(label="Calibrate Center")
        cal_btn.set_size_request(170, 42)
        cal_btn.set_valign(Gtk.Align.CENTER)
        cal_btn.add_css_class("destructive-action")
        cal_btn.connect("clicked", self._on_calibrate_clicked)
        cal_row.add_suffix(cal_btn)
        center_group.add(cal_row)

        self.add(center_group)

        # 2. Diagnostics & Raw Protocol Information
        diag_group = Adw.PreferencesGroup()
        diag_group.set_title("Diagnostics and Protocol")
        diag_group.set_description("Underlying Linux kernel and USB HID transport parameters")

        def make_diag_row(title, subtitle, icon_name=None):
            row = Adw.ActionRow()
            row.set_title(title)
            row.set_subtitle(subtitle)
            if icon_name:
                row.set_icon_name(icon_name)
            return row

        diag_group.add(make_diag_row(
            "USB Vendor / Product ID",
            "0x0EB7 : 0x0020 (CSL DD Direct Drive Native Mode)",
            "preferences-desktop-keyboard-shortcuts-symbolic"
        ))
        diag_group.add(make_diag_row(
            "HID Communication Pipe",
            "Report ID 0x01 (Evdev/Standard), Report ID 0xFF (Vendor DirectDrive)",
            "network-transmit-receive-symbolic"
        ))
        diag_group.add(make_diag_row(
            "Active Kernel Driver",
            "Native hidraw + evdev event stream (Zero kernel unbind)",
            "security-high-symbolic"
        ))

        self.add(diag_group)

    def _on_calibrate_clicked(self, btn):
        if not self.device or not self.device.connected:
            if self.on_toast_requested:
                self.on_toast_requested("Device not connected!")
            return

        self.device.calibrate_center()
        if self.on_toast_requested:
            self.on_toast_requested("Center calibration command sent to CSL DD!")
