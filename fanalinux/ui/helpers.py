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
