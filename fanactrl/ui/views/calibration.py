"""
Calibration & Diagnostics View: Center Calibration, Hardware Info.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib


class CalibrationView(Gtk.Box):
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
        cal_btn.add_css_class("destructive-action")
        cal_btn.connect("clicked", self._on_calibrate_clicked)
        cal_row.add_suffix(cal_btn)
        center_group.add(cal_row)

        self.append(center_group)

        # 2. Diagnostics & Raw Protocol Information
        diag_group = Adw.PreferencesGroup()
        diag_group.set_title("Diagnostics & Protocol")

        vid_row = Adw.ActionRow()
        vid_row.set_title("USB Vendor / Product ID")
        vid_row.set_subtitle("0x0EB7 : 0x0020 (CSL DD Direct Drive Native Mode)")
        diag_group.add(vid_row)

        pipe_row = Adw.ActionRow()
        pipe_row.set_title("HID Communication Pipe")
        pipe_row.set_subtitle("Report ID 0x01 (Evdev/Standard), Report ID 0xFF (Vendor DirectDrive)")
        diag_group.add(pipe_row)

        driver_row = Adw.ActionRow()
        driver_row.set_title("Active Kernel Driver")
        driver_row.set_subtitle("hid-generic + userspace /dev/hidraw8 (Non-root uaccess)")
        diag_group.add(driver_row)

        self.append(diag_group)

    def _on_calibrate_clicked(self, btn):
        if not self.device or not self.device.connected:
            if self.on_toast_requested:
                self.on_toast_requested("Device not connected!")
            return

        self.device.calibrate_center()
        if self.on_toast_requested:
            self.on_toast_requested("Center calibration command sent to CSL DD!")
