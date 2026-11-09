"""Manual LED controls must yield while a game profile owns the wheel."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from gi.repository import Adw

from fanalinux.ui.views.leds import LedsView


class TestNativeGameLedYield(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Adw.init()

    def test_manual_controls_toggle(self):
        view = LedsView(MagicMock(), telemetry_mgr=MagicMock())
        self.assertTrue(len(view._manual_led_widgets) >= 8)
        view.set_game_active(True)
        self.assertTrue(all(not w.get_sensitive() for w in view._manual_led_widgets))
        view.set_game_active(False)
        self.assertTrue(all(w.get_sensitive() for w in view._manual_led_widgets))


if __name__ == "__main__":
    unittest.main()
