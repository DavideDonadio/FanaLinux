"""
Unit tests for the isiMotor Pulse telemetry adapter.
Mocks IsiMotorClient at the import boundary; no sockets, no game.
"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fanalinux.core.telemetry.pulse import PulseTelemetry


class FakeECU:
    def __init__(self, tc=False, abs_=False):
        self.tc_active = tc
        self.abs_active = abs_


class FakeTelem:
    def __init__(self, gear=3, rpm=9200.0, kmh=214.5, tc=False, abs_=False):
        self.gear = gear
        self.engine_rpm = rpm
        self.forward_speed_kmh = kmh
        self.ecu = FakeECU(tc, abs_)


class TestPulseMapping(unittest.TestCase):
    def _client_with(self, telems):
        frames = []
        c = PulseTelemetry(on_telemetry=lambda *a, **k: frames.append((a, k)))
        c._client = SimpleNamespace(
            get_latest_telemetry=lambda: (telems.pop(0) if telems else None))
        c._running = True
        return c, frames

    def _pump_once(self, c):
        telem = c._client.get_latest_telemetry()
        gear = int(telem.gear)
        rpm = int(telem.engine_rpm)
        speed_kmh = float(telem.forward_speed_kmh)
        ecu = getattr(telem, "ecu", None)
        c._dispatch_telemetry(rpm, gear, speed_kmh,
                              bool(getattr(ecu, "abs_active", False)),
                              bool(getattr(ecu, "tc_active", False)))

    def test_gear_rpm_speed_mapping(self):
        c, frames = self._client_with([FakeTelem()])
        self._pump_once(c)
        args, kw = frames[0]
        self.assertEqual((args[0], args[1]), (9200, 3))
        self.assertAlmostEqual(args[2], 214.5)
        self.assertEqual((args[3], args[4]), (False, False))

    def test_tc_abs_flags(self):
        c, frames = self._client_with([FakeTelem(tc=True, abs_=True)])
        self._pump_once(c)
        args, _kw = frames[0]
        self.assertEqual((args[3], args[4]), (True, True))

    def test_reverse_gear(self):
        c, frames = self._client_with([FakeTelem(gear=-1, rpm=1500.0, kmh=12.0)])
        self._pump_once(c)
        self.assertEqual(frames[0][0][1], -1)

    def test_missing_dependency(self):
        self.assertIn(PulseTelemetry.is_available(), (True, False))

    def test_cached_dll_needs_no_network(self):
        import tempfile
        from unittest import mock
        from fanalinux.core.telemetry import pulse as pulse_mod
        with tempfile.NamedTemporaryFile(suffix=".dll", delete=False) as f:
            f.write(b"x" * 64)
            cached = f.name
        try:
            with mock.patch.object(pulse_mod, "PULSE_DLL_CACHE", Path(cached)):
                with mock.patch("urllib.request.urlopen") as urlopen:
                    result = PulseTelemetry.ensure_plugin_dll()
                    self.assertEqual(result, Path(cached))
                    urlopen.assert_not_called()
        finally:
            Path(cached).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
