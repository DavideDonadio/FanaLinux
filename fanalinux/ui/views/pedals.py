"""Standalone USB pedal mapping, independent of wheelbase connectivity."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from fanalinux.core.pedals import PedalMapper, PedalSettings
from fanalinux.ui.helpers import slider_cluster


class PedalsView(Adw.PreferencesPage):
    def __init__(self, on_toast_requested=None):
        super().__init__()
        self._toast = on_toast_requested
        self.settings = PedalSettings.load()
        self.mapper = PedalMapper(self.settings.brake_force)
        group = Adw.PreferencesGroup(title="USB ClubSport V3 Pedals")
        group.set_description(
            "Software brake force for ClubSport V3 / V3 Inverted connected directly over USB. "
            "Select FanaLinux Pedals in your game. Keep FanaLinux open while playing; "
            "disabling mapping or closing the app restores the physical device. "
            "Quit BrakeTune before enabling this mapper.")
        row = Adw.ActionRow(title="Enable pedal mapping")
        row.set_subtitle("Hide physical pedal input while the virtual controller is active")
        toggle = Gtk.Switch(valign=Gtk.Align.CENTER)
        toggle.set_active(self.settings.enabled)
        toggle.connect("notify::active", self._toggle)
        row.add_suffix(toggle)
        row.set_activatable_widget(toggle)
        group.add(row)

        force_row = Adw.ActionRow(title="Brake force")
        force_row.set_subtitle("100% uses the full range; 20% reaches full braking at one fifth of the range")
        cluster, _, self._force_label = slider_cluster(
            1, 100, 1, self.settings.brake_force, unit="%", width=220,
            badge_width=5, on_change=self._force_changed)
        force_row.add_suffix(cluster)
        group.add(force_row)
        self.status_row = Adw.ActionRow(title="Status")
        group.add(self.status_row)
        self.add(group)

        live = Adw.PreferencesGroup(title="Live brake input")
        self._bars = []
        for title in ("Physical pedal", "Game output"):
            row = Adw.ActionRow(title=title)
            bar = Gtk.ProgressBar(valign=Gtk.Align.CENTER, show_text=True)
            bar.set_size_request(220, -1)
            row.add_suffix(bar)
            live.add(row)
            self._bars.append(bar)
        self.add(live)
        if self.settings.enabled:
            self.mapper.start()
        self._refresh()
        self._timer = GLib.timeout_add(50, self._refresh)

    def _save(self):
        if not self.settings.save() and self._toast:
            self._toast("Could not save pedal settings")

    def _toggle(self, switch, _param):
        self.settings.enabled = switch.get_active()
        self._save()
        if self.settings.enabled:
            self.mapper.start()
        else:
            self.mapper.stop()

    def _force_changed(self, value):
        self.settings.brake_force = int(value)
        self._force_label.set_text(f"{int(value)}%")
        self.mapper.set_force(value)
        self._save()

    def _refresh(self):
        self.status_row.set_subtitle(self.mapper.status)
        for bar, value in zip(self._bars, (self.mapper.input, self.mapper.output)):
            bar.set_fraction(value)
            bar.set_text(f"{value:.0%}")
        return True

    def stop(self):
        GLib.source_remove(self._timer)
        self.mapper.stop()
