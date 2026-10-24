"""Regression tests for review findings #3, #4, #5 (offline, no hardware)."""
import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestConnectReturnValue(unittest.TestCase):
    def test_init_failure_returns_false(self):
        """connect() must not report success when init disconnects internally."""
        from fanalinux.core.device import FanatecDevice
        dev = FanatecDevice()
        dev.find_hidraw_path = lambda: os.devnull

        def fatal_write(data):
            dev.disconnect()
            return 0

        dev.write_report = fatal_write
        self.assertFalse(dev.connect())
        self.assertFalse(dev.connected)


class TestSteeringNormalization(unittest.TestCase):
    def _listener(self, center, min_v, max_v):
        from fanalinux.core.evdev_listener import EvdevListener, EV_ABS, ABS_X
        l = EvdevListener()
        l.center_raw = center
        l._axis_ranges = {ABS_X: (min_v, max_v)}
        got = []
        l.on_steering = lambda norm, raw: got.append((norm, raw))
        l._process_event(EV_ABS, ABS_X, 65535)
        l._process_event(EV_ABS, ABS_X, 0)
        l._process_event(EV_ABS, ABS_X, center)
        return [n for n, _ in got]

    def test_symmetric_full_range(self):
        right, left, middle = self._listener(32768, 0, 65535)
        self.assertAlmostEqual(right, 1.0)
        self.assertAlmostEqual(left, -1.0)
        self.assertAlmostEqual(middle, 0.0)

    def test_off_center_no_early_clip(self):
        """Off-midpoint calibrated center must still reach +/-1.0 at the stops."""
        right, left, middle = self._listener(33768, 0, 65535)
        self.assertAlmostEqual(right, 1.0)
        self.assertAlmostEqual(left, -1.0)
        self.assertAlmostEqual(middle, 0.0)


class TestGameSwitchTelemetry(unittest.TestCase):
    def _window_with_fake_mgr(self):
        from gi.repository import Adw
        Adw.init()
        from fanalinux.ui.window import MainWindow
        win = MainWindow()
        calls = []

        class FakeMgr:
            enabled = False

            def start(self, telemetry_type=None):
                self.enabled = True
                calls.append(("start", telemetry_type))

            def stop(self):
                self.enabled = False
                calls.append(("stop",))

        win.telemetry_mgr = FakeMgr()
        return win, calls

    def test_direct_switch_stops_previous(self):
        """A->B with B telemetry off must stop A's telemetry (no stopped event fires)."""
        win, calls = self._window_with_fake_mgr()
        try:
            game_a = {"id": "ac", "name": "Assetto Corsa", "telemetry_type": "ac_udp"}
            game_b = {"id": "ams2", "name": "Automobilista 2"}
            win._apply_game_started(game_a, "Default", True)
            self.assertIn(("start", "ac_udp"), calls)
            win._apply_game_started(game_b, "Default", False)
            self.assertIn(("stop",), calls)
            self.assertEqual(len([c for c in calls if c[0] == "start"]), 1)
        finally:
            win.detector.stop()

    def test_manual_telemetry_survives_new_game(self):
        """Telemetry with no game behind it must not be killed by a game detection."""
        win, calls = self._window_with_fake_mgr()
        try:
            win.telemetry_mgr.enabled = True  # manually started, no game
            game_b = {"id": "ams2", "name": "Automobilista 2"}
            win._apply_game_started(game_b, "Default", False)
            self.assertNotIn(("stop",), calls)
        finally:
            win.detector.stop()

    def test_same_game_restart_keeps_session(self):
        """Same game re-detected (e.g. new PID) must not bounce telemetry."""
        win, calls = self._window_with_fake_mgr()
        try:
            game_a = {"id": "ac", "name": "Assetto Corsa", "telemetry_type": "ac_udp"}
            win._apply_game_started(game_a, "Default", True)
            win._apply_game_started(game_a, "Default", True)
            self.assertNotIn(("stop",), calls)
        finally:
            win.detector.stop()


class TestUdevRule(unittest.TestCase):
    def test_no_world_writable_mode(self):
        rule = PROJECT_ROOT / "udev" / "99-fanatec-fanalinux.rules"
        text = rule.read_text()
        self.assertNotIn("0666", text)
        self.assertIn("uaccess", text)


if __name__ == "__main__":
    unittest.main()
