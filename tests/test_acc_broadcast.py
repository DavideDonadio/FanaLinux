"""
Unit tests for the ACC broadcast telemetry client.
Crafts handshake + realtime packets per the Kunos SDK protocol
(BroadcastingNetworkProtocol.cs) and asserts gear/speed dispatch.
"""

import struct
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fanalinux.core.telemetry.acc_broadcast import ACCBroadcastTelemetry, _pack_string


def reg_result(conn_id=7, success=1):
    return struct.pack("<BiB", 1, conn_id, success) + _pack_string("")


def realtime_update(focused=0):
    # type 2; focused car index at offset 15
    return (struct.pack("<BHHBBff", 2, 1, 1, 0, 0, 1.0, 2.0)
            + struct.pack("<i", focused))


def car_update(car=0, gear_raw=5, kmh=184):
    # type 3; gear at 5 (raw-2), kmh at 19
    return (struct.pack("<BHHB", 3, car, 0, gear_raw)
            + struct.pack("<fff", 0.0, 0.0, 0.0)
            + struct.pack("<BHHHHfHI", 1, kmh, 3, 1, 1, 0.5, 12, 0))


class TestACCBroadcast(unittest.TestCase):
    def test_pack_string_roundtrip(self):
        self.assertEqual(_pack_string("ab"), b"\x02\x00ab")
        self.assertEqual(_pack_string(""), b"\x00\x00")

    def test_registration_and_focused_car(self):
        frames = []
        c = ACCBroadcastTelemetry(on_telemetry=lambda *a, **k: frames.append((a, k)))
        # Registration path sends entry/track requests; sink them.
        sent = []
        c._sock = type("S", (), {"sendto": lambda self, p, t: sent.append(p)})()
        c._handle_message(reg_result())
        self.assertEqual(c._connection_id, 7)
        self.assertTrue(c.is_connected)
        c._handle_message(realtime_update(focused=0))
        c._handle_message(car_update(car=0, gear_raw=5, kmh=184))
        self.assertEqual(len(frames), 1)
        args, _kw = frames[0]
        rpm, gear, speed = args[0], args[1], args[2]
        self.assertEqual(rpm, 0)  # No RPM on this feed by protocol design.
        self.assertEqual(gear, 3)
        self.assertEqual(speed, 184.0)

    def test_other_cars_ignored_once_focused(self):
        frames = []
        c = ACCBroadcastTelemetry(on_telemetry=lambda *a, **k: frames.append(a))
        c._sock = type("S", (), {"sendto": lambda self, p, t: None})()
        c._handle_message(reg_result())
        c._handle_message(realtime_update(focused=2))
        c._handle_message(car_update(car=5, gear_raw=4, kmh=100))
        self.assertEqual(frames, [])

    def test_rejected_registration(self):
        c = ACCBroadcastTelemetry()
        c._sock = type("S", (), {"sendto": lambda self, p, t: None})()
        c._handle_message(reg_result(success=0))
        self.assertIsNone(c._connection_id)
        self.assertFalse(c.is_connected)

    def test_gear_range_guard(self):
        frames = []
        c = ACCBroadcastTelemetry(on_telemetry=lambda *a, **k: frames.append(a))
        c._sock = type("S", (), {"sendto": lambda self, p, t: None})()
        c._handle_message(reg_result())
        c._handle_message(car_update(car=0, gear_raw=50, kmh=100))
        self.assertEqual(frames, [])

    def test_reverse_and_neutral(self):
        gears = []
        c = ACCBroadcastTelemetry(on_telemetry=lambda *a, **k: gears.append(k.get("gear", a[1])))
        c._sock = type("S", (), {"sendto": lambda self, p, t: None})()
        c._handle_message(reg_result())
        c._handle_message(car_update(car=0, gear_raw=1, kmh=0))
        c._latched_car = None
        c._focused_car = None
        c._handle_message(car_update(car=0, gear_raw=2, kmh=0))
        self.assertEqual(gears, [-1, 0])


if __name__ == "__main__":
    unittest.main()
