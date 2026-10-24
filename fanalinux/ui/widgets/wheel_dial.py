"""
Circular Steering Wheel Center Calibration Dial Widget.
Features high-resolution Formula V2.5 rim rendering with real-time rotation
and an interactive calibration animation.
"""

import math
import os
import time

import cairo
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from collections.abc import Callable

from gi.repository import GLib, Gtk

from fanalinux.core.hardware import get_rim_info, load_hardware_config

RESOURCES_RIMS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "resources", "rims"
)


class WheelDialWidget(Gtk.Box):
    def __init__(self, on_calibrate_clicked: Callable[[], None] | None = None,
                 on_reset_clicked: Callable[[], None] | None = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.on_calibrate_clicked = on_calibrate_clicked
        self.on_reset_clicked = on_reset_clicked
        self.angle_deg = 0.0

        # Animation state
        self._animating = False
        self._anim_start_time = 0.0
        self._anim_duration = 0.6  # seconds
        self._anim_start_angle = 0.0
        self._anim_source_id = None
        self._just_calibrated = False

        # Load Rim Surface for currently configured rim
        self._rim_surface = None
        hw_config = load_hardware_config()
        self.set_rim(get_rim_info(hw_config.rim_id))

        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)
        self.set_margin_top(10)
        self.set_margin_bottom(14)

        # 1. Circular Drawing Area (270x270 - calibrated for exact 2-column baseline alignment)
        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.set_content_width(270)
        self.drawing_area.set_content_height(270)
        self.drawing_area.set_draw_func(self._draw_dial)
        self.append(self.drawing_area)

        # 2. Action Buttons (Calibrate + Reset)
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_box.set_halign(Gtk.Align.CENTER)

        self.cal_btn = Gtk.Button(label="Calibrate Center")
        self.cal_btn.set_size_request(160, 40)
        self.cal_btn.set_halign(Gtk.Align.CENTER)
        self.cal_btn.add_css_class("suggested-action")
        self.cal_btn.add_css_class("pill")
        self.cal_btn.connect("clicked", self._on_btn_clicked)
        btn_box.append(self.cal_btn)

        self.reset_btn = Gtk.Button(label="Reset to Factory 0°")
        self.reset_btn.set_size_request(150, 40)
        self.reset_btn.set_halign(Gtk.Align.CENTER)
        self.reset_btn.add_css_class("pill")
        self.reset_btn.connect("clicked", self._on_reset_btn_clicked)
        btn_box.append(self.reset_btn)

        self.append(btn_box)

    def set_rim(self, rim_info: dict):
        """Set or update the active steering wheel rim image rendered on the dial."""
        rim_filename = rim_info.get("image", "formula_v2.png")
        rim_path = os.path.join(RESOURCES_RIMS_DIR, rim_filename)
        if os.path.exists(rim_path):
            try:
                self._rim_surface = cairo.ImageSurface.create_from_png(rim_path)
                if hasattr(self, "drawing_area"):
                    self.drawing_area.queue_draw()
            except Exception as e:
                print(f"Warning: could not load rim image: {e}")

    def set_angle(self, degrees: float):
        """Update angle from hardware if not currently running the calibration animation."""
        if not self._animating:
            if abs(self.angle_deg - degrees) > 0.1:
                self.angle_deg = float(degrees)
                self.drawing_area.queue_draw()

    def _on_btn_clicked(self, btn):
        # Trigger the smooth calibration animation and device command
        self._start_calibration_animation()
        if self.on_calibrate_clicked:
            self.on_calibrate_clicked()

    def _on_reset_btn_clicked(self, btn):
        self._start_calibration_animation()
        if self.on_reset_clicked:
            self.on_reset_clicked()

    def _start_calibration_animation(self):
        if self._anim_source_id:
            GLib.source_remove(self._anim_source_id)

        self._animating = True
        self._just_calibrated = True
        self._anim_start_angle = self.angle_deg
        self._anim_start_time = time.time()
        self._anim_source_id = GLib.timeout_add(16, self._anim_step)

    def _anim_step(self):
        elapsed = time.time() - self._anim_start_time
        progress = min(1.0, elapsed / self._anim_duration)

        # Smooth cubic ease-out to zero
        ease = 1.0 - math.pow(1.0 - progress, 3)
        self.angle_deg = self._anim_start_angle * (1.0 - ease)

        self.drawing_area.queue_draw()

        if progress >= 1.0:
            self.angle_deg = 0.0
            self._animating = False
            self._anim_source_id = None
            GLib.timeout_add_seconds(2, self._clear_calibrated_badge)
            return False  # Stop timer
        return True

    def _clear_calibrated_badge(self):
        self._just_calibrated = False
        self.drawing_area.queue_draw()
        return False

    def _draw_dial(self, area, cr, width, height):
        cx = width / 2.0
        cy = height / 2.0
        r = min(cx, cy) - 20.0

        # 1. Dark sleek circular dial background
        cr.save()
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.set_source_rgba(0.09, 0.11, 0.14, 0.7)
        cr.fill_preserve()
        cr.set_source_rgba(0.24, 0.28, 0.35, 0.8)
        cr.set_line_width(2.0)
        cr.stroke()
        cr.restore()

        # 2. Calibration Ripple Wave effect if animating
        if self._animating:
            elapsed = time.time() - self._anim_start_time
            anim_prog = min(1.0, elapsed / self._anim_duration)
            ripple_r = 20.0 + (anim_prog * (r - 20.0))
            alpha = max(0.0, 1.0 - anim_prog)

            cr.save()
            cr.arc(cx, cy, ripple_r, 0, 2 * math.pi)
            cr.set_source_rgba(0.2, 0.9, 0.4, alpha * 0.7)
            cr.set_line_width(4.0)
            cr.stroke()
            cr.restore()

        # 3. Dashed alignment crosshairs
        cr.save()
        cr.set_source_rgba(0.4, 0.45, 0.52, 0.3)
        cr.set_line_width(1.0)
        cr.set_dash([4.0, 4.0], 0)
        cr.move_to(cx - r + 4, cy)
        cr.line_to(cx + r - 4, cy)
        cr.move_to(cx, cy - r + 4)
        cr.line_to(cx, cy + r - 4)
        cr.stroke()
        cr.restore()

        # 4. Degree ticks around perimeter
        cr.save()
        for deg in range(0, 360, 15):
            rad = math.radians(deg)
            is_cardinal = (deg % 90 == 0)
            tick_len = 10.0 if is_cardinal else (6.0 if deg % 30 == 0 else 3.5)
            r1 = r - 3.0
            r2 = r1 - tick_len

            x1 = cx + r1 * math.cos(rad)
            y1 = cy + r1 * math.sin(rad)
            x2 = cx + r2 * math.cos(rad)
            y2 = cy + r2 * math.sin(rad)

            if is_cardinal:
                cr.set_source_rgba(0.95, 0.78, 0.2, 0.9)  # Fanatec Gold/Yellow
                cr.set_line_width(2.2)
            else:
                cr.set_source_rgba(0.5, 0.56, 0.65, 0.5)
                cr.set_line_width(1.2)

            cr.move_to(x1, y1)
            cr.line_to(x2, y2)
            cr.stroke()
        cr.restore()

        # 5. Real ClubSport Formula V2.5 Rim (Rotates smoothly in real time)
        cr.save()
        cr.translate(cx, cy)
        cr.rotate(math.radians(self.angle_deg))

        if self._rim_surface:
            # High-res authentic ClubSport Formula V2.5 rendering
            sw = self._rim_surface.get_width()
            sh = self._rim_surface.get_height()
            target_dim = (r - 24.0) * 2.0  # Scale nicely within the 250x250 circular dial
            scale = target_dim / max(sw, sh)

            cr.scale(scale, scale)
            cr.set_source_surface(self._rim_surface, -sw / 2.0, -sh / 2.0)
            cr.paint()
        else:
            # Fallback stylized rim if image unavailable
            cr.set_source_rgba(0.2, 0.23, 0.28, 0.95)
            cr.rectangle(-32, -22, 64, 44)
            cr.fill_preserve()
            cr.set_source_rgba(0.9, 0.75, 0.2, 0.9)
            cr.set_line_width(1.5)
            cr.stroke()
            cr.arc(-72, 0, 26, math.pi * 0.5, math.pi * 1.5)
            cr.arc(72, 0, 26, -math.pi * 0.5, math.pi * 0.5)
            cr.stroke()

        cr.restore()

        # 6. Top 12 o'clock center alignment pointer
        cr.save()
        cr.set_source_rgba(0.95, 0.25, 0.25, 0.9)
        cr.move_to(cx, cy - r + 3)
        cr.line_to(cx, cy - r + 13)
        cr.set_line_width(3.0)
        cr.stroke()
        cr.restore()

        # 7. Top Angle Badge Bubble
        cr.save()
        badge_w = 84.0 if self._just_calibrated else 72.0
        badge_h = 30.0
        badge_x = cx - (badge_w / 2.0)
        badge_y = cy - r + 16.0

        cr.arc(badge_x + 15, badge_y + 15, 15, math.pi * 0.5, math.pi * 1.5)
        cr.arc(badge_x + badge_w - 15, badge_y + 15, 15, -math.pi * 0.5, math.pi * 0.5)
        cr.close_path()

        if self._just_calibrated:
            cr.set_source_rgba(0.12, 0.35, 0.18, 0.95)
            cr.fill_preserve()
            cr.set_source_rgba(0.3, 0.95, 0.45, 1.0)
        elif abs(self.angle_deg) < 1.0:
            cr.set_source_rgba(0.1, 0.12, 0.15, 0.95)
            cr.fill_preserve()
            cr.set_source_rgba(0.3, 0.85, 0.4, 0.9)
        else:
            cr.set_source_rgba(0.1, 0.12, 0.15, 0.95)
            cr.fill_preserve()
            cr.set_source_rgba(0.85, 0.75, 0.25, 0.85)

        cr.set_line_width(1.5)
        cr.stroke()

        cr.set_source_rgba(1.0, 1.0, 1.0, 0.95)
        cr.select_font_face("Sans", 0, 1)
        cr.set_font_size(14.0)
        txt = "0.0° ✓" if self._just_calibrated else f"{int(round(self.angle_deg))}°"
        extents = cr.text_extents(txt)
        tx = cx - (extents.width / 2.0)
        ty = badge_y + (badge_h / 2.0) + (extents.height / 2.0) - 1
        cr.move_to(tx, ty)
        cr.show_text(txt)
        cr.restore()
