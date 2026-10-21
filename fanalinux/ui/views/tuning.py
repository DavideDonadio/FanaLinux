"""
Tuning Menu View: 1:1 Hardware Motor & Steering Tuning Controls.
Includes Preset Management (Save, Load, Export/Import JSON).
"""

import os
import json
import pathlib
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
from typing import Optional, Callable

from fanalinux.core.tuning import TuningProfile, TUNING_METADATA
from fanalinux.core.presets import list_presets, load_preset, save_preset, delete_preset, init_default_presets
from fanalinux.ui.helpers import widen_page_clamp


class TuningView(Adw.PreferencesPage):
    def __init__(
        self,
        device,
        on_toast_requested: Optional[Callable[[str], None]] = None,
        on_presets_changed: Optional[Callable[[], None]] = None
    ):
        super().__init__()
        self.device = device
        self.on_toast_requested = on_toast_requested
        self.on_presets_changed = on_presets_changed
        self.profile = TuningProfile()
        self._controls = {}

        # Ensure default presets exist
        init_default_presets()

        # Ensure page clamp utilizes available window space
        GLib.idle_add(widen_page_clamp, self)

        self._build_ui()

    def _build_ui(self):
        meta_by_id = {m["id"]: m for m in TUNING_METADATA}

        # 1. Profile Slot & Preset Switcher (Sections with fewer elements stay in 1 column)
        slot_group = Adw.PreferencesGroup()
        slot_group.set_title("Hardware Memory Slots &amp; Presets")
        slot_group.set_description("Select hardware memory slots or save custom per-car game presets")

        # Hardware Slot Row
        slot_row = Adw.ActionRow()
        slot_row.set_title("Active Hardware Slot")
        slot_row.set_subtitle("Directly selects wheelbase EEPROM profile (Slots 1 to 5)")

        self.slot_dropdown = Gtk.DropDown.new_from_strings([
            "Slot 1 (S_1)", "Slot 2 (S_2)", "Slot 3 (S_3)", "Slot 4 (S_4)", "Slot 5 (S_5)"
        ])
        self.slot_dropdown.set_valign(Gtk.Align.CENTER)
        self.slot_dropdown.set_size_request(160, -1)
        self.slot_dropdown.connect("notify::selected", self._on_slot_changed)
        slot_row.add_suffix(self.slot_dropdown)
        slot_group.add(slot_row)

        # Load Saved Preset Row
        load_row = Adw.ActionRow()
        load_row.set_title("Load Preset from Disk")
        load_row.set_subtitle("Recall tuning configuration for specific car/sim")

        load_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        load_box.set_valign(Gtk.Align.CENTER)

        presets = list_presets()
        self.preset_dropdown = Gtk.DropDown.new_from_strings(presets)
        self.preset_dropdown.set_valign(Gtk.Align.CENTER)
        self.preset_dropdown.set_size_request(180, -1)
        load_box.append(self.preset_dropdown)

        load_btn = Gtk.Button(label="Load")
        load_btn.set_valign(Gtk.Align.CENTER)
        load_btn.connect("clicked", self._on_load_preset_clicked)
        load_box.append(load_btn)

        load_row.add_suffix(load_box)
        slot_group.add(load_row)

        # Save Preset Row
        save_row = Adw.ActionRow()
        save_row.set_title("Save Current Configuration")
        save_row.set_subtitle("Save current parameters under a new preset name")

        save_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        save_box.set_valign(Gtk.Align.CENTER)

        self.preset_entry = Gtk.Entry()
        self.preset_entry.set_placeholder_text("Assetto Corsa - GT3")
        self.preset_entry.set_text("Custom")
        self.preset_entry.set_width_chars(18)
        self.preset_entry.set_valign(Gtk.Align.CENTER)
        save_box.append(self.preset_entry)

        save_preset_btn = Gtk.Button(label="Save Preset")
        save_preset_btn.set_size_request(110, 38)
        save_preset_btn.set_valign(Gtk.Align.CENTER)
        save_preset_btn.connect("clicked", self._on_save_preset)
        save_box.append(save_preset_btn)

        save_row.add_suffix(save_box)
        slot_group.add(save_row)
        self.add(slot_group)

        # 2. Section with MORE elements: Motor Dynamics & Steering (Divided into 2 columns of elements)
        motor_group = Adw.PreferencesGroup()
        motor_group.set_title("Direct-Drive Motor &amp; Steering Dynamics")
        motor_group.set_description("Master torque strength, rotation limit, and dynamic mechanical resistance.")

        motor_two_col = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        motor_two_col.set_hexpand(True)
        motor_two_col.set_homogeneous(True)

        motor_left_list = Gtk.ListBox()
        motor_left_list.add_css_class("boxed-list")
        motor_left_list.set_hexpand(True)

        motor_right_list = Gtk.ListBox()
        motor_right_list.add_css_class("boxed-list")
        motor_right_list.set_hexpand(True)

        for param_id in ["sen", "ff", "ffs"]:
            if param_id in meta_by_id:
                self._create_control_row(motor_left_list, meta_by_id[param_id], compact=True)

        for param_id in ["ndp", "nfr", "nin"]:
            if param_id in meta_by_id:
                self._create_control_row(motor_right_list, meta_by_id[param_id], compact=True)

        motor_two_col.append(motor_left_list)
        motor_two_col.append(motor_right_list)
        motor_group.add(motor_two_col)
        self.add(motor_group)

        # 3. Section with MORE elements: Filters & Force Multipliers (Divided into 2 columns of elements)
        effects_group = Adw.PreferencesGroup()
        effects_group.set_title("Signal Filters &amp; Game Force Multipliers")
        effects_group.set_description("Interpolation smoothing, curb strike intensity, and game physics force scaling.")

        effects_two_col = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        effects_two_col.set_hexpand(True)
        effects_two_col.set_homogeneous(True)

        effects_left_list = Gtk.ListBox()
        effects_left_list.add_css_class("boxed-list")
        effects_left_list.set_hexpand(True)

        effects_right_list = Gtk.ListBox()
        effects_right_list.add_css_class("boxed-list")
        effects_right_list.set_hexpand(True)

        for param_id in ["int_filter", "fei", "for_mult"]:
            if param_id in meta_by_id:
                self._create_control_row(effects_left_list, meta_by_id[param_id], compact=True)

        for param_id in ["spr_mult", "dpr_mult"]:
            if param_id in meta_by_id:
                self._create_control_row(effects_right_list, meta_by_id[param_id], compact=True)

        effects_two_col.append(effects_left_list)
        effects_two_col.append(effects_right_list)
        effects_group.add(effects_two_col)
        self.add(effects_group)

        # 4. Section with FEWER elements: Hardware Feedback (Leaves in 1 single column)
        feedback_group = Adw.PreferencesGroup()
        feedback_group.set_title("Hardware Feedback &amp; Pedals")
        feedback_group.set_description("Wheel rim vibration motor level and load-cell brake pressure sensitivity.")
        for param_id in ["sho", "bli", "brf"]:
            if param_id in meta_by_id:
                self._create_control_row(feedback_group, meta_by_id[param_id], compact=False)
        self.add(feedback_group)

        # 5. Actions at the end of Tuning tab (no header text)
        actions_group = Adw.PreferencesGroup()

        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        actions_box.set_halign(Gtk.Align.END)
        actions_box.set_margin_top(8)
        actions_box.set_margin_bottom(16)

        reset_btn = Gtk.Button(label="Reset Defaults")
        reset_btn.set_size_request(140, 42)
        reset_btn.set_valign(Gtk.Align.CENTER)
        reset_btn.connect("clicked", self._on_reset_defaults)
        actions_box.append(reset_btn)

        apply_btn = Gtk.Button(label="Apply to Wheelbase")
        apply_btn.set_size_request(180, 42)
        apply_btn.set_valign(Gtk.Align.CENTER)
        apply_btn.add_css_class("suggested-action")
        apply_btn.add_css_class("pill")
        apply_btn.connect("clicked", self._on_apply_clicked)
        actions_box.append(apply_btn)

        actions_group.add(actions_box)
        self.add(actions_group)

    def _create_control_row(self, container, meta, compact=False):
        row = Adw.ActionRow()
        row.set_title(meta["name"])
        if compact:
            row.set_tooltip_text(meta["desc"])
        else:
            row.set_subtitle(meta["desc"])

        param_id = meta["id"]
        current_val = getattr(self.profile, param_id, meta.get("default", 0))

        if meta.get("type") == "toggle":
            switch_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            switch_box.set_valign(Gtk.Align.CENTER)

            mode_label = Gtk.Label(label="Peak" if current_val else "Linear")
            mode_label.set_width_chars(6)
            mode_label.add_css_class("val-badge")

            switch = Gtk.Switch()
            switch.set_active(bool(current_val))
            switch.set_valign(Gtk.Align.CENTER)

            def _on_switch_changed(sw, state):
                mode_label.set_text("Peak" if sw.get_active() else "Linear")

            switch.connect("state-set", _on_switch_changed)

            switch_box.append(mode_label)
            switch_box.append(switch)
            row.add_suffix(switch_box)
            self._controls[param_id] = switch
        else:
            val_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            val_box.set_valign(Gtk.Align.CENTER)

            def _format_display_val(v):
                if param_id == "sen" and int(v) <= 0:
                    return "Auto"
                return f"{int(v)}{meta['unit']}"

            val_label = Gtk.Label(label=_format_display_val(current_val))
            val_label.set_width_chars(6)
            val_label.set_xalign(1.0)
            val_label.add_css_class("val-badge")

            adj = Gtk.Adjustment(
                value=current_val,
                lower=meta["min"],
                upper=meta["max"],
                step_increment=meta.get("step", 1),
                page_increment=meta.get("step", 1) * 5
            )
            scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
            scale_w = 180 if compact else 220
            scale.set_size_request(scale_w, -1)
            scale.set_valign(Gtk.Align.CENTER)
            scale.set_draw_value(False)

            def _on_val_changed(adjustment, lbl=val_label, pid=param_id, unit=meta['unit']):
                raw_v = int(adjustment.get_value())
                if pid == "sen":
                    # Snap 1..89 to 0 (Auto) if < 45, else 90
                    if 0 < raw_v < 90:
                        raw_v = 0 if raw_v < 45 else 90
                        adjustment.set_value(raw_v)
                        return
                    if raw_v <= 0:
                        lbl.set_text("Auto")
                        return
                lbl.set_text(f"{raw_v}{unit}")

            adj.connect("value-changed", _on_val_changed)

            val_box.append(val_label)
            val_box.append(scale)
            row.add_suffix(val_box)
            self._controls[param_id] = adj

        if hasattr(container, "add"):
            container.add(row)
        else:
            container.append(row)

    def _on_slot_changed(self, dropdown, param):
        slot_num = dropdown.get_selected() + 1
        self.profile.slot = slot_num
        if self.on_toast_requested:
            self.on_toast_requested(f"Switched to Hardware Profile Slot {slot_num}")

    def _on_load_preset_clicked(self, btn):
        idx = self.preset_dropdown.get_selected()
        model = self.preset_dropdown.get_model()
        if model and 0 <= idx < model.get_n_items():
            name = model.get_string(idx)
            p = load_preset(name)
            if p:
                self.set_active_profile(p)
                if self.on_toast_requested:
                    self.on_toast_requested(f"Loaded preset '{name}'")
            else:
                if self.on_toast_requested:
                    self.on_toast_requested(f"Could not load preset '{name}': invalid or corrupt JSON")

    def set_active_profile(self, profile: TuningProfile):
        """Update tuning UI to reflect profile values."""
        self.profile = profile
        self.preset_entry.set_text(profile.name)
        if 1 <= profile.slot <= 5:
            self.slot_dropdown.set_selected(profile.slot - 1)
        self._sync_ui_to_profile()

    def _on_save_preset(self, btn):
        preset_name = self.preset_entry.get_text().strip() or "Custom"
        
        # Pull current UI state into profile
        for meta in TUNING_METADATA:
            param_id = meta["id"]
            ctrl = self._controls.get(param_id)
            if not ctrl:
                continue
            if isinstance(ctrl, Gtk.Switch):
                setattr(self.profile, param_id, 1 if ctrl.get_active() else 0)
            elif isinstance(ctrl, Gtk.Adjustment):
                val = int(ctrl.get_value())
                if param_id == "sen" and 0 < val < 90:
                    val = 0 if val < 45 else 90
                setattr(self.profile, param_id, val)

        if save_preset(preset_name, self.profile):
            self.refresh_presets()
            if self.on_toast_requested:
                self.on_toast_requested(f"Saved preset '{preset_name}' to disk")
            if self.on_presets_changed:
                self.on_presets_changed()
        else:
            if self.on_toast_requested:
                self.on_toast_requested(f"Failed to save preset '{preset_name}'")

    def refresh_presets(self):
        presets = list_presets()
        curr_idx = self.preset_dropdown.get_selected()
        model = self.preset_dropdown.get_model()
        curr_text = model.get_string(curr_idx) if (model and 0 <= curr_idx < model.get_n_items()) else "Default"
        self.preset_dropdown.set_model(Gtk.StringList.new(presets))
        # Reselect
        for i, name in enumerate(presets):
            if name == curr_text or name == self.preset_entry.get_text().strip():
                self.preset_dropdown.set_selected(i)
                break

    def _on_reset_defaults(self, btn):
        self.profile = TuningProfile()
        self._sync_ui_to_profile()
        if self.on_toast_requested:
            self.on_toast_requested("Reset parameters to baseline defaults")

    def _sync_ui_to_profile(self):
        for meta in TUNING_METADATA:
            param_id = meta["id"]
            ctrl = self._controls.get(param_id)
            if not ctrl:
                continue
            val = getattr(self.profile, param_id, meta.get("default", 0))
            if isinstance(ctrl, Gtk.Switch):
                ctrl.set_active(bool(val))
            elif isinstance(ctrl, Gtk.Adjustment):
                ctrl.set_value(float(val))

    def _on_apply_clicked(self, btn):
        for meta in TUNING_METADATA:
            param_id = meta["id"]
            ctrl = self._controls.get(param_id)
            if not ctrl:
                continue
            if isinstance(ctrl, Gtk.Switch):
                setattr(self.profile, param_id, 1 if ctrl.get_active() else 0)
            elif isinstance(ctrl, Gtk.Adjustment):
                val = int(ctrl.get_value())
                if param_id == "sen" and 0 < val < 90:
                    val = 0 if val < 45 else 90
                setattr(self.profile, param_id, val)

        if self.device and self.device.connected:
            self.device.apply_tuning_profile(self.profile)
            if self.on_toast_requested:
                self.on_toast_requested(f"Tuning parameters flashed to CSL DD (Slot {self.profile.slot})!")
        else:
            if self.on_toast_requested:
                self.on_toast_requested("Device not connected!")
