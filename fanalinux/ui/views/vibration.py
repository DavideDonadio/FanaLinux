"""
Vibration View: Telemetry-Driven Haptic Feedback & Dynamic Rim/Pedal Vibration.
Matches the official Fanatec App / FanaLab Vibration tab.
"""

import logging
import threading

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from collections.abc import Callable

from gi.repository import Adw, Gtk

from fanalinux.core.vibration import (
    VibrationSettings,
    load_vibration_settings,
    save_vibration_settings,
)
from fanalinux.ui.helpers import slider_cluster

logger = logging.getLogger("fanalinux.vibration")


class VibrationView(Adw.PreferencesPage):
    def __init__(self, device, haptic_engine=None, on_toast_requested: Callable[[str], None] | None = None):
        super().__init__()
        self.device = device
        self.haptic_engine = haptic_engine
        self.on_toast_requested = on_toast_requested
        self.settings: VibrationSettings = self.haptic_engine.settings if self.haptic_engine else load_vibration_settings()

        self._controls = {}

        self._build_ui()

    def _build_ui(self):
        # 1. Section: Braking & Engine Dynamics
        col1_group = Adw.PreferencesGroup()
        col1_group.set_title("Braking &amp; Engine Dynamics")
        col1_group.set_description("Haptic rumble triggered by wheel braking lockups and engine RPM thresholds.")
        groups = {"braking": col1_group}
        self.add(col1_group)

        # 3. Section: Suspension & Rough Surface
        col2_group = Adw.PreferencesGroup()
        col2_group.set_title("Suspension &amp; Curb Strikes")
        col2_group.set_description("Simulates track curb strikes, rumblestrips, and surface displacements.")
        groups["suspension"] = col2_group
        self.add(col2_group)

        # 4. Section: Traction & Tire Slip
        col3_group = Adw.PreferencesGroup()
        col3_group.set_title("Traction &amp; Wheel Slip")
        col3_group.set_description("Tactile alerts when driven wheels spin or tires lock up under deceleration.")
        groups["traction"] = col3_group
        self.add(col3_group)

        # 5. Section: Chassis Balance
        col4_group = Adw.PreferencesGroup()
        col4_group.set_title("Chassis Balance (Slip Angles)")
        col4_group.set_description("Alerts when front or rear slip angles exceed optimal friction limits.")
        groups["balance"] = col4_group
        self.add(col4_group)

        for group_key, title, subtitle, toggle_attr, sliders in self.VIBRATION_SECTIONS:
            self._build_section(groups[group_key], title, subtitle, toggle_attr, sliders)

        # 6. Actions at the end of Vibration tab (no header text)
        actions_group = Adw.PreferencesGroup()
        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        actions_box.set_halign(Gtk.Align.END)
        actions_box.set_margin_top(8)
        actions_box.set_margin_bottom(16)

        reset_btn = Gtk.Button(label="Reset Defaults")
        reset_btn.set_size_request(140, 42)
        reset_btn.set_valign(Gtk.Align.CENTER)
        reset_btn.connect("clicked", self._on_reset_clicked)
        actions_box.append(reset_btn)

        test_btn = Gtk.Button(label="Preview Haptics")
        test_btn.set_size_request(160, 42)
        test_btn.set_valign(Gtk.Align.CENTER)
        test_btn.add_css_class("suggested-action")
        test_btn.add_css_class("pill")
        test_btn.connect("clicked", self._on_test_clicked)
        actions_box.append(test_btn)

        actions_group.add(actions_box)
        self.add(actions_group)

    # ----------------- Section Builders -----------------

    # (group, title, subtitle, toggle attr, [(attr, label, min, max, step, unit, is_float)]).
    # Adding an effect = one table row; the loop below builds the whole tab.
    VIBRATION_SECTIONS = [
        ("braking", "ABS Vibration", "Tactile feedback triggered when anti-lock brakes engage under heavy deceleration",
         "abs_enabled", [("abs_strength", "Vibration Strength", 1, 10, 1, "", False),
                           ("abs_duration", "Vibration Duration", 20, 300, 10, "ms", False)]),
        ("braking", "Engine Vibration", "Continuous subtle engine rumble scaled with vehicle engine RPM",
         "engine_enabled", [("engine_strength", "Vibration Strength", 1, 10, 1, "", False),
                              ("engine_initial", "Initial Vibration", 0, 100, 5, "%", False)]),
        ("braking", "Rev Limiter Vibration", "Sharp rhythmic vibration shudder when approaching maximum engine revs",
         "rev_enabled", [("rev_strength", "Vibration Strength", 1, 10, 1, "", False),
                           ("rev_threshold", "Threshold", 80.0, 100.0, 0.5, "%", True)]),
        ("suspension", "Suspension Travel Vibration", "Simulates curb strikes and rough road surface displacements",
         "suspension_enabled", [("suspension_strength", "Vibration Strength", 1, 10, 1, "", False),
                                  ("suspension_threshold", "Threshold", 0.1, 50.0, 0.5, "%", True)]),
        ("traction", "Traction Control Vibration", "Tactile pulse when ECU traction control cuts engine power during acceleration",
         "tc_enabled", [("tc_strength", "Vibration Strength", 1, 10, 1, "", False),
                           ("tc_duration", "Vibration Duration", 20, 300, 10, "ms", False)]),
        ("traction", "Wheel Lock Vibration", "Direct tactile shudder whenever individual tires lock up under braking",
         "wheel_lock_enabled", [("wheel_lock_strength", "Vibration Strength", 1, 10, 1, "", False)]),
        ("traction", "Wheel Spin Vibration", "Tactile warning when driven tires break traction and spin faster than car speed",
         "wheel_spin_enabled", [("wheel_spin_strength", "Vibration Strength", 1, 10, 1, "", False)]),
        ("balance", "Understeer Vibration", "Alerts you when front tires exceed grip angle and scrub across asphalt",
         "understeer_enabled", [("understeer_strength", "Vibration Strength", 1, 10, 1, "", False),
                                  ("understeer_friction_limit", "Friction Limit", 0.0, 30.0, 0.5, "°", True)]),
        ("balance", "Oversteer Vibration", "Alerts you when rear slip angle exceeds recovery threshold (rear slide)",
         "oversteer_enabled", [("oversteer_strength", "Vibration Strength", 1, 10, 1, "", False),
                                 ("oversteer_friction_limit", "Friction Limit", 0.0, 30.0, 0.5, "°", True)]),
    ]

    def _build_section(self, group: Adw.PreferencesGroup, title: str, subtitle: str,
                       toggle_attr: str, sliders: list):
        expander = Adw.ExpanderRow()
        expander.set_title(title)
        expander.set_subtitle(subtitle)
        self._add_toggle_prefix(expander, toggle_attr)
        for attr, label, lo, hi, step, unit, is_float in sliders:
            self._add_slider_row(expander, attr, label, lo, hi, step, unit, is_float=is_float)
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

        def _on_val_changed(v):
            if is_float:
                v = round(v, 1)
            else:
                v = int(v)
            row_lbl.set_text(f"{v:.1f}{unit}" if is_float else f"{v}{unit}")
            setattr(self.settings, attr_name, v)
            self._save()

        box, adj, row_lbl = slider_cluster(
            float(min_val), float(max_val), float(step),
            float(getattr(self.settings, attr_name, min_val)),
            unit=unit, digits=1 if is_float else 0, width=220, badge_width=7,
            on_change=_on_val_changed,
        )
        row.add_suffix(box)
        expander.add_row(row)
        self._controls[attr_name] = (adj, row_lbl, unit, is_float)

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
        if not self.device or not self.device.connected:
            if self.on_toast_requested:
                self.on_toast_requested("Device not connected!")
            return

        strength = max(10, min(100, int(self.settings.abs_strength * 10)))
        duration_s = max(0.2, self.settings.abs_duration / 1000.0)

        def _worker():
            try:
                self.device.vibrate_wheel(intensity=strength, duration=duration_s, freq=18)
            except Exception as e:
                logger.error(f"Error previewing haptics: {e}")

        threading.Thread(target=_worker, daemon=True).start()

        if self.on_toast_requested:
            self.on_toast_requested(f"Previewing haptic pulse ({strength}% strength, {int(duration_s * 1000)}ms)...")
