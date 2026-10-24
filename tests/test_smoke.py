"""
Automated smoke test suite for FanaLinux.
Walks the entire package tree, imports all modules, instantiates core classes,
and calls hardware discovery routines without hardware present to ensure zero
NameError, AttributeError, or syntax errors on startup.
"""

import importlib
import pkgutil
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import fanalinux


class TestSmoke(unittest.TestCase):
    def test_import_all_submodules(self):
        """Walk and import every module under the fanalinux package."""
        prefix = fanalinux.__name__ + "."
        for _, modname, ispkg in pkgutil.walk_packages(fanalinux.__path__, prefix):
            with self.subTest(module=modname):
                try:
                    mod = importlib.import_module(modname)
                    self.assertIsNotNone(mod)
                except Exception as e:
                    self.fail(f"Failed to import {modname}: {e}")

    def test_device_discovery_cold_path(self):
        """Instantiate FanatecDevice and execute discovery without physical hardware."""
        from fanalinux.core.device import FanatecDevice
        dev = FanatecDevice()
        self.assertIsNotNone(dev)
        
        # Must execute cleanly without NameError (e.g. PID definitions) or unhandled exceptions
        hidraw_path = dev.find_hidraw_path()
        if hidraw_path is not None:
            self.skipTest("Fanatec hardware present; cold-path test requires no hardware")
        self.assertIsNone(hidraw_path)

        is_connected = dev.check_connection()
        self.assertIsInstance(is_connected, bool)
        self.assertFalse(is_connected)

        dev.disconnect()
        self.assertFalse(dev.connected)

    def test_detector_catalog_and_icons(self):
        """Instantiate GameDetector and verify game catalog and icon path resolutions."""
        from fanalinux.core.detector import BUILTIN_GAMES, GameDetector
        detector = GameDetector()
        self.assertGreaterEqual(len(detector.get_all_games()), 14)

        for game in BUILTIN_GAMES:
            gid = game["id"]
            icon_path = detector.get_game_icon_path(gid)
            self.assertIsNotNone(icon_path, f"Icon path for {gid} should resolve")
            self.assertTrue(Path(icon_path).exists(), f"Icon file for {gid} should exist on disk: {icon_path}")

    def test_telemetry_manager_initialization(self):
        """Instantiate TelemetryManager and verify clients can be retrieved cleanly."""
        from fanalinux.core.device import FanatecDevice
        from fanalinux.core.telemetry.manager import (
            TELEMETRY_FACTORIES,
            TelemetryManager,
        )
        dev = FanatecDevice()
        mgr = TelemetryManager(dev)
        self.assertFalse(mgr.is_connected)
        self.assertFalse(mgr.is_running)

        for telem_type in TELEMETRY_FACTORIES:
            client = mgr._get_client(telem_type)
            self.assertIsNotNone(client)
            self.assertFalse(client.is_connected)

    def test_ui_window_instantiation(self):
        """Instantiate Libadwaita MainWindow and verify all view pages attach cleanly."""
        import gi
        gi.require_version('Gtk', '4.0')
        gi.require_version('Adw', '1')
        from gi.repository import Adw
        Adw.init()

        from fanalinux.ui.window import MainWindow
        win = MainWindow()
        self.addCleanup(win._on_close, None)
        self.assertIsNotNone(win)
        self.assertIsNotNone(win.overview_view)
        self.assertIsNotNone(win.tuning_view)
        self.assertIsNotNone(win.vibration_view)
        self.assertIsNotNone(win.leds_view)
        self.assertIsNotNone(win.profiles_view)
        self.assertIsNotNone(win.calibration_view)


if __name__ == "__main__":
    unittest.main()
