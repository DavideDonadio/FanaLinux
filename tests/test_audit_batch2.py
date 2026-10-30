"""Regression tests for the external audit batch 2 (state-sync fixes)."""

import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from gi.repository import Adw

from fanalinux.core.telemetry.forza import ForzaTelemetry
from fanalinux.core.telemetry.scs import SCSTelemetry


def _scs_frame(sim_time=12345, rpm=900.0, speed_ms=0.0, throttle=0.0):
    mm = bytearray(968)
    struct.pack_into("<?", mm, 4, False)
    struct.pack_into("<Q", mm, 8, sim_time)
    struct.pack_into("<i", mm, 504, 0)
    struct.pack_into("<f", mm, 740, 2500.0)
    struct.pack_into("<5f", mm, 948, speed_ms, rpm, 0.0, throttle, 0.0)
    return bytes(mm)


class TestAuditBatch2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Adw.init()

    def test_stale_stop_preserves_active_game(self):
        """Delayed A-stop after A->B must not clobber B's profile or identity."""
        from fanalinux.ui.window import MainWindow
        win = MainWindow()
        try:
            win._last_game_id = "b"
            win._apply_game_stopped({"id": "a", "name": "A"}, "Default")
            self.assertEqual(win._last_game_id, "b")
            # Legit stop still clears.
            win._apply_game_stopped({"id": "b", "name": "B"}, "Default")
            self.assertIsNone(win._last_game_id)
        finally:
            try:
                win.destroy()
            except Exception:
                pass

    def test_reconcile_deleted_preset(self):
        from fanalinux.core.detector import GameDetector
        det = GameDetector.__new__(GameDetector)
        det.game_mappings = {"ac": {"preset": "Gone", "enabled": True}}
        det.custom_games = []
        det.fallback_preset = "Gone"
        saved = []
        det.save_config = lambda: saved.append(True)
        det.reconcile_deleted_preset("Gone")
        self.assertEqual(det.game_mappings["ac"]["preset"], "Default")
        self.assertEqual(det.fallback_preset, "Default")
        self.assertTrue(saved)

    def test_scs_frozen_idle_buffer_times_out(self):
        """Idling rpm in a frozen buffer must not count as a heartbeat."""
        c = SCSTelemetry(on_telemetry=lambda *a, **k: None)
        c.is_connected = True
        c._last_sim_time = 12345
        import time
        c._last_time_change = time.time() - 10.0
        c.process_frame(_scs_frame(sim_time=12345, rpm=900.0))
        self.assertFalse(c.is_connected)

    def test_forza_fwd_spin_triggers_tc_not_abs(self):
        """FWD wheelspin (front slip, throttle) -> TC; spin under braking -> no ABS."""
        seen = []
        client = ForzaTelemetry(on_telemetry=lambda *a, **k: seen.append((a, k)))
        base = bytearray(324)
        struct.pack_into("<iI3f", base, 0, 1, 1000, 8200.0, 800.0, 7200.0)
        struct.pack_into("<4f", base, 68, 0.05, 0.05, 0.06, 0.06)
        struct.pack_into("<4f", base, 100, 150.0, 150.0, 150.0, 150.0)
        struct.pack_into("<f", base, 256, 30.0)
        # Case 1: throttle + front spin, no brake -> TC, no ABS.
        pkt = bytearray(base)
        struct.pack_into("<4f", pkt, 84, 0.6, 0.6, 0.0, 0.0)
        struct.pack_into("<BbBB", pkt, 312, 4, 0, 200, 0)
        client.process_packet(bytes(pkt))
        # Case 2: braking + positive spin only -> neither ABS nor TC.
        pkt2 = bytearray(base)
        struct.pack_into("<4f", pkt2, 84, 0.6, 0.6, 0.0, 0.0)
        struct.pack_into("<BbBB", pkt2, 312, 4, 0, 0, 200)
        client.process_packet(bytes(pkt2))
        self.assertEqual(len(seen), 2)
        self.assertTrue(seen[0][0][4])
        self.assertFalse(seen[0][0][3])
        self.assertFalse(seen[1][0][3])
        self.assertFalse(seen[1][0][4])

    def test_dynamic_cache_rearms_after_inhibit(self):
        """Inhibited writes must not poison the cache; re-arm re-applies."""
        from fanalinux.core.dynamic_ffb_engine import DynamicFFBEngine
        dev = MagicMock()
        dev.connected = True
        dev.output_inhibited = True
        eng = DynamicFFBEngine(dev, settings=MagicMock(
            reverse_damper_enabled=False, speed_sensitive_enabled=True,
            speed_threshold_min=50, speed_threshold_max=100,
            damper_effect_strength=75, damper_effect_range=90))
        eng.update_telemetry(150.0, 3, 0.0, (0, 0, 0, 0), active_sen=900)
        self.assertEqual(eng._last_applied_damping, -1)
        dev.output_inhibited = False
        eng.update_telemetry(150.0, 3, 0.0, (0, 0, 0, 0), active_sen=900)
        dev.send_damper_friction.assert_called_with(75)

    def test_haptic_weak_event_keeps_strong_pulse(self):
        from fanalinux.core.haptics import HapticEngine
        eng = HapticEngine.__new__(HapticEngine)
        import threading as _t
        eng._lock = _t.Lock()
        eng._pulse_active = False
        eng._pulse_end_time = 0.0
        eng._pulse_intensity = 0
        eng.trigger_pulse(90, 5.0)
        eng.trigger_pulse(30, 5.0)
        self.assertEqual(eng._pulse_intensity, 90)

    def test_trigger_happy_range_matches_kernel(self):
        """Button mapping must agree with the kernel header, not comments.
        BTN_TRIGGER_HAPPY1..40 = codes 704..743 -> buttons 17..56."""
        from evdev import ecodes
        from fanalinux.core.evdev_listener import EvdevListener, EV_KEY
        got = []
        listener = EvdevListener(on_button=lambda b, p: got.append((b, p)))
        self.assertEqual(ecodes.BTN_TRIGGER_HAPPY40 - ecodes.BTN_TRIGGER_HAPPY1, 39)
        listener._process_event(EV_KEY, 704, 1)
        listener._process_event(EV_KEY, 743, 1)
        listener._process_event(EV_KEY, 744, 1)  # beyond the real range
        by_code = {b: p for b, p in got}
        self.assertEqual(by_code[17], True)
        self.assertEqual(by_code[56], True)
        self.assertEqual(by_code[744], True)  # passes through raw, never mapped

    def test_disconnect_serialized_with_writes(self):
        """Concurrent writes during disconnect must not raise or double-close."""
        from fanalinux.core.device import FanatecDevice
        import os as _os
        dev = FanatecDevice.__new__(FanatecDevice)
        import threading as _t
        dev._lock = _t.RLock()
        dev.connected = True
        dev._fd = 999999
        errors = []
        real_close = _os.close
        closes = []
        _os.close = lambda fd: closes.append(fd)
        try:
            def writer():
                try:
                    for _ in range(200):
                        dev.write_report([0xFF] * 8)
                except Exception as e:  # noqa: BLE001
                    errors.append(e)
            ts = [_t.Thread(target=writer) for _ in range(4)]
            for t in ts:
                t.start()
            dev.disconnect()
            for t in ts:
                t.join()
        finally:
            _os.close = real_close
        self.assertEqual(errors, [])
        self.assertLessEqual(len(closes), 1)


if __name__ == "__main__":
    unittest.main()
