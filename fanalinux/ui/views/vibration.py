"""
Vibration View: Telemetry-Driven Haptic Feedback & Dynamic Rim/Pedal Vibration.
Matches the official Fanatec App / FanaLab Vibration tab.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
from typing import Optional, Callable

from fanalinux.core.vibration import VibrationSettings, load_vibration_settings, save_vibration_settings


class VibrationView(Adw.PreferencesPage):
    def __init__(self, device, haptic_engine=None, on_toast_requested: Optional[Callable[[str], None]] = None):
        super().__init__()
        self.device = device
        self.haptic_engine = haptic_engine
        self.on_toast_requested = on_toast_requested
        self.settings: VibrationSettings = self.haptic_engine.settings if self.haptic_engine else load_vibration_settings()

        self._controls = {}
        self._build_ui()

    def _build_ui(self):
        # 1. Top Controls: Reset & Quick Test
        top_group = Adw.PreferencesGroup()
        top_group.set_title("Vibration Values")
        top_group.set_description(
            "Configure real-time haptic feedback sent to the direct drive motor, rim grips, "
            "and peripheral pedals based on in-game vehicle telemetry."
        )

        top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        top_box.set_halign(Gtk.Align.END)
        top_box.set_margin_top(4)
        top_box.set_margin_bottom(8)

        reset_btn = Gtk.Button(label="Reset Defaults")
        reset_btn.set_size_request(130, 38)
        reset_btn.set_valign(Gtk.Align.CENTER)
        reset_btn.connect("clicked", self._on_reset_clicked)
        top_box.append(reset_btn)

        test_btn = Gtk.Button(label="Test Vibration")
        test_btn.set_size_request(130, 38)
        test_btn.set_valign(Gtk.Align.CENTER)
        test_btn.add_css_class("suggested-action")
        test_btn.connect("clicked", self._on_test_clicked)
        top_box.append(test_btn)

        top_group.add(top_box)
        self.add(top_group)

        # 2. Column 1: Braking & Engine Dynamics
        col1_group = Adw.PreferencesGroup()
        col1_group.set_title("Braking &amp; Engine")
        self._build_abs_section(col1_group)
        self._build_engine_section(col1_group)
        self._build_rev_limiter_section(col1_group)
        self.add(col1_group)

        # 3. Column 2: Suspension & Chassis Dynamics
        col2_group = Adw.PreferencesGroup()
        col2_group.set_title("Suspension &amp; Chassis Dynamics")
        self._build_suspension_section(col2_group)
        self._build_understeer_section(col2_group)
        self._build_oversteer_section(col2_group)
        self.add(col2_group)

        # 4. Column 3: Traction & Tire Grip
        col3_group = Adw.PreferencesGroup()
        col3_group.set_title("Traction &amp; Tire Grip")
        self._build_tc_section(col3_group)
        self._build_wheel_lock_section(col3_group)
        self._build_wheel_spin_section(col3_group)
        self.add(col3_group)

    # ----------------- Section Builders -----------------

    def _build_abs_section(self, group: Adw.PreferencesGroup):
        expander = Adw.ExpanderRow()
        expander.set_title("ABS Vibration")
        expander.set_subtitle("Tactile feedback triggered when anti-lock brakes engage under heavy deceleration")
        sw = self._add_toggle_prefix(expander, "abs_enabled")

        self._add_slider_row(expander, "abs_strength", "Vibration Strength", 1, 10, 1, "")
        self._add_slider_row(expander, "abs_duration", "Vibration Duration", 20, 300, 10, "ms")
        group.add(expander)

    def _build_engine_section(self, group: Adw.PreferencesGroup):
        expander = Adw.ExpanderRow()
        expander.set_title("Engine Vibration")
        expander.set_subtitle("Continuous subtle engine rumble scaled with vehicle engine RPM")
        sw = self._add_toggle_prefix(expander, "engine_enabled")

        self._add_slider_row(expander, "engine_strength", "Vibration Strength", 1, 10, 1, "")
        self._add_slider_row(expander, "engine_initial", "Initial Vibration", 0, 100, 5, "%")
        group.add(expander)

    def _build_rev_limiter_section(self, group: Adw.PreferencesGroup):
        expander = Adw.ExpanderRow()
        expander.set_title("Rev Limiter Vibration")
        expander.set_subtitle("Sharp rhythmic vibration shudder when approaching maximum engine revs")
        sw = self._add_toggle_prefix(expander, "rev_enabled")

        self._add_slider_row(expander, "rev_strength", "Vibration Strength", 1, 10, 1, "")
        self._add_slider_row(expander, "rev_threshold", "Threshold", 80.0, 100.0, 0.5, "%", is_float=True)
        group.add(expander)

    def _build_suspension_section(self, group: Adw.PreferencesGroup):
        expander = Adw.ExpanderRow()
        expander.set_title("Suspension Travel Vibration")
        expander.set_subtitle("Simulates curb strikes and rough road surface displacements")
        sw = self._add_toggle_prefix(expander, "suspension_enabled")

        self._add_slider_row(expander, "suspension_strength", "Vibration Strength", 1, 10, 1, "")
        self._add_slider_row(expander, "suspension_threshold", "Threshold", 0.1, 50.0, 0.5, "%", is_float=True)
        group.add(expander)

    def _build_understeer_section(self, group: Adw.PreferencesGroup):
        expander = Adw.ExpanderRow()
        expander.set_title("Understeer Vibration")
        expander.set_subtitle("Alerts you when front tires exceed grip angle and scrub across asphalt")
        sw = self._add_toggle_prefix(expander, "understeer_enabled")

        self._add_slider_row(expander, "understeer_strength", "Vibration Strength", 1, 10, 1, "")
        self._add_slider_row(expander, "understeer_friction_limit", "Friction Limit", 0.0, 30.0, 0.5, "°", is_float=True)
        group.add(expander)

    def _build_oversteer_section(self, group: Adw.PreferencesGroup):
        expander = Adw.ExpanderRow()
        expander.set_title("Oversteer Vibration")
        expander.set_subtitle("Alerts you when rear slip angle exceeds recovery threshold (rear slide)")
        sw = self._add_toggle_prefix(expander, "oversteer_enabled")

        self._add_slider_row(expander, "oversteer_strength", "Vibration Strength", 1, 10, 1, "")
        self._add_slider_row(expander, "oversteer_friction_limit", "Friction Limit", 0.0, 30.0, 0.5, "°", is_float=True)
        group.add(expander)

    def _build_tc_section(self, group: Adw.PreferencesGroup):
        expander = Adw.ExpanderRow()
        expander.set_title("Traction Control Vibration")
        expander.set_subtitle("Tactile pulse when ECU traction control cuts engine power during acceleration")
        sw = self._add_toggle_prefix(expander, "tc_enabled")

        self._add_slider_row(expander, "tc_strength", "Vibration Strength", 1, 10, 1, "")
        self._add_slider_row(expander, "tc_duration", "Vibration Duration", 20, 300, 10, "ms")
        group.add(expander)

    def _build_wheel_lock_section(self, group: Adw.PreferencesGroup):
        expander = Adw.ExpanderRow()
        expander.set_title("Wheel Lock Vibration")
        expander.set_subtitle("Direct tactile shudder whenever individual tires lock up under braking")
        sw = self._add_toggle_prefix(expander, "wheel_lock_enabled")

        self._add_slider_row(expander, "wheel_lock_strength", "Vibration Strength", 1, 10, 1, "")
        group.add(expander)

    def _build_wheel_spin_section(self, group: Adw.PreferencesGroup):
        expander = Adw.ExpanderRow()
        expander.set_title("Wheel Spin Vibration")
        expander.set_subtitle("Tactile warning when driven tires break traction and spin faster than car speed")
        sw = self._add_toggle_prefix(expander, "wheel_spin_enabled")

        self._add_slider_row(expander, "wheel_spin_strength", "Vibration Strength", 1, 10, 1, "")
        group.add(expander)

    # ----------------- UI Helpers -----------------

    def _add_toggle_prefix(self, row: Adw.ExpanderRow, attr_name: str) -> Gtk.Switch:
        current_val = getattr(self.settings, attr_name, True)
        sw = Gtk.Switch()
        sw.set_active(bool(current_val))
        sw.set_valign(Gtk.Align.CENTER)

        def _on_toggled(switch, state):
            setattr(self.settings, attr_name, switch.get_active())
            self._save()

        sw.connect("state-set", _on_toggled)
        row.add_suffix(sw)
        self._controls[attr_name] = sw
        return sw

    def _add_slider_row(self, expander: Adw.ExpanderRow, attr_name: str, title: str,
                         min_val: float, max_val: float, step: float, unit: str, is_float: bool = False):
        row = Adw.ActionRow()
        row.set_title(title)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        box.set_valign(Gtk.Align.CENTER)

        current_val = getattr(self.settings, attr_name, min_val)
        display_txt = f"{current_val:.1f}{unit}" if is_float else f"{int(current_val)}{unit}"
        lbl = Gtk.Label(label=display_txt)
        lbl.set_width_chars(7)
        lbl.set_xalign(1.0)
        lbl.add_css_class("val-badge")

        adj = Gtk.Adjustment(
            value=float(current_val),
            lower=float(min_val),
            upper=float(max_val),
            step_increment=float(step),
            page_increment=float(step) * 5
        )
        scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
        scale.set_size_request(220, -1)
        scale.set_valign(Gtk.Align.CENTER)
        scale.set_draw_value(False)

        def _on_val_changed(adjustment):
            v = adjustment.get_value()
            if is_float:
                v = round(v, 1)
                lbl.set_text(f"{v:.1f}{unit}")
                setattr(self.settings, attr_name, v)
            else:
                v = int(v)
                lbl.set_text(f"{v}{unit}")
                setattr(self.settings, attr_name, v)
            self._save()

        adj.connect("value-changed", _on_val_changed)

        box.append(lbl)
        box.append(scale)
        row.add_suffix(box)
        expander.add_row(row)
        self._controls[attr_name] = (adj, lbl, unit, is_float)

    def _save(self):
        save_vibration_settings(self.settings)
        if self.haptic_engine:
            self.haptic_engine.settings = self.settings

    def _on_reset_clicked(self, btn):
        self.settings = VibrationSettings()
        self._save()

        # Update all controls
        for attr, ctrl in self._controls.items():
            val = getattr(self.settings, attr)
            if isinstance(ctrl, Gtk.Switch):
                ctrl.set_active(bool(val))
            elif isinstance(ctrl, tuple):
                adj, lbl, unit, is_float = ctrl
                adj.set_value(float(val))
                if is_float:
                    lbl.set_text(f"{val:.1f}{unit}")
                else:
                    lbl.set_text(f"{int(val)}{unit}")

        if self.on_toast_requested:
            self.on_toast_requested("Vibration defaults restored")

    def _on_test_clicked(self, btn):
        if self.haptic_engine:
            self.haptic_engine.trigger_pulse(self.settings.abs_strength * 10, max(0.1, self.settings.abs_duration / 1000.0))
        elif self.device and self.device.connected:
            self.device.vibrate_wheel(intensity=60, duration=0.25, freq=18)

        if self.on_toast_requested:
            self.on_toast_requested("Testing tactile vibration pulse (18 Hz)...")
