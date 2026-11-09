"""
Game Profiles & Auto-Switching View (FanaLab Equivalent).
Allows configuring per-game tuning presets, auto-telemetry, and background detection.
"""

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
import os
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from gi.repository import Adw, GLib, Gtk

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
        self._game_expanders = []
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
        self.games_group.set_title("Simulators &amp; Game Profiles")
        self.games_group.set_description(
            "Associate each racing game with a specific tuning preset and choose whether in-game telemetry launches automatically."
        )

        self._populate_games()
        self.add(self.games_group)


    def _populate_games(self):
        # Notice card first: same in-group spacing as the calibration shortcut
        # row, visually separate from the game rows below it.
        tip_row = Adw.ActionRow()
        tip_row.set_title("About Force Feedback")
        tip_row.set_subtitle(
            "Every game drives FFB through the kernel driver. Dashboard and LEDs need a game data feed — present where telemetry is supported, absent for the rest."
        )
        tip_row.set_subtitle_lines(2)
        tip_row.set_icon_name("help-about-symbolic")
        tip_row.set_activatable(False)
        self.games_group.add(tip_row)

        presets = list_presets()
        all_games = self.detector.get_all_games()

        def _is_supported(game):
            return bool(game.get("has_telemetry") and game.get("telemetry_type"))

        def _rank(game):
            if _is_supported(game):
                # ACC closes the supported block, directly above FFB Only.
                return (0, 1) if game["id"] == "acc" else (0, 0)
            if game["id"] in self.FEEDLESS_IDS:
                return (1, 0)
            return (2, 0)

        # Supported first (ACC last of them), feed-less next, unsupported last.
        ordered = sorted(all_games, key=_rank)
        for game in ordered:
            self.games_group.add(self._make_game_row(game, presets, supported=_is_supported(game)))

    # Detected games which expose no Linux-readable telemetry: tuning
    # profiles still apply, dashboard/LEDs stay dark.
    FEEDLESS_IDS = ("assetto_corsa_evo",)

    # FanaLinux game id -> isiMotor Pulse installer key.
    PULSE_IDS = {"rfactor2": "rF2", "lmu": "LMU"}

    FEEDLESS_NOTES = {
        "assetto_corsa_evo": "No telemetry on Linux — the game exposes shared memory only.",
    }

    @staticmethod
    def _pulse_status(game_key: str) -> tuple[bool | None, str]:
        """(installed, detail) for the isiMotor Pulse plugin; None if unavailable."""
        try:
            from isimotor_pulse_client.install.steam import detect_game_installations
        except ImportError:
            return None, "Plugin support unavailable — reinstall FanaLinux."
        try:
            for game_dir in detect_game_installations().get(game_key, []):
                dll = Path(game_dir) / "Plugins" / "isiMotor_Pulse.dll"
                if dll.exists():
                    return True, f"Installed — {dll}"
            return False, "Not installed — one click installs the open-source isiMotor Pulse DLL."
        except Exception as e:
            return None, f"Status check failed: {e}"

    @staticmethod
    def _expander_subtitle(gid: str, preset: str) -> str:
        return f"Assigned Profile: {preset}"

    def _on_uninstall_pulse(self, _btn, gid: str, expander, row) -> None:
        """Remove the Pulse DLL from the game folder off the UI thread."""
        from fanalinux.core.telemetry.pulse import PulseTelemetry
        if not PulseTelemetry.is_available():
            self._toast("Plugin support unavailable — reinstall FanaLinux.")
            return
        row.set_subtitle("Uninstalling…")

        def work():
            try:
                import json
                from isimotor_pulse_client.install.dll import uninstall_plugin
                from isimotor_pulse_client.install.steam import detect_game_installations
                key = self.PULSE_IDS[gid]
                dirs = detect_game_installations().get(key, [])
                if not dirs:
                    name = {"rF2": "rFactor 2", "LMU": "Le Mans Ultimate"}.get(key, key)
                    raise RuntimeError(f"No {name} installation found in the Steam libraries.")
                for game_dir in dirs:
                    uninstall_plugin(target_dir=Path(game_dir))
                    # Leave no stale opt-in: the game would warn about it.
                    json_path = (Path(game_dir) / "UserData" / "player"
                                 / "CustomPluginVariables.JSON")
                    try:
                        data = json.loads(json_path.read_text(encoding="utf-8"))
                        plugin = data.get("isiMotor_Pulse")
                        if isinstance(plugin, dict) and plugin.get(" Enabled") != 0:
                            plugin[" Enabled"] = 0
                            json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                    except (OSError, ValueError):
                        pass
                result = (True, "Plugin uninstalled — wheel dashboard goes dark again.")
            except Exception as e:
                result = (False, f"Uninstall failed: {e}")
            GLib.idle_add(self._on_pulse_uninstalled, gid, expander, row, result)

        threading.Thread(target=work, daemon=True).start()

    def _on_pulse_uninstalled(self, gid, expander, row, result) -> bool:
        ok, message = result
        installed, detail = self._pulse_status(self.PULSE_IDS[gid])
        if not ok:
            detail = message
        elif not installed:
            detail = ("No Linux telemetry without it — install to unlock gear, RPM, "
                      "speed and rev LEDs on your wheel.")
        row.set_subtitle(detail)
        pill = getattr(expander, "_pulse_pill", None)
        if pill is not None:
            pill.set_label("Installed isiMotor Pulse" if installed else "Missing plugin")
            pill.remove_css_class("status-pill-running")
            pill.remove_css_class("status-pill-unsupported")
            pill.add_css_class("status-pill-running" if installed else "status-pill-unsupported")
        install_btn = getattr(row, "_install_btn", None)
        if install_btn is not None:
            install_btn.set_label("Reinstall plugin" if installed else "Install telemetry plugin")
        uninstall_btn = getattr(row, "_uninstall_btn", None)
        if uninstall_btn is not None:
            uninstall_btn.set_visible(installed)
        expander._pulse_installed = installed
        self._toast(message)
        return False

    def _on_install_pulse(self, _btn, gid: str, expander, row) -> None:
        """Copy the Pulse DLL into the game folder off the UI thread."""
        from fanalinux.core.telemetry.pulse import PulseTelemetry
        if not PulseTelemetry.is_available():
            self._toast("Plugin support unavailable — reinstall FanaLinux.")
            return
        row.set_subtitle("Installing…")

        def work():
            try:
                from isimotor_pulse_client.install.dll import copy_and_install_dll
                from isimotor_pulse_client.install.steam import detect_game_installations
                # The pip package ships no DLL: fetch the prebuilt one once.
                dll_path = PulseTelemetry.ensure_plugin_dll()
                key = self.PULSE_IDS[gid]
                dirs = detect_game_installations().get(key, [])
                if not dirs:
                    name = {"rF2": "rFactor 2", "LMU": "Le Mans Ultimate"}.get(key, key)
                    raise RuntimeError(f"No {name} installation found in the Steam libraries.")
                for game_dir in dirs:
                    ok, message, _paths = copy_and_install_dll(
                        custom_dll=Path(dll_path), target_dir=str(game_dir))
                    if not ok:
                        raise RuntimeError(message)
                result = (True, "Plugin installed — restart the game to light up the dashboard.")
            except Exception as e:
                result = (False, f"Install failed: {e}")
            GLib.idle_add(self._on_pulse_installed, gid, expander, row, result)

        threading.Thread(target=work, daemon=True).start()

    def _on_pulse_installed(self, gid, expander, row, result) -> bool:
        ok, message = result
        installed, detail = self._pulse_status(self.PULSE_IDS[gid])
        if not ok:
            # Hold the failure in the row, not just the toast.
            detail = message
        elif installed:
            detail = "Installed — gear, RPM, speed and rev LEDs live on your wheel."
        row.set_subtitle(
            'Open-source plugin: '
            '<a href="https://github.com/marcgardent/isiMotor-Pulse-Plugin">'
            '<span underline="none">marcgardent/isiMotor-Pulse-Plugin</span></a>\n' + detail)
        if ok:
            # Fresh plugin: telemetry is now useful, so auto-start it.
            self.detector.game_mappings.setdefault(gid, {})["auto_telemetry"] = True
            self.detector.save_config()
            telem_sw = getattr(expander, "_telem_sw", None)
            if telem_sw is not None:
                telem_sw.set_active(True)
        # Refresh main-row subtitle + Install button label.
        current = self.detector.game_mappings.get(gid, {}).get("preset")
        if not current:
            for game in self.detector.get_all_games():
                if game.get("id") == gid:
                    current = game.get("default_preset", "Default")
                    break
        expander.set_subtitle(self._expander_subtitle(gid, current or "Default"))
        pill = getattr(expander, "_pulse_pill", None)
        if pill is not None:
            pill.set_label("Installed isiMotor Pulse" if installed else "Missing plugin")
            pill.remove_css_class("status-pill-running")
            pill.remove_css_class("status-pill-unsupported")
            pill.add_css_class("status-pill-running" if installed else "status-pill-unsupported")
        plug_btn = getattr(row, "_install_btn", None)
        if plug_btn is not None:
            plug_btn.set_label("Reinstall plugin" if installed else "Install telemetry plugin")
        uninstall_btn = getattr(row, "_uninstall_btn", None)
        if uninstall_btn is not None:
            uninstall_btn.set_visible(installed)
        expander._pulse_installed = installed
        self._toast(message)
        return False

    def _toast(self, message: str) -> None:
        if self.on_toast_requested:
            self.on_toast_requested(message)

    def _on_expander_expanded(self, expanded_row, _param) -> None:
        """Single-open accordions: opening one closes the rest."""
        if not expanded_row.get_expanded():
            return
        for row in self._game_expanders:
            if row is not expanded_row:
                row.set_expanded(False)

    def _make_game_row(self, game, presets, supported: bool = True):
        gid = game["id"]
        mapping = self.detector.game_mappings.get(gid, {})
        current_preset = mapping.get("preset") or game.get("default_preset", "Default")
        is_enabled = mapping.get("enabled", True)
        auto_telem = mapping.get("auto_telemetry", game.get("has_telemetry", False))

        if not supported and gid not in self.FEEDLESS_IDS:
            # Flat row: no expander arrow, nothing to open.
            row = Adw.ActionRow()
            row.set_title(game["name"])
            flat_icon = self.detector.get_game_icon_path(gid)
            if flat_icon and os.path.exists(flat_icon):
                flat_img = Gtk.Image.new_from_file(flat_icon)
                flat_img.set_pixel_size(32)
                row.add_prefix(flat_img)
            else:
                row.set_icon_name("input-gaming-symbolic")
            badge = Gtk.Label(label="Not supported")
            badge.set_valign(Gtk.Align.CENTER)
            badge.add_css_class("status-pill-na")
            row.add_suffix(badge)
            return row

        expander = Adw.ExpanderRow()
        expander.connect("notify::expanded", self._on_expander_expanded)
        self._game_expanders.append(expander)
        expander.set_title(game["name"])
        expander.set_subtitle(self._expander_subtitle(gid, current_preset))
        if gid in self.PULSE_IDS:
            # Status pill always on the main row; install lives in the dropdown.
            installed, _detail = self._pulse_status(self.PULSE_IDS[gid])
            pill = Gtk.Label(label="Installed isiMotor Pulse" if installed else "Missing plugin")
            pill.set_valign(Gtk.Align.CENTER)
            pill.add_css_class("status-pill-running" if installed else "status-pill-unsupported")
            expander.add_suffix(pill)
            expander._pulse_pill = pill
            expander._pulse_installed = installed
        if gid in self.FEEDLESS_IDS:
            badge = Gtk.Label(label="FFB Only")
            badge.set_valign(Gtk.Align.CENTER)
            badge.add_css_class("status-pill-nodash")
            expander.add_suffix(badge)
        elif gid == "acc":
            badge = Gtk.Label(label="No RPM")
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

        # Every expander game gets a preset: tuning applies over hidraw
        # whether or not a telemetry feed exists. (Only flat rows lack one.)
        if supported or gid in self.FEEDLESS_IDS:
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
                    exp.set_subtitle(self._expander_subtitle(g_id, chosen))

            preset_dd.connect("notify::selected", _on_preset_picked)
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
            expander._telem_sw = telem_sw

            def _on_telem_toggle(sw, state, g_id=gid):
                entry = self.detector.game_mappings.setdefault(g_id, {})
                entry["auto_telemetry"] = sw.get_active()
                entry["auto_telemetry_explicit"] = True
                self.detector.save_config()

            telem_sw.connect("state-set", _on_telem_toggle)
            telem_row.add_suffix(telem_sw)
            expander.add_row(telem_row)

            if gid == "acc":
                # One-time game-side setup + the feed's known limit.
                acc_note = Adw.ActionRow()
                acc_note.set_title("Broadcast Setup (one-time)")
                acc_note.set_subtitle(
                    "Enable broadcasting in Documents/Assetto Corsa Competizione/Config/broadcasting.json. "
                    "This feed carries gear + speed only — no RPM, so the rev LEDs stay dark.")
                acc_note.set_subtitle_lines(2)
                acc_note.set_activatable(False)
                expander.add_row(acc_note)

        if gid in self.PULSE_IDS:
            # One-click plugin install; the DLL never ships with FanaLinux.
            _installed, detail = self._pulse_status(self.PULSE_IDS[gid])
            plug_row = Adw.ActionRow()
            plug_row.set_title("isiMotor Pulse Telemetry Plugin")
            if not expander._pulse_installed:
                detail = ("No Linux telemetry without it — install to unlock gear, RPM, "
                          "speed and rev LEDs on your wheel.")
            plug_row.set_subtitle(
                'Open-source plugin: '
                '<a href="https://github.com/marcgardent/isiMotor-Pulse-Plugin">'
                '<span underline="none">marcgardent/isiMotor-Pulse-Plugin</span></a>\n' + detail)
            plug_row.set_subtitle_lines(3)
            plug_row.set_activatable(False)
            install_btn = Gtk.Button(
                label="Reinstall plugin" if expander._pulse_installed else "Install telemetry plugin")
            install_btn.set_valign(Gtk.Align.CENTER)
            install_btn.connect("clicked", self._on_install_pulse, gid, expander, plug_row)
            plug_row.add_suffix(install_btn)
            plug_row._install_btn = install_btn
            uninstall_btn = Gtk.Button(label="Uninstall")
            uninstall_btn.set_valign(Gtk.Align.CENTER)
            uninstall_btn.connect("clicked", self._on_uninstall_pulse, gid, expander, plug_row)
            uninstall_btn.set_visible(expander._pulse_installed)
            plug_row.add_suffix(uninstall_btn)
            plug_row._uninstall_btn = uninstall_btn
            expander.add_row(plug_row)

        if gid in self.FEEDLESS_IDS:
            # Tuning still applies; explain why the wheel stays dark.
            note = Adw.ActionRow()
            note.set_title("Telemetry unavailable")
            note.set_subtitle(self.FEEDLESS_NOTES[gid])
            note.set_activatable(False)
            expander.add_row(note)

        if gid == "lmu":
            proton = Adw.ActionRow()
            proton.set_title("Proton setup")
            proton.set_subtitle_lines(2)
            proton.set_subtitle(
                'Requires the <a href="https://steamcommunity.com/sharedfiles/filedetails/?id=3536726840">'
                '<span underline="none">GE-Proton10-34-LMU-hid_fixes</span></a> '
                "Proton build with inverted FFB in the game settings.")
            proton.set_activatable(False)
            expander.add_row(proton)

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
