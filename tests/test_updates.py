"""Unit tests for version comparison (offline, no network)."""
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fanalinux.core.updates import is_newer, get_local_version


class TestUpdates(unittest.TestCase):
    def test_is_newer(self):
        self.assertTrue(is_newer("0.5.6", "v0.5.7"))
        self.assertTrue(is_newer("0.6.0", "0.6.1"))
        self.assertFalse(is_newer("0.6.0", "v0.6.0"))
        self.assertFalse(is_newer("0.6.1", "0.6.0"))
        self.assertFalse(is_newer("0.6.0", "0.6"))

    def test_local_version_resolves(self):
        self.assertTrue(get_local_version())


if __name__ == "__main__":
    unittest.main()
