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

        self.conn_badge = Gtk.Label(label="Online")
        self.conn_badge.add_css_class("success")
        self.conn_badge.add_css_class("title-4")
        self.status_row.add_suffix(self.conn_badge)
        info_group.add(self.status_row)

        self.rim_row = Adw.ActionRow()
        self.rim_row.set_title("Steering Wheel Rim")
        self.rim_row.set_subtitle("ClubSport Steering Wheel Formula V2.5")
        self.rim_row.set_icon_name("applications-games-symbolic")
        info_group.add(self.rim_row)

        self.add(info_group)

        # 2. Live Axes & Telemetry
        axes_group = Adw.PreferencesGroup()
        axes_group.set_title("Live Axes &amp; Inputs")

        # Steering
        self.steer_row = Adw.ActionRow()
        self.steer_row.set_title("Steering Angle")
        self.steer_label = Gtk.Label(label="0.0°")
        self.steer_label.add_css_class("numeric")
        self.steer_label.add_css_class("heading")
        self.steer_row.add_suffix(self.steer_label)

        self.steer_bar = Gtk.ProgressBar()
        self.steer_bar.set_fraction(0.5)
        self.steer_bar.set_size_request(240, 16)
        self.steer_row.add_suffix(self.steer_bar)
        axes_group.add(self.steer_row)

        # Throttle
        self.throttle_row = Adw.ActionRow()
        self.throttle_row.set_title("Throttle (Accelerator)")
        self.throttle_bar = Gtk.ProgressBar()
        self.throttle_bar.set_fraction(0.0)
        self.throttle_bar.add_css_class("success")
        self.throttle_bar.set_size_request(240, 16)
        self.throttle_label = Gtk.Label(label="0%")
        self.throttle_row.add_suffix(self.throttle_label)
        self.throttle_row.add_suffix(self.throttle_bar)
        axes_group.add(self.throttle_row)

        # Brake
        self.brake_row = Adw.ActionRow()
        self.brake_row.set_title("Brake")
        self.brake_bar = Gtk.ProgressBar()
        self.brake_bar.set_fraction(0.0)
        self.brake_bar.add_css_class("destructive")
        self.brake_bar.set_size_request(240, 16)
        self.brake_label = Gtk.Label(label="0%")
        self.brake_row.add_suffix(self.brake_label)
        self.brake_row.add_suffix(self.brake_bar)
        axes_group.add(self.brake_row)

        # Clutch
        self.clutch_row = Adw.ActionRow()
        self.clutch_row.set_title("Clutch")
        self.clutch_bar = Gtk.ProgressBar()
        self.clutch_bar.set_fraction(0.0)
        self.clutch_bar.set_size_request(240, 16)
        self.clutch_label = Gtk.Label(label="0%")
        self.clutch_row.add_suffix(self.clutch_label)
        self.clutch_row.add_suffix(self.clutch_bar)
        axes_group.add(self.clutch_row)

        self.add(axes_group)

        # 3. Button Matrix Visualizer
        btn_group = Adw.PreferencesGroup()
        btn_group.set_title("Button Matrix Live State")

        btn_flow = Gtk.FlowBox()
        btn_flow.set_max_children_per_line(8)
        btn_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        btn_flow.set_homogeneous(True)

        for btn_num in range(1, 25):
            lbl = Gtk.Label(label=f"B{btn_num}")
            lbl.set_size_request(48, 36)
            lbl.add_css_class("card")
            lbl.set_margin_start(4)
            lbl.set_margin_end(4)
            lbl.set_margin_top(4)
            lbl.set_margin_bottom(4)
            self._button_chips[btn_num] = lbl
            btn_flow.append(lbl)

        btn_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        btn_card.add_css_class("card")
        btn_card.set_margin_top(8)
        btn_card.set_margin_bottom(8)
        btn_card.append(btn_flow)
        btn_group.add(btn_card)

        self.add(btn_group)

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
                chip.add_css_class("suggested-action")
            else:
                chip.remove_css_class("suggested-action")
