"""
Calibration, Diagnostics & Force Feedback Motor Test Suite.
Matches Fanatec Control Panel calibration and motor diagnostic tabs.
"""

import threading
import time

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, GLib, Gtk

from fanalinux.ui.helpers import slider_cluster
from fanalinux.ui.widgets.wheel_dial import WheelDialWidget


class CalibrationView(Adw.PreferencesPage):
    def __init__(self, device, on_toast_requested=None):
        super().__init__()
        self.device = device
        self.on_toast_requested = on_toast_requested
        self.evdev_listener = None
        self._last_raw_steering = 32768
        self._abort_self_test = False
        self._self_test_running = False
        # Run generation: a restarted test bumps this so the stale worker
        # goes inert instead of fighting the new run.
        self._self_test_gen = 0


        self._build_ui()

    def set_evdev_listener(self, listener):
        self.evdev_listener = listener

    def update_rim(self, rim_info: dict):
        if hasattr(self, "wheel_dial") and self.wheel_dial:
            self.wheel_dial.set_rim(rim_info)

    def _build_ui(self):
        # 1. Force Feedback Motor & Vibration Test Suite
        ffb_group = Adw.PreferencesGroup()
        ffb_group.set_title("Force Feedback Motor &amp; Vibration Diagnostics")
        ffb_group.set_description(
            "Interactive hardware diagnostic suite to test direct drive torque, "
            "centering spring, friction, and vibration motors."
        )

        # Centering Spring Test
        spring_row = Adw.ActionRow()
        spring_row.set_title("Hardware Centering Spring")
        spring_row.set_subtitle("Engages direct-drive motor autocenter force pulling toward 0.0°")
        spring_row.set_icon_name("emblem-synchronizing-symbolic")

        def _on_spring_changed(v):
            spring_lbl.set_text(f"{int(v)}%")

        spring_box, self.spring_adj, spring_lbl = slider_cluster(
            10, 100, 5, 50, unit="%", width=220, badge_width=5,
            on_change=_on_spring_changed,
        )

        self.spring_sw = Gtk.Switch()
        self.spring_sw.set_valign(Gtk.Align.CENTER)
        self.spring_sw.connect("state-set", self._on_spring_toggled)

        spring_box.append(self.spring_sw)
        spring_row.add_suffix(spring_box)
        ffb_group.add(spring_row)

        # Dynamic Friction / Damping Test
        friction_row = Adw.ActionRow()
        friction_row.set_title("Mechanical Friction / Damping")
        friction_row.set_subtitle("Applies rotational resistance to feel motor damping while turning the wheel")
        friction_row.set_icon_name("preferences-system-symbolic")

        def _on_friction_changed(v):
            friction_lbl.set_text(f"{int(v)}%")

        friction_box, self.friction_adj, friction_lbl = slider_cluster(
            10, 100, 5, 40, unit="%", width=220, badge_width=5,
            on_change=_on_friction_changed,
        )

        self.friction_sw = Gtk.Switch()
        self.friction_sw.set_valign(Gtk.Align.CENTER)
        self.friction_sw.connect("state-set", self._on_friction_toggled)

        friction_box.append(self.friction_sw)
        friction_row.add_suffix(friction_box)
        ffb_group.add(friction_row)

        # Automated Full Hardware Self-Test (10s)
        self_test_row = Adw.ActionRow()
        self_test_row.set_title("Full Hardware Self-Test (10s)")
        self_test_row.set_subtitle("10-second automated sequence verifying RevLEDs, Flags, OLED, DD motor sweeps &amp; haptic rumble")
        self_test_row.set_icon_name("media-playback-start-symbolic")

        self.self_test_btn = Gtk.Button(label="Run Self-Test")
        self.self_test_btn.set_size_request(160, 42)
        self.self_test_btn.set_valign(Gtk.Align.CENTER)
        self.self_test_btn.add_css_class("suggested-action")
        self.self_test_btn.connect("clicked", self._on_self_test_clicked)
        self_test_row.add_suffix(self.self_test_btn)
        ffb_group.add(self_test_row)

        # Safety Force Cutoff Row
        stop_row = Adw.ActionRow()
        stop_row.set_title("Safety Force Cutoff")
        stop_row.set_subtitle("Immediately cancels and zeros all active torque, spring, and vibration outputs")
        stop_row.set_icon_name("process-stop-symbolic")

        stop_btn = Gtk.Button(label="Stop All Forces")
        stop_btn.set_size_request(160, 42)
        stop_btn.set_valign(Gtk.Align.CENTER)
        stop_btn.add_css_class("destructive-action")
        stop_btn.connect("clicked", self._on_emergency_stop_clicked)
        stop_row.add_suffix(stop_btn)
        ffb_group.add(stop_row)

        # 2. Wheel Center Calibration & Visual Dial (Right Column in Screenshot 2)
        center_group = Adw.PreferencesGroup()
        center_group.set_title("Wheel Center Calibration")
        center_group.set_description(
            "Recalibrates the motor optical/magnetic index zero point. "
            "Ensure your steering wheel is physically centered (0.0°) before triggering."
        )

        # Embedded 360° Circular Steering Visualizer Dial (Screenshot 2)
        self.wheel_dial = WheelDialWidget(
            on_calibrate_clicked=self._on_calibrate_clicked,
            on_reset_clicked=self._on_reset_clicked
        )
        center_group.add(self.wheel_dial)

        # Hardware shortcut helper row
        hw_tip_row = Adw.ActionRow()
        hw_tip_row.set_title("Hardware EEPROM Flash Shortcut")
        hw_tip_row.set_subtitle("To permanently flash center into base memory across all platforms: [Tuning Button] + [FunkySwitch Press]")
        hw_tip_row.set_icon_name("help-about-symbolic")
        center_group.add(hw_tip_row)

        # Pedal deadzone controls were removed: without Fanatec pedals on hand
        # there is no way to validate them, and display-only sliders lie.
        # Live pedal gauges in Overview stay (they show kernel truth).

        # Build Single Column Calibration Layout (Full Horizontal Space)
        self.add(ffb_group)
        self.add(center_group)

    def _on_spring_toggled(self, switch, state):
        if not self.device or not self.device.connected:
            if self.on_toast_requested:
                self.on_toast_requested("Device not connected!")
            return
        if state:
            strength = int(self.spring_adj.get_value())
            self.device.output_inhibited = False  # explicit re-arm after cutoff
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
            self.device.output_inhibited = False  # explicit re-arm after cutoff
            self.device.send_damper_friction(fric)
            if self.on_toast_requested:
                self.on_toast_requested(f"Motor friction resistance applied ({fric}%)")
        else:
            self.device.send_damper_friction(0)
            if self.on_toast_requested:
                self.on_toast_requested("Motor friction disabled")

    def _on_self_test_clicked(self, btn):
        if not self.device or not self.device.connected:
            if self.on_toast_requested:
                self.on_toast_requested("Device not connected!")
            return

        if self._self_test_running:
            if self.on_toast_requested:
                self.on_toast_requested("Self-test is already running!")
            return

        # Show Safety Warning Dialog
        root = self.get_root()
        dialog = Adw.MessageDialog(
            transient_for=root if isinstance(root, Gtk.Window) else None,
            heading="Full Hardware Self-Test (10s)",
            body="This will run an automated 10-second diagnostic verifying:\n\n"
                 "• RevLEDs, Flag clusters & OLED Display\n"
                 "• Direct Drive motor torque (Left/Right sweeps & Centering)\n"
                 "• Steering rim grip vibration & pedal haptic rumble\n\n"
                 "Please ensure the wheel rim is clear to rotate freely.\nDo you want to proceed?"
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("proceed", "Start Self-Test")
        dialog.set_response_appearance("proceed", Adw.ResponseAppearance.SUGGESTED)

        def _on_dialog_response(dlg, response_id):
            if response_id == "proceed":
                self._run_full_self_test()

        dialog.connect("response", _on_dialog_response)
        dialog.present()

    def _run_full_self_test(self):
        self._abort_self_test = False
        self._self_test_gen += 1
        gen = self._self_test_gen
        if self.device:
            self.device.output_inhibited = False  # deliberate force run re-arms
        self._self_test_running = True
        self.self_test_btn.set_sensitive(False)
        self.self_test_btn.set_label("Running (10s)...")

        def _worker():
            def live() -> bool:
                return gen == self._self_test_gen and not self._abort_self_test
            class _LiveDevice:
                """Device proxy: calls from a superseded run go inert."""
                def __init__(self, inner):
                    self._inner = inner
                def __getattr__(self, name):
                    fn = getattr(self._inner, name)
                    if not callable(fn):
                        return fn
                    def gated(*a, **k):
                        if live():
                            return fn(*a, **k)
                    return gated
            dev = _LiveDevice(self.device)
            def sleep_check(seconds: float) -> bool:
                end_t = time.time() + seconds
                while time.time() < end_t:
                    if not live():
                        return False
                    time.sleep(min(0.04, max(0.005, end_t - time.time())))
                return live()

            try:
                # -------------------------------------------------------------
                # PHASE 1: Displays & Multi-Color LEDs (0.0s - 3.2s)
                # -------------------------------------------------------------
                if self.on_toast_requested:
                    GLib.idle_add(self.on_toast_requested, "Self-Test (1/3): Testing RevLEDs, Flag clusters & OLED...")

                dev.set_display_text("TST")
                if not sleep_check(0.4):
                    return

                color_palette = [
                    (0, 255, 0), (0, 255, 0), (0, 255, 0),       # Green
                    (255, 200, 0), (255, 200, 0), (255, 200, 0), # Yellow
                    (255, 0, 0), (255, 0, 0), (0, 100, 255)      # Red / Blue
                ]

                # Sweep in 9 RevLEDs
                current_leds = [(0, 0, 0)] * 9
                for i in range(9):
                    if self._abort_self_test:
                        return
                    current_leds[i] = color_palette[i]
                    dev.set_revleds(current_leds)
                    if not sleep_check(0.12):
                        return

                # Flag LEDs cycle (3 left, 3 right)
                dev.set_display_text("LED")
                for c in [(255, 0, 0), (255, 200, 0), (0, 120, 255)]:
                    if self._abort_self_test:
                        return
                    dev.set_flagleds([c] * 6)
                    if not sleep_check(0.35):
                        return

                # All LEDs full bright white flash
                if self._abort_self_test:
                    return
                dev.set_revleds([(255, 255, 255)] * 9)
                dev.set_flagleds([(255, 255, 255)] * 6)
                if not sleep_check(0.4):
                    return

                # Clear LEDs
                dev.set_revleds([(0, 0, 0)] * 9)
                dev.set_flagleds([(0, 0, 0)] * 6)

                # -------------------------------------------------------------
                # PHASE 2: Direct Drive Motor Torque & Centering (3.2s - 6.8s)
                # -------------------------------------------------------------
                if self._abort_self_test:
                    return

                if self.on_toast_requested:
                    GLib.idle_add(self.on_toast_requested, "Self-Test (2/3): Direct Drive motor test: Left sweep, Right sweep & Centering...")

                dev.set_display_text("DD")

                # Smooth ramp Left (up to ~20% torque)
                for step in range(1, 11):
                    if self._abort_self_test:
                        return
                    force = int(-7000 * (step / 10.0))
                    dev.send_constant_force(force)
                    if not sleep_check(0.07):
                        return

                if not sleep_check(0.35):
                    return

                # Smooth ramp back to 0
                for step in range(10, -1, -1):
                    if self._abort_self_test:
                        return
                    force = int(-7000 * (step / 10.0))
                    dev.send_constant_force(force)
                    if not sleep_check(0.035):
                        return

                # Smooth ramp Right (up to ~20% torque)
                for step in range(1, 11):
                    if self._abort_self_test:
                        return
                    force = int(7000 * (step / 10.0))
                    dev.send_constant_force(force)
                    if not sleep_check(0.07):
                        return

                if not sleep_check(0.35):
                    return

                # Smooth ramp back to 0
                for step in range(10, -1, -1):
                    if self._abort_self_test:
                        return
                    force = int(7000 * (step / 10.0))
                    dev.send_constant_force(force)
                    if not sleep_check(0.035):
                        return

                # Centering spring check
                if self._abort_self_test:
                    return
                dev.send_centering_spring(50)
                if not sleep_check(0.8):
                    return
                dev.send_centering_spring(0)

                # -------------------------------------------------------------
                # PHASE 3: Tactile Rim Grip & Pedal Rumble (6.8s - 9.4s)
                # -------------------------------------------------------------
                if self._abort_self_test:
                    return

                if self.on_toast_requested:
                    GLib.idle_add(self.on_toast_requested, "Self-Test (3/3): Testing rim grip rumble & pedal haptic motors...")

                dev.set_display_text("VIB")

                # Left grip rumble (1.0s)
                dev.send_handle_vibration(180, 0)
                if not sleep_check(1.0):
                    return

                if self._abort_self_test:
                    return

                # Right grip rumble (1.0s)
                dev.send_handle_vibration(0, 180)
                if not sleep_check(1.0):
                    return

                if self._abort_self_test:
                    return

                # Both handles + base 18 Hz tactile pulse (0.6s)
                dev.send_handle_vibration(220, 220)
                end_vib = time.time() + 0.6
                half = (1.0 / 18.0) / 2.0
                while time.time() < end_vib and not self._abort_self_test:
                    dev.send_constant_force(4500)
                    if not sleep_check(half):
                        return
                    dev.send_constant_force(-4500)
                    if not sleep_check(half):
                        return

                # -------------------------------------------------------------
                # PHASE 4: Pass & Restoration (9.4s - 10.0s)
                # -------------------------------------------------------------
                dev.send_constant_force(0)
                dev.send_handle_vibration(0, 0)
                dev.send_centering_spring(0)
                dev.set_display_text("OK")
                if not sleep_check(0.6):
                    return
                dev.clear_display()

                if self.on_toast_requested:
                    GLib.idle_add(self.on_toast_requested, "Hardware Self-Test Complete: All displays, LEDs, DD motor, and haptic actuators passed!")

            finally:
                # Superseded runs own nothing: skip cleanup, the new run does it.
                if gen == self._self_test_gen:
                    self._self_test_running = False
                    try:
                        dev.stop_all_forces()
                        dev.set_revleds([(0, 0, 0)] * 9)
                        dev.set_flagleds([(0, 0, 0)] * 6)
                        dev.clear_display()
                    except Exception:
                        pass
                    GLib.idle_add(self.self_test_btn.set_sensitive, True)
                    GLib.idle_add(self.self_test_btn.set_label, "Run Self-Test")

        threading.Thread(target=_worker, daemon=True).start()

    def update_steering(self, norm_val: float, raw_val: int):
        self._last_raw_steering = raw_val
        active_sen = getattr(self.device, "active_sen", 900)
        max_deg = (active_sen / 2.0) if active_sen > 0 else 450.0
        deg = norm_val * max_deg
        GLib.idle_add(self.wheel_dial.set_angle, deg)

    def _on_emergency_stop_clicked(self, btn):
        self._abort_self_test = True
        self._self_test_gen += 1  # retire any running worker immediately
        self._self_test_running = False
        if hasattr(self, 'self_test_btn'):
            self.self_test_btn.set_sensitive(True)
            self.self_test_btn.set_label("Run Self-Test")
        if self.device:
            # Zeroes go out first, then the gate closes, atomically: background
            # engines (haptics, dynamic FFB) go silent until a switch or
            # self-test explicitly re-arms.
            self.device.emergency_stop()
            try:
                self.device.set_revleds([(0, 0, 0)] * 9)
                self.device.set_flagleds([(0, 0, 0)] * 6)
                self.device.clear_display()
            except Exception:
                pass
        self.spring_sw.set_active(False)
        self.friction_sw.set_active(False)
        if self.on_toast_requested:
            self.on_toast_requested("Emergency Cutoff: All forces, springs, and vibrations zeroed!")

    def _on_calibrate_clicked(self, btn=None):
        # 1. Update persistent software calibration offset in evdev listener
        if self.evdev_listener:
            self.evdev_listener.set_center_raw(self._last_raw_steering)

        # 2. Immediately snap visual dial to 0.0
        GLib.idle_add(self.wheel_dial.set_angle, 0.0)

        # 3. Physical visual confirmation on the wheel rim LEDs
        if self.device and self.device.connected:
            def _feedback():
                try:
                    self.device.set_display_text("CAL")
                    self.device.set_revleds([(0, 255, 0)] * 9)
                    time.sleep(0.8)
                    self.device.clear_display()
                    self.device.set_revleds([(0, 0, 0)] * 9)
                except Exception:
                    pass

            threading.Thread(target=_feedback, daemon=True).start()
            self.device.calibrate_center()

        if self.on_toast_requested:
            self.on_toast_requested(f"Wheel center calibrated to 0.0° (Raw: {self._last_raw_steering})!")

    def _on_reset_clicked(self, btn=None):
        if self.evdev_listener:
            self.evdev_listener.reset_center()

        GLib.idle_add(self.wheel_dial.set_angle, 0.0)

        if self.device and self.device.connected:
            def _feedback():
                try:
                    self.device.set_display_text("RST")
                    time.sleep(0.6)
                    self.device.clear_display()
                except Exception:
                    pass

            threading.Thread(target=_feedback, daemon=True).start()

        if self.on_toast_requested:
            self.on_toast_requested("Steering center reset to factory default (32768)!")
