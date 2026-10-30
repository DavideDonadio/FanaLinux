"""Manual LED controls must yield while a native-driver game owns the wheel."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from gi.repository import Adw

from fanalinux.core.detector import NATIVE_DRIVER_IDS
from fanalinux.ui.views.leds import LedsView


class TestNativeGameLedYield(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Adw.init()

    def test_manual_controls_toggle(self):
        view = LedsView(MagicMock(), telemetry_mgr=MagicMock())
        self.assertTrue(len(view._manual_led_widgets) >= 8)
        view.set_native_game_active(True)
        self.assertTrue(all(not w.get_sensitive() for w in view._manual_led_widgets))
        view.set_native_game_active(False)
        self.assertTrue(all(w.get_sensitive() for w in view._manual_led_widgets))

    def test_native_set_covers_sdk_games(self):
        self.assertEqual(NATIVE_DRIVER_IDS, {"acc", "assetto_corsa_evo", "rfactor2", "lmu"})


if __name__ == "__main__":
    unittest.main()
