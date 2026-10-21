"""
Overview View: Hardware Status, Live Gauges, and Button Matrix.
"""

import os
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from typing import Optional, Callable
from gi.repository import Gtk, Adw, GLib, Gdk, Gio

from fanalinux.core.hardware import (
    load_hardware_config,
    save_hardware_config,
    KNOWN_RIMS,
    get_base_info,
    get_rim_info,
    KNOWN_BASES,
)

RESOURCES_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..", "resources"))


class OverviewView(Adw.PreferencesPage):
    def __init__(self, device, on_rim_changed: Optional[Callable[[dict], None]] = None):
        super().__init__()
        self.device = device
        self.on_rim_changed = on_rim_changed
        self._button_chips = {}
        self.hardware_config = load_hardware_config()
        self.current_rim_info = get_rim_info(self.hardware_config.rim_id)
        if self.device:
            self.device.rim_name = self.current_rim_info["name"]
        self._build_ui()

    def _create_thumbnail(self, image_path: str, fallback_icon: str, size: int = 102, box_width: int = 128, box_height: int = 108) -> tuple[Gtk.Box, Gtk.Image]:
        """Create a clean, strictly sized hardware thumbnail centered in a fixed-geometry container."""
        container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        container.set_size_request(box_width, box_height)
        container.set_halign(Gtk.Align.START)
        container.set_valign(Gtk.Align.CENTER)
        container.set_hexpand(False)
        container.set_vexpand(False)
        container.set_margin_end(16)

        if os.path.exists(image_path):
            f = Gio.File.new_for_path(image_path)
            tex = Gdk.Texture.new_from_file(f)
            img = Gtk.Image.new_from_paintable(tex)
        else:
            img = Gtk.Image.new_from_icon_name(fallback_icon)

        img.set_pixel_size(size)
        img.set_valign(Gtk.Align.CENTER)
        img.set_halign(Gtk.Align.CENTER)
        img.set_hexpand(True)
        img.set_vexpand(True)
        container.append(img)
        return container, img

    def _build_ui(self):
        # 1. Device Info Card
        info_group = Adw.PreferencesGroup()
        info_group.set_title("Hardware Status")

        # Determine appropriate hardware thumbnail images based on connected device
        base_info = get_base_info(self.device.product_id if self.device else 0x0020)
        base_img_path = os.path.join(RESOURCES_DIR, "bases", base_info.get("image", "csl_dd.png"))
        rim_img_path = os.path.join(RESOURCES_DIR, "rims", self.current_rim_info.get("image", "formula_v2.png"))

        # Base Row
        self.status_row = Adw.ActionRow()
        self.status_row.set_title(base_info["name"])
        pid_hex = f"0x{self.device.product_id:04X}" if self.device else "0x0020"
        self.status_row.set_subtitle(f"Vendor ID: 0x0EB7 | Product ID: {pid_hex} | PC Mode (Red)")
        base_box, self.base_thumbnail = self._create_thumbnail(base_img_path, "input-gaming-symbolic", size=112, box_width=128, box_height=108)
        self.status_row.add_prefix(base_box)

        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        status_box.set_valign(Gtk.Align.CENTER)
        status_box.add_css_class("status-indicator-box")

        self.status_dot = Gtk.Image.new_from_icon_name("media-record-symbolic")
        self.status_dot.set_pixel_size(10)
        self.status_dot.add_css_class("status-dot-online")
        status_box.append(self.status_dot)

        self.conn_badge = Gtk.Label(label="Online")
        self.conn_badge.add_css_class("success")
        self.conn_badge.add_css_class("heading")
        status_box.append(self.conn_badge)

        self.status_row.add_suffix(status_box)
        info_group.add(self.status_row)

        # Rim Row
        self.rim_row = Adw.ActionRow()
        self.rim_row.set_title("Steering Wheel Rim")
        self.rim_row.set_subtitle(self.current_rim_info["subtitle"])
        rim_box, self.rim_thumbnail = self._create_thumbnail(rim_img_path, "applications-games-symbolic", size=102, box_width=128, box_height=108)
        self.rim_row.add_prefix(rim_box)

        # Dropdown selector for exact steering wheel model
        rim_names = [r["name"] for r in KNOWN_RIMS]
        rim_string_list = Gtk.StringList.new(rim_names)
        self.rim_dropdown = Gtk.DropDown.new(rim_string_list, None)
        self.rim_dropdown.set_valign(Gtk.Align.CENTER)

        selected_idx = 0
        for i, r in enumerate(KNOWN_RIMS):
            if r["id"] == self.hardware_config.rim_id:
                selected_idx = i
                break
        self.rim_dropdown.set_selected(selected_idx)
        self.rim_dropdown.connect("notify::selected", self._on_rim_selected)
        self.rim_row.add_suffix(self.rim_dropdown)

        info_group.add(self.rim_row)
        self.add(info_group)

        # 2. Live Axes & Telemetry
        axes_group = Adw.PreferencesGroup()
        axes_group.set_title("Live Axes &amp; Inputs")

        # Helper to build consistent aligned axis rows
        def create_axis_row(title, css_class, default_txt, size_w=240, size_h=14):
            row = Adw.ActionRow()
            row.set_title(title)

            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
            box.set_valign(Gtk.Align.CENTER)

            lbl = Gtk.Label(label=default_txt)
            lbl.set_width_chars(7)
            lbl.set_xalign(1.0)
            lbl.add_css_class("val-badge")

            bar = Gtk.ProgressBar()
            bar.set_size_request(size_w, size_h)
            bar.set_valign(Gtk.Align.CENTER)
            if css_class:
                bar.add_css_class(css_class)

            box.append(lbl)
            box.append(bar)
            row.add_suffix(box)
            return row, lbl, bar

        # Steering
        self.steer_row, self.steer_label, self.steer_bar = create_axis_row(
            "Steering Angle", None, "0.0°", size_w=240
        )
        self.steer_bar.set_fraction(0.5)
        axes_group.add(self.steer_row)

        # Throttle
        self.throttle_row, self.throttle_label, self.throttle_bar = create_axis_row(
            "Throttle (Accelerator)", "gauge-throttle", "0%", size_w=240
        )
        axes_group.add(self.throttle_row)

        # Brake
        self.brake_row, self.brake_label, self.brake_bar = create_axis_row(
            "Brake", "gauge-brake", "0%", size_w=240
        )
        axes_group.add(self.brake_row)

        # Clutch
        self.clutch_row, self.clutch_label, self.clutch_bar = create_axis_row(
            "Clutch", "gauge-clutch", "0%", size_w=240
        )
        axes_group.add(self.clutch_row)

        self.add(axes_group)

        # 3. Button Matrix Visualizer
        btn_group = Adw.PreferencesGroup()
        btn_group.set_title("Button Matrix Live State")
        btn_group.set_description("Buttons, paddles, and FunkySwitch inputs highlight live when pressed")

        self.btn_flow = Gtk.FlowBox()
        self.btn_flow.set_max_children_per_line(9)
        self.btn_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self.btn_flow.set_homogeneous(True)
        self.btn_flow.set_row_spacing(10)
        self.btn_flow.set_column_spacing(10)
        self.btn_flow.set_margin_top(16)
        self.btn_flow.set_margin_bottom(16)
        self.btn_flow.set_margin_start(16)
        self.btn_flow.set_margin_end(16)

        self._rebuild_button_matrix(self.current_rim_info)

        matrix_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        matrix_box.add_css_class("card")
        matrix_box.add_css_class("matrix-card")
        matrix_box.set_margin_top(8)
        matrix_box.set_margin_bottom(8)
        matrix_box.set_margin_start(2)
        matrix_box.set_margin_end(2)
        matrix_box.append(self.btn_flow)

        btn_group.add(matrix_box)
        self.add(btn_group)

    def _create_and_add_chip(self, chip_id, label_text: str) -> Gtk.Label:
        lbl = Gtk.Label(label=label_text)
        lbl.add_css_class("btn-chip")
        lbl.set_size_request(56, 42)
        lbl.set_valign(Gtk.Align.CENTER)
        lbl.set_halign(Gtk.Align.CENTER)
        self._button_chips[chip_id] = lbl
        self.btn_flow.append(lbl)
        return lbl

    def _rebuild_button_matrix(self, rim_info: dict):
        """Dynamically generate the button matrix tailored to the active steering wheel rim."""
        self._button_chips.clear()
        while child := self.btn_flow.get_first_child():
            self.btn_flow.remove(child)

        active_buttons = rim_info.get("active_buttons")
        if active_buttons:
            for btn_num in active_buttons:
                self._create_and_add_chip(btn_num, f"B{btn_num:02d}")
        else:
            btn_count = rim_info.get("button_count", 18)
            for btn_num in range(1, btn_count + 1):
                self._create_and_add_chip(btn_num, f"B{btn_num:02d}")

        if rim_info.get("has_dpad", True):
            hat_inputs = [
                ("HAT_UP", "D-UP"),
                ("HAT_DOWN", "D-DN"),
                ("HAT_LEFT", "D-LT"),
                ("HAT_RIGHT", "D-RT"),
            ]
            for hat_id, hat_label in hat_inputs:
                self._create_and_add_chip(hat_id, hat_label)

    def _on_rim_selected(self, dropdown, param):
        idx = dropdown.get_selected()
        if 0 <= idx < len(KNOWN_RIMS):
            rim_info = KNOWN_RIMS[idx]
            self.hardware_config.rim_id = rim_info["id"]
            save_hardware_config(self.hardware_config)
            self.current_rim_info = rim_info
            if self.device:
                self.device.rim_name = rim_info["name"]
            self.rim_row.set_subtitle(rim_info["subtitle"])

            # Dynamically rebuild button matrix to match newly selected rim
            self._rebuild_button_matrix(rim_info)

            # Update prefix image
            rim_img_path = os.path.join(RESOURCES_DIR, "rims", rim_info.get("image", "formula_v2.png"))
            if os.path.exists(rim_img_path):
                f = Gio.File.new_for_path(rim_img_path)
                tex = Gdk.Texture.new_from_file(f)
                self.rim_thumbnail.set_from_paintable(tex)
                self.rim_thumbnail.set_pixel_size(102)

            if self.on_rim_changed:
                self.on_rim_changed(rim_info)

    def set_connection_status(self, is_online: bool):
        """Update hardware status badge and cards based on connection state."""
        if is_online:
            self.status_dot.remove_css_class("status-dot-offline")
            self.status_dot.add_css_class("status-dot-online")
            self.conn_badge.set_text("Online")
            self.conn_badge.remove_css_class("error")
            self.conn_badge.add_css_class("success")
            base_info = get_base_info(self.device.product_id if self.device else 0x0020)
            self.status_row.set_title(base_info["name"])
            pid_hex = f"0x{self.device.product_id:04X}" if self.device else "0x0020"
            self.status_row.set_subtitle(f"Vendor ID: 0x0EB7 | Product ID: {pid_hex} | PC Mode (Red)")
            self.rim_row.set_subtitle(self.current_rim_info["subtitle"])
        else:
            self.status_dot.remove_css_class("status-dot-online")
            self.status_dot.add_css_class("status-dot-offline")
            self.conn_badge.set_text("Offline")
            self.conn_badge.remove_css_class("success")
            self.conn_badge.add_css_class("error")
            base_info = get_base_info(self.device.product_id if self.device else 0x0020)
            self.status_row.set_title(f"{base_info['name']} (Disconnected)")
            self.status_row.set_subtitle("Hardware disconnected — connect USB or power on wheelbase")
            self.rim_row.set_subtitle("No steering wheel rim detected")
            # Reset live input gauges
            self.update_steering(0.0, 32768)
            self.update_throttle(0.0)
            self.update_brake(0.0)
            self.update_clutch(0.0)
            for btn_id, chip in self._button_chips.items():
                chip.remove_css_class("active")

    def update_steering(self, norm_val: float, raw_val: int):
        deg = norm_val * 450.0
        frac = (norm_val + 1.0) / 2.0
        GLib.idle_add(self._apply_steering, deg, frac)

    def _apply_steering(self, deg, frac):
        self.steer_label.set_text(f"{deg:+.1f}°")
        self.steer_bar.set_fraction(max(0.0, min(1.0, frac)))

    def update_throttle(self, val: float):
        GLib.idle_add(self._apply_throttle, val)

    def _apply_throttle(self, val):
        self.throttle_bar.set_fraction(val)
        self.throttle_label.set_text(f"{int(val * 100)}%")

    def update_brake(self, val: float):
        GLib.idle_add(self._apply_brake, val)

    def _apply_brake(self, val):
        self.brake_bar.set_fraction(val)
        self.brake_label.set_text(f"{int(val * 100)}%")

    def update_clutch(self, val: float):
        GLib.idle_add(self._apply_clutch, val)

    def _apply_clutch(self, val):
        self.clutch_bar.set_fraction(val)
        self.clutch_label.set_text(f"{int(val * 100)}%")

    def update_button(self, btn_id, is_pressed: bool):
        GLib.idle_add(self._apply_button, btn_id, is_pressed)

    def _apply_button(self, btn_id, is_pressed: bool):
        if btn_id not in self._button_chips:
            # Auto-expand chip dynamically if an accessory button is pressed beyond configured count
            if isinstance(btn_id, int) and 1 <= btn_id <= 64:
                self._create_and_add_chip(btn_id, f"B{btn_id:02d}")
            else:
                return

        chip = self._button_chips[btn_id]
        if is_pressed:
            chip.add_css_class("active")
        else:
            chip.remove_css_class("active")
