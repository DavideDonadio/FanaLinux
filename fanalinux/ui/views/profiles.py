"""
Game Profiles & Auto-Switching View (FanaLab Equivalent).
Allows configuring per-game tuning presets, auto-telemetry, and background detection.
"""

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
import os
from collections.abc import Callable
from typing import Any

from gi.repository import Adw, Gtk

from fanalinux.core.detector import GameDetector
from fanalinux.core.presets import list_presets, load_preset


class ProfilesView(Adw.PreferencesPage):
    def __init__(
        self,
        device,
        telemetry_mgr,
        detector: GameDetector,
        on_toast_requested: Callable[[str], None] | None = None,
        on_preset_applied: Callable[[str], None] | None = None
    ):
        super().__init__()
        self.device = device
        self.telemetry_mgr = telemetry_mgr
        self.detector = detector
        self.on_toast_requested = on_toast_requested
        self.on_preset_applied = on_preset_applied

        self._preset_dropdowns = []
        self._build_ui()

    def _build_ui(self):
        # 1. Master Auto-Profile Settings & Live Status
        status_group = Adw.PreferencesGroup()
        status_group.set_title("Auto-Profile Engine Status")
        status_group.set_description(
            "Monitors Linux processes in background and automatically flashes wheel tuning parameters "
            "and starts telemetry whenever a supported racing simulator launches."
        )

        # Active Game Status Row
        self.status_row = Adw.ActionRow()
        self.status_row.set_title("Active Simulator")
        self.status_row.set_subtitle("No racing simulator currently running (Idle)")
        self.status_img = Gtk.Image.new_from_icon_name("input-gaming-symbolic")
        self.status_img.set_pixel_size(32)
        self.status_row.add_prefix(self.status_img)

        self.status_badge = Gtk.Label(label="Idle")
        self.status_badge.set_valign(Gtk.Align.CENTER)
        self.status_badge.add_css_class("status-pill-idle")
        self.status_row.add_suffix(self.status_badge)

        status_group.add(self.status_row)

        # Global Auto-Switching Toggle
        auto_toggle_row = Adw.ActionRow()
        auto_toggle_row.set_title("Enable Auto-Profile Switching")
        auto_toggle_row.set_subtitle("Automatically switch profiles and start telemetry on game launch")
        auto_img = Gtk.Image.new_from_icon_name("view-refresh-symbolic")
        auto_img.set_pixel_size(32)
        auto_toggle_row.add_prefix(auto_img)

        self.auto_switch = Gtk.Switch()
        self.auto_switch.set_active(self.detector.enabled)
        self.auto_switch.set_valign(Gtk.Align.CENTER)
        self.auto_switch.connect("state-set", self._on_auto_switch_toggled)
        auto_toggle_row.add_suffix(self.auto_switch)
        status_group.add(auto_toggle_row)

        # Fallback Preset Selection
        fallback_row = Adw.ActionRow()
        fallback_row.set_title("Desktop Fallback Preset")
        fallback_row.set_subtitle("Preset restored when simulators exit")
        fallback_img = Gtk.Image.new_from_icon_name("video-display-symbolic")
        fallback_img.set_pixel_size(32)
        fallback_row.add_prefix(fallback_img)

        presets = list_presets()
        self.fallback_dropdown = Gtk.DropDown.new_from_strings(presets)
        self.fallback_dropdown.set_valign(Gtk.Align.CENTER)
        self._select_dropdown_text(self.fallback_dropdown, self.detector.fallback_preset)
        self.fallback_dropdown.connect("notify::selected", self._on_fallback_changed)
        fallback_row.add_suffix(self.fallback_dropdown)
        status_group.add(fallback_row)

        self.add(status_group)

        # 2. Simulator Profiles Catalog
        self.games_group = Adw.PreferencesGroup()
        self.games_group.set_title("Supported Simulators &amp; Game Profiles")
        self.games_group.set_description(
            "Associate each racing game with a specific tuning preset and choose whether in-game telemetry launches automatically."
        )

        self._populate_games()
        self.add(self.games_group)

    def _populate_games(self):
        presets = list_presets()
        all_games = self.detector.get_all_games()

        def _is_supported(game):
            return bool(game.get("has_telemetry") and game.get("telemetry_type"))

        for game in all_games:
            if not _is_supported(game):
                continue
            self.games_group.add(self._make_game_row(game, presets, supported=True))

        unsupported = [g for g in all_games if not _is_supported(g)]
        if unsupported:
            unsupported_group = Adw.PreferencesGroup()
            unsupported_group.set_title("Not Yet Supported")
            unsupported_group.set_description(
                "Detection only — telemetry integration is pending, preset assignment is locked."
            )
            for game in unsupported:
                unsupported_group.add(self._make_game_row(game, presets, supported=False))
            self.add(unsupported_group)

    def _make_game_row(self, game, presets, supported: bool = True):
        gid = game["id"]
        mapping = self.detector.game_mappings.get(gid, {})
        current_preset = mapping.get("preset") or game.get("default_preset", "Default")
        is_enabled = mapping.get("enabled", True)
        auto_telem = mapping.get("auto_telemetry", game.get("has_telemetry", False))

        expander = Adw.ExpanderRow()
        expander.set_title(game["name"])
        if supported:
            expander.set_subtitle(f"Assigned Profile: {current_preset}")
        else:
            expander.set_subtitle("Currently not supported — detection only")
            badge = Gtk.Label(label="Not supported")
            badge.set_valign(Gtk.Align.CENTER)
            badge.add_css_class("status-pill-unsupported")
            expander.add_suffix(badge)
        
        icon_path = self.detector.get_game_icon_path(gid)
        if icon_path and os.path.exists(icon_path):
            img = Gtk.Image.new_from_file(icon_path)
            img.set_pixel_size(32)
            expander.add_prefix(img)
        else:
            expander.set_icon_name("input-gaming-symbolic")

        # Enable Toggle for this game
        enable_row = Adw.ActionRow()
        enable_row.set_title("Auto-Switch for this Game")
        enable_row.set_subtitle("Detect process launch and automatically load assigned preset")
        enable_sw = Gtk.Switch()
        enable_sw.set_active(is_enabled)
        enable_sw.set_valign(Gtk.Align.CENTER)

        def _on_game_enable(sw, state, g_id=gid):
            self.detector.game_mappings.setdefault(g_id, {})["enabled"] = sw.get_active()
            self.detector.save_config()

        enable_sw.connect("state-set", _on_game_enable)
        enable_row.add_suffix(enable_sw)
        expander.add_row(enable_row)

        # Assigned Tuning Preset Dropdown
        preset_row = Adw.ActionRow()
        preset_row.set_title("Assigned Hardware Preset")
        preset_row.set_subtitle("Tuning profile flashed to CSL DD when game starts")

        preset_dd = Gtk.DropDown.new_from_strings(presets)
        preset_dd.set_valign(Gtk.Align.CENTER)
        preset_dd.set_size_request(200, -1)
        self._select_dropdown_text(preset_dd, current_preset)

        def _on_preset_picked(dd, param, g_id=gid, exp=expander):
            idx = dd.get_selected()
            if idx >= 0:
                chosen = dd.get_model().get_string(idx)
                self.detector.game_mappings.setdefault(g_id, {})["preset"] = chosen
                self.detector.save_config()
                exp.set_subtitle(f"Assigned Profile: {chosen}")

        preset_dd.connect("notify::selected", _on_preset_picked)
        if not supported:
            preset_dd.set_sensitive(False)
        preset_row.add_suffix(preset_dd)
        self._preset_dropdowns.append(preset_dd)

        # Apply Immediately Button
        apply_btn = Gtk.Button(label="Apply Preset Now")
        apply_btn.set_valign(Gtk.Align.CENTER)

        def _on_apply_preset(btn, g_id=gid, dd=preset_dd):
            idx = dd.get_selected()
            if idx >= 0:
                chosen = dd.get_model().get_string(idx)
                profile = load_preset(chosen)
                if profile and self.device and self.device.connected:
                    self.device.apply_tuning_profile(profile)
                    if self.on_toast_requested:
                        self.on_toast_requested(f"Applied preset '{chosen}' to wheelbase!")
                    if self.on_preset_applied:
                        self.on_preset_applied(chosen)
                elif not self.device or not self.device.connected:
                    if self.on_toast_requested:
                        self.on_toast_requested("Device not connected!")

        apply_btn.connect("clicked", _on_apply_preset)
        preset_row.add_suffix(apply_btn)
        expander.add_row(preset_row)

        # Telemetry row (if game supports telemetry)
        if game.get("has_telemetry", False):
            telem_row = Adw.ActionRow()
            telem_row.set_title("Auto-Start In-Game Telemetry")
            telem_row.set_subtitle("Automatically start RevLED and display telemetry listener")

            telem_sw = Gtk.Switch()
            telem_sw.set_active(auto_telem)
            telem_sw.set_valign(Gtk.Align.CENTER)

            def _on_telem_toggle(sw, state, g_id=gid):
                entry = self.detector.game_mappings.setdefault(g_id, {})
                entry["auto_telemetry"] = sw.get_active()
                entry["auto_telemetry_explicit"] = True
                self.detector.save_config()

            telem_sw.connect("state-set", _on_telem_toggle)
            telem_row.add_suffix(telem_sw)
            expander.add_row(telem_row)

        return expander

    def _select_dropdown_text(self, dropdown: Gtk.DropDown, text: str):
        model = dropdown.get_model()
        n = model.get_n_items() if model else 0
        for i in range(n):
            if model.get_string(i) == text:
                dropdown.set_selected(i)
                return
        if n > 0:
            dropdown.set_selected(0)

    def refresh_preset_lists(self):
        """Update all dropdowns when presets are added or modified."""
        presets = list_presets()
        for dd in self._preset_dropdowns:
            curr_idx = dd.get_selected()
            curr_text = dd.get_model().get_string(curr_idx) if curr_idx >= 0 else ""
            new_model = Gtk.StringList.new(presets)
            dd.set_model(new_model)
            self._select_dropdown_text(dd, curr_text)

        # Also fallback dropdown
        curr_fb_idx = self.fallback_dropdown.get_selected()
        curr_fb_text = self.fallback_dropdown.get_model().get_string(curr_fb_idx) if curr_fb_idx >= 0 else "Default"
        self.fallback_dropdown.set_model(Gtk.StringList.new(presets))
        self._select_dropdown_text(self.fallback_dropdown, curr_fb_text)

    def update_status(self, game_info: dict[str, Any] | None):
        """Update the status row when a game is detected or exits."""
        if game_info:
            self.status_row.set_title(f"Active Simulator: {game_info['name']}")
            mapping = self.detector.game_mappings.get(game_info["id"], {})
            preset_name = mapping.get("preset") or game_info.get("default_preset", "Default")
            self.status_row.set_subtitle(f"Running (Profile: '{preset_name}')")
            self.status_badge.set_text("Running")
            self.status_badge.remove_css_class("status-pill-idle")
            self.status_badge.add_css_class("status-pill-running")
        else:
            self.status_row.set_title("Active Simulator: None")
            self.status_row.set_subtitle(f"No game running — Baseline '{self.detector.fallback_preset}' active")
            self.status_badge.set_text("Idle")
            self.status_badge.remove_css_class("status-pill-running")
            self.status_badge.add_css_class("status-pill-idle")

    def _on_auto_switch_toggled(self, switch, state):
        self.detector.enabled = switch.get_active()
        self.detector.save_config()
        if self.on_toast_requested:
            status = "enabled" if self.detector.enabled else "disabled"
            self.on_toast_requested(f"Auto-Profile switching {status}")

    def _on_fallback_changed(self, dropdown, param):
        idx = dropdown.get_selected()
        if idx >= 0:
            name = dropdown.get_model().get_string(idx)
            self.detector.fallback_preset = name
            self.detector.save_config()
