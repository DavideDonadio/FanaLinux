"""Stream loss must clear stuck motor outputs (haptics + dynamic damper)."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fanalinux.core.telemetry.manager import TelemetryManager


def _manager():
    mgr = TelemetryManager.__new__(TelemetryManager)
    mgr.enabled = True
    mgr.device = MagicMock()
    mgr.active_client = MagicMock()
    mgr.haptic_engine = MagicMock()
    mgr.dynamic_ffb_engine = MagicMock()
    mgr._stream_was_alive = False
    return mgr


class TestStreamLossClearsOutputs(unittest.TestCase):
    def test_connected_then_lost_zeroes_once(self):
        mgr = _manager()
        mgr.active_client.is_connected = True
        mgr.check_stream_health()
        mgr.haptic_engine.zero_outputs.assert_not_called()
        mgr.active_client.is_connected = False
        mgr.check_stream_health()
        mgr.haptic_engine.zero_outputs.assert_called_once()
        mgr.dynamic_ffb_engine.reset.assert_called_once()
        # Further polls while dead stay silent (no USB chatter).
        mgr.check_stream_health()
        mgr.haptic_engine.zero_outputs.assert_called_once()

    def test_disabled_session_never_zeroes(self):
        mgr = _manager()
        mgr.enabled = False
        mgr.active_client.is_connected = False
        mgr.check_stream_health()
        mgr.haptic_engine.zero_outputs.assert_not_called()


if __name__ == "__main__":
    unittest.main()
