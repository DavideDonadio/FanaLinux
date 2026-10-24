"""
Dynamic FFB (Damper Overlay) View.
Replicates FanaLab's 'FFB Dynamique' / 'Surcouche d'Amortissement':
1. Speed-Sensitive Damper (Sensible à la vitesse)
2. Reverse Driving Safety Damper (Conduite en marche arrière)
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
from typing import Optional, Callable

from fanalinux.core.dynamic_ffb import (
    DynamicFFBSettings,
    load_dynamic_ffb_settings,
    save_dynamic_ffb_settings,
)
from fanalinux.ui.helpers import widen_page_clamp, attach_spin_button


class DynamicFFBView(Adw.PreferencesPage):
    def __init__(self, device, telemetry_mgr=None, on_toast_requested: Optional[Callable[[str], None]] = None):
        super().__init__()
        self.device = device
        self.telemetry_mgr = telemetry_mgr
        self.on_toast_requested = on_toast_requested
        self.settings: DynamicFFBSettings = load_dynamic_ffb_settings()

        # Ensure full width layout
        GLib.idle_add(widen_page_clamp, self)
        self._build_ui()

    def _build_ui(self):
        # 1. Section: Speed-Sensitive Damper
        speed_group = Adw.PreferencesGroup()
        speed_group.set_title("Speed-Sensitive Damper")
        speed_group.set_description(
            "Progressively increases steering wheel damping at high aerodynamic speeds "
            "to stabilize straight-line tracking and eliminate high-speed tank-slappers."
        )

        # Master Toggle
        speed_toggle_row = Adw.ActionRow()
        speed_toggle_row.set_title("Enable Speed Sensitivity")
        speed_toggle_row.set_subtitle("Activate telemetry-based high-speed damper scaling")
        self.speed_sw = Gtk.Switch()
        self.speed_sw.set_valign(Gtk.Align.CENTER)
        self.speed_sw.set_active(self.settings.speed_sensitive_enabled)
        self.speed_sw.connect("state-set", self._on_speed_toggle)
        speed_toggle_row.add_suffix(self.speed_sw)
        speed_group.add(speed_toggle_row)

        # Min Speed Threshold
        speed_group.add(self._make_slider_row(
            "Speed Threshold",
            "Minimum vehicle speed where dynamic damping begins fading in",
            "speed_threshold_min",
            50, 300, 5, " km/h"
        ))

        # Max Speed Threshold
        speed_group.add(self._make_slider_row(
            "Speed Threshold Max",
            "Speed at which dynamic damping reaches 100% of configured effect",
            "speed_threshold_max",
            100, 450, 5, " km/h"
        ))

        # Damper Effect Range
        speed_group.add(self._make_slider_row(
            "Damper Effect Range",
            "Steering angle window around center (0.0°) where damping applies",
            "damper_effect_range",
            10, 180, 5, "°"
        ))

        # Damper Effect Strength
        speed_group.add(self._make_slider_row(
            "Damper Effect Strength",
            "Magnitude of additional rotational resistance applied to wheel",
            "damper_effect_strength",
            0, 100, 1, "%"
        ))
        self.add(speed_group)

        # 2. Section: Reverse Driving Safety Damper
        reverse_group = Adw.PreferencesGroup()
        reverse_group.set_title("Reverse Driving Safety Damper")
        reverse_group.set_description(
            "Applies a strong resistance clamp when rolling backwards after a spin-out "
            "to prevent violent Direct Drive wheel snap and protect wrists."
        )

        # Master Toggle
        rev_toggle_row = Adw.ActionRow()
        rev_toggle_row.set_title("Enable Reverse Damper")
        rev_toggle_row.set_subtitle("Automatically damp violent caster snap when rolling backwards")
        self.rev_sw = Gtk.Switch()
        self.rev_sw.set_valign(Gtk.Align.CENTER)
        self.rev_sw.set_active(self.settings.reverse_damper_enabled)
        self.rev_sw.connect("state-set", self._on_reverse_toggle)
        rev_toggle_row.add_suffix(self.rev_sw)
        reverse_group.add(rev_toggle_row)

        # Damper Effect Strength
        reverse_group.add(self._make_slider_row(
            "Damper Effect Strength",
            "Holding resistance clamping the motor when rolling in reverse",
            "reverse_damper_strength",
            0, 100, 1, "%"
        ))

        # Fade-in Intensity
        reverse_group.add(self._make_slider_row(
            "Fade-in Intensity",
            "Ramp-up aggression once reverse vehicle movement is detected",
            "reverse_fade_in",
            1, 10, 1, ""
        ))
        self.add(reverse_group)

        # 3. Bottom Actions (No Header Text)
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

        actions_group.add(actions_box)
        self.add(actions_group)

    def _make_slider_row(self, title: str, subtitle: str, attr_name: str,
                         min_val: int, max_val: int, step: int, unit: str):
        row = Adw.ActionRow()
        row.set_title(title)
        row.set_subtitle(subtitle)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        box.set_valign(Gtk.Align.CENTER)

        current_val = getattr(self.settings, attr_name, min_val)
        lbl = Gtk.Label(label=f"{int(current_val)}{unit}")
        lbl.set_width_chars(8)
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
            v = int(adjustment.get_value())
            lbl.set_text(f"{v}{unit}")
            setattr(self.settings, attr_name, v)
            self._save()

        adj.connect("value-changed", _on_val_changed)

        box.append(lbl)
        box.append(scale)
        attach_spin_button(box, adj)
        row.add_suffix(box)
        return row

    def _on_speed_toggle(self, switch, state):
        self.settings.speed_sensitive_enabled = state
        self._save()
        if self.on_toast_requested:
            self.on_toast_requested(f"Speed-Sensitive Damper: {'Active' if state else 'Disabled'}")

    def _on_reverse_toggle(self, switch, state):
        self.settings.reverse_damper_enabled = state
        self._save()
        if self.on_toast_requested:
            self.on_toast_requested(f"Reverse Driving Safety Damper: {'Active' if state else 'Disabled'}")

    def _on_reset_clicked(self, btn):
        default = DynamicFFBSettings()
        self.settings = default
        self._save()
        self.speed_sw.set_active(default.speed_sensitive_enabled)
        self.rev_sw.set_active(default.reverse_damper_enabled)
        if self.on_toast_requested:
            self.on_toast_requested("Dynamic FFB settings reset to defaults")

    def _save(self):
        save_dynamic_ffb_settings(self.settings)
        if self.telemetry_mgr and hasattr(self.telemetry_mgr, 'dynamic_ffb_engine'):
            self.telemetry_mgr.dynamic_ffb_engine.reload_settings()
