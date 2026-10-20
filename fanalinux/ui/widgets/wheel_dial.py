"""
Circular Steering Wheel Center Calibration Dial Widget.
Matches the official Fanatec App Wheel Center visualizer (Screenshot 2).
"""

import math
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib
from typing import Optional, Callable


class WheelDialWidget(Gtk.Box):
    def __init__(self, on_calibrate_clicked: Optional[Callable[[], None]] = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.on_calibrate_clicked = on_calibrate_clicked
        self.angle_deg = 0.0

        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)
        self.set_margin_top(12)
        self.set_margin_bottom(12)

        # 1. Circular Drawing Area (260x260)
        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.set_content_width(260)
        self.drawing_area.set_content_height(260)
        self.drawing_area.set_draw_func(self._draw_dial)
        self.append(self.drawing_area)

        # 2. Big Calibration Button
        self.cal_btn = Gtk.Button(label="WHEEL CENTER CALIBRATION")
        self.cal_btn.set_size_request(240, 44)
        self.cal_btn.set_halign(Gtk.Align.CENTER)
        self.cal_btn.add_css_class("suggested-action")
        self.cal_btn.add_css_class("pill")
        self.cal_btn.connect("clicked", self._on_btn_clicked)
        self.append(self.cal_btn)

    def set_angle(self, degrees: float):
        """Update angle and redraw."""
        if abs(self.angle_deg - degrees) > 0.1:
            self.angle_deg = float(degrees)
            self.drawing_area.queue_draw()

    def _on_btn_clicked(self, btn):
        if self.on_calibrate_clicked:
            self.on_calibrate_clicked()

    def _draw_dial(self, area, cr, width, height):
        cx = width / 2.0
        cy = height / 2.0
        r = min(cx, cy) - 22.0

        # Background circular glow / dark disk
        cr.save()
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.set_source_rgba(0.12, 0.14, 0.17, 0.6)
        cr.fill_preserve()
        cr.set_source_rgba(0.28, 0.32, 0.38, 0.8)
        cr.set_line_width(2.0)
        cr.stroke()
        cr.restore()

        # Dashed alignment crosshairs
        cr.save()
        cr.set_source_rgba(0.4, 0.45, 0.52, 0.35)
        cr.set_line_width(1.0)
        cr.set_dash([4.0, 4.0], 0)
        # Horizontal
        cr.move_to(cx - r, cy)
        cr.line_to(cx + r, cy)
        # Vertical
        cr.move_to(cx, cy - r)
        cr.line_to(cx, cy + r)
        cr.stroke()
        cr.restore()

        # Degree tick marks around the ring
        cr.save()
        for deg in range(0, 360, 15):
            rad = math.radians(deg)
            is_cardinal = (deg % 90 == 0)
            tick_len = 10.0 if is_cardinal else (6.0 if deg % 30 == 0 else 3.0)
            r1 = r - 2.0
            r2 = r1 - tick_len

            x1 = cx + r1 * math.cos(rad)
            y1 = cy + r1 * math.sin(rad)
            x2 = cx + r2 * math.cos(rad)
            y2 = cy + r2 * math.sin(rad)

            if is_cardinal:
                cr.set_source_rgba(0.9, 0.75, 0.2, 0.9)  # Fanatec Yellow accent
                cr.set_line_width(2.0)
            else:
                cr.set_source_rgba(0.55, 0.6, 0.68, 0.6)
                cr.set_line_width(1.2)

            cr.move_to(x1, y1)
            cr.line_to(x2, y2)
            cr.stroke()
        cr.restore()

        # Center Rotating Steering Wheel
        cr.save()
        cr.translate(cx, cy)
        cr.rotate(math.radians(self.angle_deg))

        # Stylized Formula / GT Rim
        # Main center hub / screen box
        cr.set_source_rgba(0.2, 0.23, 0.28, 0.95)
        cr.rectangle(-32, -22, 64, 44)
        cr.fill_preserve()
        cr.set_source_rgba(0.9, 0.75, 0.2, 0.9)  # Gold/Yellow accent border
        cr.set_line_width(1.5)
        cr.stroke()

        # RevLED strip atop hub
        cr.set_source_rgba(0.1, 0.8, 1.0, 0.85)  # Cyan/Blue LEDs
        for lx in (-24, -12, 0, 12, 24):
            cr.arc(lx, -16, 2.5, 0, 2 * math.pi)
            cr.fill()

        # Horizontal spokes connecting to grips
        cr.set_source_rgba(0.25, 0.29, 0.35, 0.9)
        cr.rectangle(-75, -12, 45, 24)
        cr.rectangle(30, -12, 45, 24)
        cr.fill()

        # Left Grip
        cr.set_source_rgba(0.15, 0.17, 0.21, 1.0)
        cr.arc(-72, 0, 26, math.pi * 0.5, math.pi * 1.5)
        cr.set_line_width(16.0)
        cr.stroke()

        # Right Grip
        cr.arc(72, 0, 26, -math.pi * 0.5, math.pi * 0.5)
        cr.set_line_width(16.0)
        cr.stroke()

        # Top 12 o'clock center alignment stripe
        cr.set_source_rgba(0.95, 0.25, 0.25, 0.9)  # Red top center marker
        cr.move_to(0, -r + 2)
        cr.line_to(0, -r + 14)
        cr.set_line_width(3.0)
        cr.stroke()

        cr.restore()

        # 4. Top Angle Badge Bubble (matches the "-2°" oval in Screenshot 2)
        cr.save()
        badge_w = 64.0
        badge_h = 28.0
        badge_x = cx - (badge_w / 2.0)
        badge_y = cy - r + 18.0

        # Draw rounded pill badge
        cr.set_source_rgba(0.1, 0.12, 0.15, 0.95)
        cr.arc(badge_x + 14, badge_y + 14, 14, math.pi * 0.5, math.pi * 1.5)
        cr.arc(badge_x + badge_w - 14, badge_y + 14, 14, -math.pi * 0.5, math.pi * 0.5)
        cr.close_path()
        cr.fill_preserve()

        # Yellow accent border when near 0, silver when off-center
        if abs(self.angle_deg) < 1.0:
            cr.set_source_rgba(0.3, 0.85, 0.4, 0.9)  # Green when dead centered!
        else:
            cr.set_source_rgba(0.85, 0.75, 0.25, 0.85)
        cr.set_line_width(1.5)
        cr.stroke()

        # Angle Text inside bubble
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.95)
        cr.select_font_face("Sans", 0, 1)  # Bold
        cr.set_font_size(13.0)
        txt = f"{int(round(self.angle_deg))}°"
        extents = cr.text_extents(txt)
        tx = cx - (extents.width / 2.0)
        ty = badge_y + (badge_h / 2.0) + (extents.height / 2.0) - 1
        cr.move_to(tx, ty)
        cr.show_text(txt)
        cr.restore()
