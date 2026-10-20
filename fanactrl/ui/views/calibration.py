"""
Calibration, Deadzones & Shifter Wizard View.
Matches Fanatec Control Panel calibration tabs.
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
        self._current_shifter_step = 1

        self._build_ui()

    def _build_ui(self):
        # 1. Wheel Center Calibration
        center_group = Adw.PreferencesGroup()
        center_group.set_title("Wheel Center Calibration")
        center_group.set_description(
            "Recalibrates the motor optical/magnetic index zero point. "
            "Ensure your steering wheel is physically centered before triggering."
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

        # 2. Pedal Min / Max Deadzones
        pedal_group = Adw.PreferencesGroup()
        pedal_group.set_title("Pedal Deadzones &amp; Calibration")
        pedal_group.set_description("Configure software deadzone thresholds for throttle, brake, and clutch")

        def make_deadzone_row(title, subtitle, default_val=2):
            row = Adw.ActionRow()
            row.set_title(title)
            row.set_subtitle(subtitle)

            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.set_valign(Gtk.Align.CENTER)

            lbl = Gtk.Label(label=f"{default_val}%")
            lbl.set_width_chars(5)
            lbl.add_css_class("val-badge")

            adj = Gtk.Adjustment(value=default_val, lower=0, upper=25, step_increment=1, page_increment=5)
            scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
            scale.set_size_request(180, -1)
            scale.set_valign(Gtk.Align.CENTER)
            scale.set_draw_value(False)
            adj.connect("value-changed", lambda a: lbl.set_text(f"{int(a.get_value())}%"))

            box.append(lbl)
            box.append(scale)
            row.add_suffix(box)
            return row

        pedal_group.add(make_deadzone_row("Throttle Lower Deadzone", "Prevents micro-inputs while resting your foot on the accelerator", 2))
        pedal_group.add(make_deadzone_row("Brake Lower Deadzone", "Initial pedal travel deadband before hydraulic/load-cell engagement", 3))
        pedal_group.add(make_deadzone_row("Clutch Engagement Threshold", "Disengagement buffer zone for launch control", 5))

        self.add(pedal_group)

        # 3. H-Pattern Shifter Calibration Wizard
        shifter_group = Adw.PreferencesGroup()
        shifter_group.set_title("ClubSport H-Pattern Shifter Calibration")
        shifter_group.set_description("Guided wizard to calibrate the Hall sensors for gears 1 through 7 and Reverse")

        self.shifter_row = Adw.ActionRow()
        self.shifter_row.set_title("Shifter Calibration Wizard")
        self.shifter_row.set_subtitle("Shift into 1st Gear, then click 'Confirm Gear 1'")

        self.shifter_btn = Gtk.Button(label="Confirm Gear 1")
        self.shifter_btn.set_size_request(160, 42)
        self.shifter_btn.set_valign(Gtk.Align.CENTER)
        self.shifter_btn.add_css_class("suggested-action")
        self.shifter_btn.connect("clicked", self._on_shifter_step_clicked)
        self.shifter_row.add_suffix(self.shifter_btn)
        shifter_group.add(self.shifter_row)

        self.add(shifter_group)

        # 4. Firmware Versions Card
        fw_group = Adw.PreferencesGroup()
        fw_group.set_title("Hardware Firmware Versions")
        fw_group.set_description("Reported microcontroller and motor firmware revisions")

        def make_fw_row(title, version_str):
            row = Adw.ActionRow()
            row.set_title(title)
            lbl = Gtk.Label(label=version_str)
            lbl.add_css_class("val-badge")
            lbl.add_css_class("accent")
            row.add_suffix(lbl)
            return row

        fw_group.add(make_fw_row("Wheelbase Mainboard Firmware", self.device.firmware_base if self.device else "1.1.8.4"))
        fw_group.add(make_fw_row("DirectDrive Motor Controller Firmware", self.device.firmware_motor if self.device else "1.0.3.2"))
        fw_group.add(make_fw_row("Formula V2.5 Steering Rim Firmware", f"v{self.device.firmware_rim}" if self.device else "v45"))

        self.add(fw_group)

    def _on_calibrate_clicked(self, btn):
        if not self.device or not self.device.connected:
            if self.on_toast_requested:
                self.on_toast_requested("Device not connected!")
            return

        self.device.calibrate_center()
        if self.on_toast_requested:
            self.on_toast_requested("Center calibration command sent to CSL DD!")

    def _on_shifter_step_clicked(self, btn):
        if not self.device or not self.device.connected:
            if self.on_toast_requested:
                self.on_toast_requested("Device not connected!")
            return

        gear_names = ["Reverse", "Gear 1", "Gear 2", "Gear 3", "Gear 4", "Gear 5", "Gear 6", "Gear 7"]
        self.device.calibrate_shifter_step(self._current_shifter_step)

        if self._current_shifter_step < 7:
            self._current_shifter_step += 1
            next_gear = gear_names[self._current_shifter_step]
            self.shifter_row.set_subtitle(f"Now shift into {next_gear}, then click 'Confirm {next_gear}'")
            self.shifter_btn.set_label(f"Confirm {next_gear}")
        elif self._current_shifter_step == 7:
            self._current_shifter_step = 0 # Reverse next
            self.shifter_row.set_subtitle("Now push down and shift into Reverse, then click 'Confirm Reverse'")
            self.shifter_btn.set_label("Confirm Reverse")
        else:
            self._current_shifter_step = 1
            self.shifter_row.set_subtitle("Calibration complete! Shifter is calibrated and indexed.")
            self.shifter_btn.set_label("Restart Wizard")
            if self.on_toast_requested:
                self.on_toast_requested("H-Pattern Shifter Calibration Complete!")
