"""Unit tests for the RevLED preview zone mapping (offline, no hardware)."""
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fanalinux.ui.views.leds import led_zone_class


class TestLedZones(unittest.TestCase):
    def test_zone_boundaries(self):
        for i in (0, 1, 2):
            self.assertEqual(led_zone_class(i), "led-zone-green")
        for i in (3, 4, 5):
            self.assertEqual(led_zone_class(i), "led-zone-yellow")
        for i in (6, 7):
            self.assertEqual(led_zone_class(i), "led-zone-red")
        for i in (8, 9, 10, 15):
            self.assertEqual(led_zone_class(i), "led-zone-blue")


if __name__ == "__main__":
    unittest.main()
