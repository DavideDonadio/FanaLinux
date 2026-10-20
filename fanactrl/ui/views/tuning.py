"""
Tuning Menu View: 1:1 Hardware Motor & Steering Tuning Controls.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib

from fanactrl.core.tuning import TuningProfile, TUNING_METADATA


class TuningView(Adw.PreferencesPage):
    def __init__(self, device, on_toast_requested=None):
        super().__init__()
        self.device = device
        self.on_toast_requested = on_toast_requested
        self.profile = TuningProfile()
        self._controls = {}

        self._build_ui()

    def _build_ui(self):
        # 1. Profile Slot Switcher
        slot_group = Adw.PreferencesGroup()
        slot_group.set_title("Onboard Hardware Memory Slot")

        slot_row = Adw.ActionRow()
        slot_row.set_title("Active Hardware Profile")
        slot_row.set_subtitle("Stored directly on the wheelbase EEPROM (Slots 1 to 5)")

        self.slot_dropdown = Gtk.DropDown.new_from_strings([
            "Slot 1 (S_1)", "Slot 2 (S_2)", "Slot 3 (S_3)", "Slot 4 (S_4)", "Slot 5 (S_5)"
        ])
        self.slot_dropdown.connect("notify::selected", self._on_slot_changed)
        slot_row.add_suffix(self.slot_dropdown)
        slot_group.add(slot_row)

        self.add(slot_group)

        # 2. Dynamic Categories from TUNING_METADATA
        categories = {}
        for meta in TUNING_METADATA:
            cat_name = meta["category"]
            if cat_name not in categories:
                group = Adw.PreferencesGroup()
                group.set_title(cat_name)
                categories[cat_name] = group
                self.add(group)

            group = categories[cat_name]
            self._create_control_row(group, meta)

        # 3. Action Buttons (Apply / Reset)
        actions_group = Adw.PreferencesGroup()
        actions_row = Adw.ActionRow()
        actions_row.set_title("Hardware Synchronization")
        actions_row.set_subtitle("Save current settings to selected wheelbase memory slot")

        reset_btn = Gtk.Button(label="Reset to Defaults")
        reset_btn.connect("clicked", self._on_reset_defaults)
        actions_row.add_suffix(reset_btn)

        apply_btn = Gtk.Button(label="Apply to Wheelbase")
        apply_btn.add_css_class("suggested-action")
        apply_btn.add_css_class("pill")
        apply_btn.connect("clicked", self._on_apply_clicked)
        actions_row.add_suffix(apply_btn)

        actions_group.add(actions_row)
        self.add(actions_group)

    def _create_control_row(self, group, meta):
        row = Adw.ActionRow()
        row.set_title(meta["name"])
        row.set_subtitle(meta["desc"])

        param_id = meta["id"]
        current_val = getattr(self.profile, param_id, meta.get("default", 0))

        if meta.get("type") == "toggle":
            switch = Gtk.Switch()
            switch.set_active(bool(current_val))
            switch.set_valign(Gtk.Align.CENTER)
            row.add_suffix(switch)
            self._controls[param_id] = switch
        else:
            val_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            
            val_label = Gtk.Label(label=f"{current_val}{meta['unit']}")
            val_label.set_size_request(60, -1)
            val_label.add_css_class("numeric")
            val_label.add_css_class("heading")

            adj = Gtk.Adjustment(
                value=current_val,
                lower=meta["min"],
                upper=meta["max"],
                step_increment=meta.get("step", 1),
                page_increment=meta.get("step", 1) * 5
            )
            scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
            scale.set_size_request(200, -1)
            scale.set_draw_value(False)

            def _on_val_changed(adjustment, lbl=val_label, unit=meta['unit']):
                lbl.set_text(f"{int(adjustment.get_value())}{unit}")

            adj.connect("value-changed", _on_val_changed)

            val_box.append(val_label)
            val_box.append(scale)
            row.add_suffix(val_box)
            self._controls[param_id] = adj

        group.add(row)

    def _on_slot_changed(self, dropdown, param):
        slot_num = dropdown.get_selected() + 1
        self.profile.slot = slot_num
        if self.on_toast_requested:
            self.on_toast_requested(f"Switched to Hardware Profile Slot {slot_num}")

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
                setattr(self.profile, param_id, int(ctrl.get_value()))

        if self.device and self.device.connected:
            self.device.apply_tuning_profile(self.profile)
            if self.on_toast_requested:
                self.on_toast_requested(f"Tuning parameters flashed to CSL DD (Slot {self.profile.slot})!")
        else:
            if self.on_toast_requested:
                self.on_toast_requested("Device not connected!")
