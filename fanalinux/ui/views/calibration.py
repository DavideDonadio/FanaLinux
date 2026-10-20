"""
Calibration, Diagnostics & Force Feedback Motor Test Suite.
Matches Fanatec Control Panel calibration and motor diagnostic tabs.
"""

import time
import threading
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
        # 1. Force Feedback Motor & Vibration Test Suite
        ffb_group = Adw.PreferencesGroup()
        ffb_group.set_title("Force Feedback Motor &amp; Vibration Diagnostics")
        ffb_group.set_description(
            "Interactive hardware diagnostic suite to test direct drive motor torque, "
            "centering spring return, dynamic mechanical friction, and rim grip vibration motors."
        )

        # Centering Spring Test
        spring_row = Adw.ActionRow()
        spring_row.set_title("Hardware Centering Spring")
        spring_row.set_subtitle("Engages direct-drive motor autocenter force pulling toward 0.0°")
        spring_row.set_icon_name("emblem-synchronizing-symbolic")

        spring_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        spring_box.set_valign(Gtk.Align.CENTER)

        spring_lbl = Gtk.Label(label="50%")
        spring_lbl.set_width_chars(5)
        spring_lbl.add_css_class("val-badge")

        self.spring_adj = Gtk.Adjustment(value=50, lower=10, upper=100, step_increment=5, page_increment=20)
        spring_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.spring_adj)
        spring_scale.set_size_request(150, -1)
        spring_scale.set_valign(Gtk.Align.CENTER)
        spring_scale.set_draw_value(False)
        self.spring_adj.connect("value-changed", lambda a: spring_lbl.set_text(f"{int(a.get_value())}%"))

        self.spring_sw = Gtk.Switch()
        self.spring_sw.set_valign(Gtk.Align.CENTER)
        self.spring_sw.connect("state-set", self._on_spring_toggled)

        spring_box.append(spring_lbl)
        spring_box.append(spring_scale)
        spring_box.append(self.spring_sw)
        spring_row.add_suffix(spring_box)
        ffb_group.add(spring_row)

        # Dynamic Friction / Damping Test
        friction_row = Adw.ActionRow()
        friction_row.set_title("Mechanical Friction / Damping")
        friction_row.set_subtitle("Applies rotational resistance to feel motor damping while turning the wheel")
        friction_row.set_icon_name("preferences-system-symbolic")

        friction_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        friction_box.set_valign(Gtk.Align.CENTER)

        friction_lbl = Gtk.Label(label="40%")
        friction_lbl.set_width_chars(5)
        friction_lbl.add_css_class("val-badge")

        self.friction_adj = Gtk.Adjustment(value=40, lower=10, upper=100, step_increment=5, page_increment=20)
        friction_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.friction_adj)
        friction_scale.set_size_request(150, -1)
        friction_scale.set_valign(Gtk.Align.CENTER)
        friction_scale.set_draw_value(False)
        self.friction_adj.connect("value-changed", lambda a: friction_lbl.set_text(f"{int(a.get_value())}%"))

        self.friction_sw = Gtk.Switch()
        self.friction_sw.set_valign(Gtk.Align.CENTER)
        self.friction_sw.connect("state-set", self._on_friction_toggled)

        friction_box.append(friction_lbl)
        friction_box.append(friction_scale)
        friction_box.append(self.friction_sw)
        friction_row.add_suffix(friction_box)
        ffb_group.add(friction_row)

        # Motor Torque Pulse Test
        torque_row = Adw.ActionRow()
        torque_row.set_title("Motor Torque Pulse Test")
        torque_row.set_subtitle("Gently pulls wheel left then right (25% torque) to verify direct drive motor output")
        torque_row.set_icon_name("media-playback-start-symbolic")

        torque_btn = Gtk.Button(label="Test Motor Torque")
        torque_btn.set_size_request(160, 42)
        torque_btn.set_valign(Gtk.Align.CENTER)
        torque_btn.add_css_class("suggested-action")
        torque_btn.connect("clicked", self._on_torque_test_clicked)
        torque_row.add_suffix(torque_btn)
        ffb_group.add(torque_row)

        # Handle Grip Vibration Test
        rumble_row = Adw.ActionRow()
        rumble_row.set_title("Rim Handle Vibration Test")
        rumble_row.set_subtitle("Fires test pulses on Formula V2.5 left and right handle vibration motors")
        rumble_row.set_icon_name("audio-volume-high-symbolic")

        rumble_btn = Gtk.Button(label="Test Grip Rumble")
        rumble_btn.set_size_request(150, 42)
        rumble_btn.set_valign(Gtk.Align.CENTER)
        rumble_btn.connect("clicked", self._on_rumble_test_clicked)
        rumble_row.add_suffix(rumble_btn)
        ffb_group.add(rumble_row)

        # Safety Force Cutoff Row
        stop_row = Adw.ActionRow()
        stop_row.set_title("Safety Force Cutoff")
        stop_row.set_subtitle("Immediately cancels and zeros all active torque, spring, and vibration outputs")

        stop_btn = Gtk.Button(label="Stop All Forces")
        stop_btn.set_size_request(160, 42)
        stop_btn.set_valign(Gtk.Align.CENTER)
        stop_btn.add_css_class("destructive-action")
        stop_btn.connect("clicked", self._on_emergency_stop_clicked)
        stop_row.add_suffix(stop_btn)
        ffb_group.add(stop_row)

        self.add(ffb_group)

        # 2. Wheel Center Calibration
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

        # 3. Pedal Min / Max Deadzones
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

        # 4. H-Pattern Shifter Calibration Wizard
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

        # 5. Firmware Versions Card
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

    def _on_spring_toggled(self, switch, state):
        if not self.device or not self.device.connected:
            if self.on_toast_requested:
                self.on_toast_requested("Device not connected!")
            return
        if state:
            strength = int(self.spring_adj.get_value())
            self.device.send_centering_spring(strength)
            if self.on_toast_requested:
                self.on_toast_requested(f"Centering spring engaged ({strength}%)")
        else:
            self.device.send_centering_spring(0)
            if self.on_toast_requested:
                self.on_toast_requested("Centering spring disabled")

    def _on_friction_toggled(self, switch, state):
        if not self.device or not self.device.connected:
            if self.on_toast_requested:
                self.on_toast_requested("Device not connected!")
            return
        if state:
            fric = int(self.friction_adj.get_value())
            self.device.send_damper_friction(fric)
            if self.on_toast_requested:
                self.on_toast_requested(f"Motor friction resistance applied ({fric}%)")
        else:
            self.device.send_damper_friction(0)
            if self.on_toast_requested:
                self.on_toast_requested("Motor friction disabled")

    def _on_torque_test_clicked(self, btn):
        if not self.device or not self.device.connected:
            if self.on_toast_requested:
                self.on_toast_requested("Device not connected!")
            return

        # Show Safety Warning Dialog
        root = self.get_root()
        dialog = Adw.MessageDialog(
            transient_for=root if isinstance(root, Gtk.Window) else None,
            heading="Motor Torque Safety Warning",
            body="Please ensure your hands are clear or hold the wheel rim firmly.\n\n"
                 "The direct drive motor will apply a gentle alternating torque (left, then right) "
                 "for approximately 2 seconds.\n\nDo you want to proceed?"
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("proceed", "Proceed with Test")
        dialog.set_response_appearance("proceed", Adw.ResponseAppearance.SUGGESTED)

        def _on_dialog_response(dlg, response_id):
            if response_id == "proceed":
                self._run_torque_sequence()

        dialog.connect("response", _on_dialog_response)
        dialog.present()

    def _run_torque_sequence(self):
        def _worker():
            if self.on_toast_requested:
                GLib.idle_add(self.on_toast_requested, "Testing motor torque: Pulling Left...")
            # Left torque (~23% holding force)
            self.device.send_constant_force(-7500)
            time.sleep(0.8)

            # Center pause
            self.device.send_constant_force(0)
            time.sleep(0.25)

            if self.on_toast_requested:
                GLib.idle_add(self.on_toast_requested, "Testing motor torque: Pulling Right...")
            # Right torque (~23% holding force)
            self.device.send_constant_force(7500)
            time.sleep(0.8)

            # Zero force
            self.device.send_constant_force(0)
            if self.on_toast_requested:
                GLib.idle_add(self.on_toast_requested, "Motor torque test complete! Forces zeroed.")

        threading.Thread(target=_worker, daemon=True).start()

    def _on_rumble_test_clicked(self, btn):
        if not self.device or not self.device.connected:
            if self.on_toast_requested:
                self.on_toast_requested("Device not connected!")
            return

        def _worker():
            # Left grip
            self.device.send_handle_vibration(left=190, right=0)
            time.sleep(0.4)
            # Right grip
            self.device.send_handle_vibration(left=0, right=190)
            time.sleep(0.4)
            # Both grips
            self.device.send_handle_vibration(left=220, right=220)
            time.sleep(0.5)
            # Stop
            self.device.send_handle_vibration(left=0, right=0)
            if self.on_toast_requested:
                GLib.idle_add(self.on_toast_requested, "Rim grip vibration test completed.")

        threading.Thread(target=_worker, daemon=True).start()
        if self.on_toast_requested:
            self.on_toast_requested("Testing Formula V2.5 handle grip vibration motors...")

    def _on_emergency_stop_clicked(self, btn):
        if self.device:
            self.device.stop_all_forces()
        self.spring_sw.set_active(False)
        self.friction_sw.set_active(False)
        if self.on_toast_requested:
            self.on_toast_requested("Emergency Cutoff: All forces, springs, and vibrations zeroed!")

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
