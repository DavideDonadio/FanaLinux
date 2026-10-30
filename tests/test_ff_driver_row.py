"""Driver row label contract: Active carries the version, states stay distinct."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from gi.repository import Adw

from fanalinux.core import driver_setup
from fanalinux.ui.views.overview import OverviewView


class TestDriverRowLabel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Adw.init()

    def _view(self):
        device = MagicMock()
        device.product_id = 0x0020
        return OverviewView(device)

    def test_active_shows_version_when_known(self):
        view = self._view()
        view.set_ff_driver(["Constant"], has_wheel=True, module_present=True)
        text = view.ff_lbl.get_text()
        ver = driver_setup.installed_version()
        base = ver.split("-")[0] if ver else ""
        if base:
            self.assertEqual(text, f"Active (v{base})")
        else:
            self.assertEqual(text, "Active")

    def test_states_stay_distinct(self):
        view = self._view()
        view.set_ff_driver([], has_wheel=True, module_present=True)
        self.assertIn("Missing", view.ff_lbl.get_text())
        view.set_ff_driver([], has_wheel=False, module_present=False)
        self.assertIn("Not detected", view.ff_lbl.get_text())


if __name__ == "__main__":
    unittest.main()
