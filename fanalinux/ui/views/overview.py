"""
Overview View: Hardware Status, Live Gauges, and Button Matrix.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib


class OverviewView(Adw.PreferencesPage):
    def __init__(self, device):
        super().__init__()
        self.device = device
        self._button_chips = {}
        self._build_ui()

    def _build_ui(self):
        # 1. Device Info Card
        info_group = Adw.PreferencesGroup()
        info_group.set_title("Hardware Status")

        self.status_row = Adw.ActionRow()
        self.status_row.set_title("Fanatec CSL DD")
        self.status_row.set_subtitle("Vendor ID: 0x0EB7 | Product ID: 0x0020 | PC Mode (Red)")
        self.status_row.set_icon_name("input-gaming-symbolic")

        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        status_box.set_valign(Gtk.Align.CENTER)

        self.status_dot = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
        self.status_dot.add_css_class("success")
        status_box.append(self.status_dot)

        self.conn_badge = Gtk.Label(label="Online")
        self.conn_badge.add_css_class("success")
        self.conn_badge.add_css_class("heading")
        status_box.append(self.conn_badge)

        self.status_row.add_suffix(status_box)
        info_group.add(self.status_row)

        self.rim_row = Adw.ActionRow()
        self.rim_row.set_title("Steering Wheel Rim")
        self.rim_row.set_subtitle("ClubSport Steering Wheel Formula V2.5 (15 Multi-Color LEDs)")
        self.rim_row.set_icon_name("applications-games-symbolic")
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
        btn_group.set_description("Buttons and shifter paddles highlight live when pressed")

        btn_flow = Gtk.FlowBox()
        btn_flow.set_max_children_per_line(8)
        btn_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        btn_flow.set_homogeneous(True)
        btn_flow.set_row_spacing(8)
        btn_flow.set_column_spacing(8)

        for btn_num in range(1, 25):
            lbl = Gtk.Label(label=f"B{btn_num:02d}")
            lbl.add_css_class("btn-chip")
            lbl.set_size_request(52, 38)
            lbl.set_valign(Gtk.Align.CENTER)
            lbl.set_halign(Gtk.Align.CENTER)
            self._button_chips[btn_num] = lbl
            btn_flow.append(lbl)

        matrix_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        matrix_box.add_css_class("card")
        matrix_box.set_margin_top(4)
        matrix_box.set_margin_bottom(4)
        matrix_box.set_margin_start(4)
        matrix_box.set_margin_end(4)
        matrix_box.append(btn_flow)

        btn_group.add(matrix_box)
        self.add(btn_group)

    def set_connection_status(self, is_online: bool):
        """Update hardware status badge and cards based on connection state."""
        if is_online:
            self.status_dot.set_from_icon_name("emblem-ok-symbolic")
            self.status_dot.remove_css_class("error")
            self.status_dot.add_css_class("success")
            self.conn_badge.set_text("Online")
            self.conn_badge.remove_css_class("error")
            self.conn_badge.add_css_class("success")
            self.status_row.set_title(self.device.product_name if self.device else "Fanatec CSL DD")
            self.status_row.set_subtitle("Vendor ID: 0x0EB7 | Product ID: 0x0020 | PC Mode (Red)")
            self.rim_row.set_subtitle(f"{self.device.rim_name if self.device else 'Formula V2.5'} (15 Multi-Color LEDs)")
        else:
            self.status_dot.set_from_icon_name("network-offline-symbolic")
            self.status_dot.remove_css_class("success")
            self.status_dot.add_css_class("error")
            self.conn_badge.set_text("Offline")
            self.conn_badge.remove_css_class("success")
            self.conn_badge.add_css_class("error")
            self.status_row.set_title("Fanatec CSL DD (Disconnected)")
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

    def update_button(self, code: int, is_pressed: bool):
        btn_idx = (code - 288 + 1) if code >= 288 else (code % 24 + 1)
        GLib.idle_add(self._apply_button, btn_idx, is_pressed)

    def _apply_button(self, btn_idx: int, is_pressed: bool):
        if btn_idx in self._button_chips:
            chip = self._button_chips[btn_idx]
            if is_pressed:
                chip.add_css_class("active")
            else:
                chip.remove_css_class("active")
