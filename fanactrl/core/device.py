"""
Fanatec Hardware Device Abstraction.

Wraps low-level HID communication, initialization handshakes,
telemetry dispatches, and tuning parameter synchronization.
"""

import time
import logging
from typing import Optional, List, Tuple
import hid

from fanactrl.core.protocol import (
    FANATEC_VENDOR_ID,
    PID_CSL_DD,
    CMD_INIT,
    CMD_DISPLAY_PREFIX,
    CMD_LEGACY_LED_PREFIX,
    REPORT_ID_DIRECT_DRIVE,
    REPORT_ID_LEGACY_CMD,
    CMD_LED_MC,
    LED_SUB_RPM,
    LED_SUB_FLAGS,
    encode_bgr565,
    text_to_segment_bytes,
    TUNING_REGISTERS,
    RIM_TYPES,
)
from fanactrl.core.tuning import TuningProfile

logger = logging.getLogger("fanactrl.device")


class FanatecDevice:
    def __init__(self, vendor_id: int = FANATEC_VENDOR_ID, product_id: int = PID_CSL_DD):
        self.vendor_id = vendor_id
        self.product_id = product_id
        self._dev: Optional[hid.device] = None
        self.connected = False
        self.product_name = "Fanatec Wheelbase"
        self.rim_name = "Formula V2.5"

    def connect(self) -> bool:
        """Find and open the Fanatec device."""
        try:
            devices = hid.enumerate(self.vendor_id, self.product_id)
            if not devices:
                logger.warning(f"No Fanatec device found matching VID: 0x{self.vendor_id:04x}, PID: 0x{self.product_id:04x}")
                self.connected = False
                return False

            dev_info = devices[0]
            self.product_name = dev_info.get("product_string", "Fanatec Wheel")
            
            self._dev = hid.device()
            self._dev.open(self.vendor_id, self.product_id)
            self._dev.set_nonblocking(True)
            self.connected = True
            logger.info(f"Connected to {self.product_name} (VID: 0x{self.vendor_id:04x}, PID: 0x{self.product_id:04x})")

            # Run initialization sequence
            self.initialize_hardware()
            return True
        except Exception as e:
            logger.error(f"Failed to connect to device: {e}")
            self.connected = False
            self._dev = None
            return False

    def disconnect(self):
        """Close connection to device."""
        if self._dev:
            try:
                self.clear_display()
                self.set_revleds([(0, 0, 0)] * 9)
                self.set_flagleds([(0, 0, 0)] * 6)
                self._dev.close()
            except Exception:
                pass
            self._dev = None
        self.connected = False

    def initialize_hardware(self):
        """Send standard initialization handshake."""
        if not self._dev:
            return
        payload = [REPORT_ID_LEGACY_CMD] + CMD_INIT
        self._dev.write(payload)
        time.sleep(0.02)

    def set_revleds(self, colors: List[Tuple[int, int, int]]):
        """
        Set the 9 multi-color RevLEDs on the rim.
        colors: list of 9 (r, g, b) tuples, each component 0..255.
        """
        if not self._dev or not self.connected:
            return
        buf = [REPORT_ID_DIRECT_DRIVE, CMD_LED_MC, LED_SUB_RPM]
        for r, g, b in colors[:9]:
            val = encode_bgr565(r, g, b)
            buf.append((val >> 8) & 0xFF)
            buf.append(val & 0xFF)
        # Pad to 64 bytes
        buf.extend([0x00] * (64 - len(buf)))
        self._dev.write(buf)

    def set_flagleds(self, colors: List[Tuple[int, int, int]]):
        """
        Set the 6 multi-color Flag LEDs on the rim (3 left, 3 right).
        colors: list of 6 (r, g, b) tuples.
        """
        if not self._dev or not self.connected:
            return
        buf = [REPORT_ID_DIRECT_DRIVE, CMD_LED_MC, LED_SUB_FLAGS]
        for r, g, b in colors[:6]:
            val = encode_bgr565(r, g, b)
            buf.append((val >> 8) & 0xFF)
            buf.append(val & 0xFF)
        buf.extend([0x00] * (64 - len(buf)))
        self._dev.write(buf)

    def set_display_text(self, text: str):
        """Send up to 3 characters to the rim's 7-segment / OLED display."""
        if not self._dev or not self.connected:
            return
        s1, s2, s3 = text_to_segment_bytes(text)
        payload = [REPORT_ID_LEGACY_CMD] + CMD_DISPLAY_PREFIX + [s1, s2, s3]
        self._dev.write(payload)

    def clear_display(self):
        """Clear the rim display back to blank."""
        if not self._dev or not self.connected:
            return
        payload = [REPORT_ID_LEGACY_CMD] + CMD_DISPLAY_PREFIX + [0x00, 0x00, 0x00]
        self._dev.write(payload)

    def apply_tuning_profile(self, profile: TuningProfile):
        """Write all tuning attributes from the profile into the hardware registers."""
        if not self._dev or not self.connected:
            return

        # Write slot selection first
        buf = [REPORT_ID_DIRECT_DRIVE, 0x03, 0x01, profile.slot & 0xFF] + [0x00] * 60
        self._dev.write(buf)
        time.sleep(0.01)

        # Mapping profile fields to tuning registers
        reg_values = {
            "SEN": profile.sen // 10 if profile.sen <= 1080 else (0xED + ((profile.sen - 1080) // 10)),
            "FF": profile.ff,
            "FFS": profile.ffs,
            "NDP": profile.ndp,
            "NFR": profile.nfr,
            "NIN": profile.nin,
            "INT": profile.int_filter,
            "FEI": profile.fei,
            "FOR": profile.for_mult // 10,
            "SPR": profile.spr_mult // 10,
            "DPR": profile.dpr_mult // 10,
            "SHO": profile.sho // 10,
            "BRF": profile.brf,
        }

        for reg_name, raw_val in reg_values.items():
            if reg_name in TUNING_REGISTERS:
                addr = TUNING_REGISTERS[reg_name]
                out_buf = [REPORT_ID_DIRECT_DRIVE, 0x03, 0x00] + [0x00] * 61
                out_buf[addr + 1] = int(raw_val) & 0xFF
                self._dev.write(out_buf)
                time.sleep(0.005)

    def calibrate_center(self):
        """Trigger center calibration sequence in hardware."""
        if not self._dev or not self.connected:
            return
        # Center calibration trigger payload: [0x01, 0xF8, 0x09, 0x01, 0x06, 0x01, 0x00, 0x00]
        payload = [REPORT_ID_LEGACY_CMD, 0xF8, 0x09, 0x01, 0x06, 0x01, 0x00, 0x00]
        self._dev.write(payload)
