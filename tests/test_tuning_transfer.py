"""Regression tests for tuning -> hardware register encoding.

Hardware-free: captures report buffers instead of writing to hidraw.
Locks in the SEN mapping found via interactive wheel validation:
hardware true SEN = (raw byte + 127) * 10, AUT code = 129.
"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fanalinux.core.device import FanatecDevice
from fanalinux.core.tuning import TuningProfile
from fanalinux.core.protocol import TUNING_REGISTERS


def capture_full_buffer(dev, profile):
    """Run apply_tuning_profile with a stubbed transport, return the 64-byte tuning buffer."""
    bufs = []
    dev.write_report = lambda data: bufs.append(list(data)) or len(data)
    dev.apply_tuning_profile(profile)
    full = [b for b in bufs if len(b) == 64 and b[:3] == [0xFF, 0x03, 0x00]]
    assert len(full) == 1, f"expected one full tuning buffer, got {len(bufs)}"
    return full[0]


def reg(buf, name):
    return buf[TUNING_REGISTERS[name] + 1]


class TestTuningTransfer(unittest.TestCase):
    def setUp(self):
        self.dev = FanatecDevice()

    def sen_byte(self, sen):
        return reg(capture_full_buffer(self.dev, TuningProfile(slot=1, sen=sen)), "SEN")

    def test_sen_encoding(self):
        # raw = deg // 10 - 127 (mod 256); verified against wheel OLED + lock-to-lock turns
        self.assertEqual(self.sen_byte(900), 219)
        self.assertEqual(self.sen_byte(540), 183)
        self.assertEqual(self.sen_byte(360), 165)
        self.assertEqual(self.sen_byte(2520), 125)
        self.assertEqual(self.sen_byte(90), 138)

    def test_sen_auto_code(self):
        self.assertEqual(self.sen_byte(0), 129)

    def test_passthrough_registers(self):
        buf = capture_full_buffer(self.dev, TuningProfile(slot=1, ff=50, ndp=70, bli=50, fei=50))
        self.assertEqual(reg(buf, "FF"), 50)
        self.assertEqual(reg(buf, "NDP"), 70)
        self.assertEqual(reg(buf, "BLI"), 50)
        self.assertEqual(reg(buf, "FEI"), 50)

    def test_scaled_registers(self):
        buf = capture_full_buffer(self.dev, TuningProfile(slot=1, for_mult=60, spr_mult=70, dpr_mult=80, sho=100))
        self.assertEqual(reg(buf, "FOR"), 6)
        self.assertEqual(reg(buf, "SPR"), 7)
        self.assertEqual(reg(buf, "DPR"), 8)
        self.assertEqual(reg(buf, "SHO"), 10)

    def test_slot_byte(self):
        buf = capture_full_buffer(self.dev, TuningProfile(slot=1))
        self.assertEqual(reg(buf, "SLOT"), 1)


if __name__ == "__main__":
    unittest.main()
