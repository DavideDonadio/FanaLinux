"""
UI Helpers for FanaLinux.
Provides unified layout helpers, styling utilities, and widget adjusters.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk


def attach_spin_button(box, adjustment, digits: int = 0):
    """Append a numeric entry bound to the same Adjustment as a slider.
    Typing an exact value and dragging stay in sync with zero extra wiring."""
    spin = Gtk.SpinButton.new(adjustment, adjustment.get_step_increment() or 1, digits)
    spin.set_numeric(True)
    spin.set_snap_to_ticks(False)
    spin.set_width_chars(7 if digits else 6)
    spin.set_valign(Gtk.Align.CENTER)
    box.append(spin)
    return spin


def slider_cluster(min_val, max_val, step, value, unit="", digits=0, width=220,
                   badge_width=6, on_change=None):
    """Badge + slider + numeric entry sharing one Adjustment. Returns (box, adj, label).
    Move each caller's existing value-changed body into on_change(raw_value) unchanged."""
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    box.set_valign(Gtk.Align.CENTER)

    def _format(v):
        return f"{v:.{digits}f}{unit}" if digits else f"{int(v)}{unit}"

    lbl = Gtk.Label(label=_format(value))
    lbl.set_width_chars(badge_width)
    lbl.set_xalign(1.0)
    lbl.add_css_class("val-badge")

    adj = Gtk.Adjustment(
        value=value,
        lower=min_val,
        upper=max_val,
        step_increment=step,
        page_increment=step * 5
    )
    scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
    scale.set_size_request(width, -1)
    scale.set_valign(Gtk.Align.CENTER)
    scale.set_draw_value(False)

    def _handler(a):
        if on_change is not None:
            on_change(a.get_value())
        else:
            lbl.set_text(_format(a.get_value()))

    adj.connect("value-changed", _handler)

    box.append(lbl)
    box.append(scale)
    attach_spin_button(box, adj, digits)
    return box, adj, lbl


def widen_page_clamp(page, max_size: int = 1180, tightening_threshold: int = 1080) -> bool:
    """
    Ensure an Adw.PreferencesPage clamp expands to utilize available wide-window space.
    Designed to be scheduled via GLib.idle_add(widen_page_clamp, page).
    """
    try:
        sw = page.get_first_child()
        if sw:
            vp = sw.get_first_child()
            if vp:
                clamp = vp.get_first_child()
                if isinstance(clamp, Adw.Clamp):
                    clamp.set_maximum_size(max_size)
                    clamp.set_tightening_threshold(tightening_threshold)
    except Exception:
        pass
    return False
