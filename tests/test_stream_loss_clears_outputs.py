"""Stream loss must clear stuck motor outputs (haptics + dynamic damper).

Health is measured by dispatched telemetry frames, not UDP datagrams:
a stream of short/wrong-type packets that parsers drop must still count
as lost.
"""

import sys
import time
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
    mgr.haptic_engine = MagicMock()
    mgr.dynamic_ffb_engine = MagicMock()
    mgr._stream_was_alive = False
    mgr._last_frame_at = 0.0
    return mgr


class TestStreamLossClearsOutputs(unittest.TestCase):
    def test_frames_then_silence_zeroes_once(self):
        mgr = _manager()
        mgr._last_frame_at = time.monotonic()
        mgr.check_stream_health()  # alive
        self.assertTrue(mgr._stream_was_alive)
        mgr._last_frame_at = time.monotonic() - 10.0  # stream died silently
        mgr.check_stream_health()
        mgr.haptic_engine.zero_outputs.assert_called_once()
        mgr.dynamic_ffb_engine.reset.assert_called_once()
        # Further polls while dead stay silent (no USB chatter).
        mgr.check_stream_health()
        mgr.haptic_engine.zero_outputs.assert_called_once()

    def test_junk_datagrams_do_not_count_as_alive(self):
        """End to end: AMS2 parser wired to a live manager. Junk packets
        leave the manager's frame clock untouched, so the fail-safe fires."""
        from fanalinux.core.telemetry.ams2 import AMS2Telemetry
        from fanalinux.core.telemetry.manager import TelemetryManager
        mgr = TelemetryManager.__new__(TelemetryManager)
        mgr.enabled = True
        mgr.device = MagicMock()
        mgr.device.connected = True
        mgr.device.active_sen = 450
        mgr.haptic_engine = MagicMock()
        mgr.dynamic_ffb_engine = MagicMock()
        mgr.auto_detect_rpm = False
        mgr.display_mode = "gear"
        mgr._last_gear = None
        mgr._last_flag_state = None
        mgr._limiter_strobe = False
        mgr._last_speed_txt = None
        mgr.peak_rpm_seen = 0
        mgr.max_rpm = 6500
        mgr._stream_was_alive = False
        mgr._last_frame_at = 0.0
        client = AMS2Telemetry(on_telemetry=mgr._handle_telemetry)
        # Junk: short + wrong-type. Neither may advance the frame clock.
        self.assertFalse(bool(client.process_packet(bytes(20))))
        wrong_type = bytearray(600)
        wrong_type[10] = 2  # not eCarPhysics
        self.assertFalse(bool(client.process_packet(bytes(wrong_type))))
        self.assertEqual(mgr._last_frame_at, 0.0)
        mgr._stream_was_alive = True  # pretend a stream was live
        mgr.check_stream_health()
        mgr.haptic_engine.zero_outputs.assert_called_once()
        # A valid physics frame revives the clock and clears the flag.
        mgr.haptic_engine.reset_mock()
        mgr.dynamic_ffb_engine.reset_mock()
        physics = bytearray(556)  # type 0 + long enough
        self.assertTrue(bool(client.process_packet(bytes(physics))))
        self.assertGreater(mgr._last_frame_at, 0.0)
        mgr.check_stream_health()
        mgr.haptic_engine.zero_outputs.assert_not_called()

    def test_disabled_session_never_zeroes(self):
        mgr = _manager()
        mgr.enabled = False
        mgr.check_stream_health()
        mgr.haptic_engine.zero_outputs.assert_not_called()


if __name__ == "__main__":
    unittest.main()
