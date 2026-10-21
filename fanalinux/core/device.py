"""
Fanatec Hardware Device Abstraction.

Native Linux hidraw implementation that does not detach the kernel driver.
Maintains concurrent compatibility with evdev gaming inputs.
"""

import os
import glob
import time
import select
import logging
import threading
import errno
from typing import Optional, List, Tuple, Dict, Any

from fanalinux.core.protocol import (
    FANATEC_VENDOR_ID,
    PID_CSL_DD,
    PID_DD_PRO,
    PID_PODIUM_DD1,
    PID_PODIUM_DD2,
    PID_CLUBSPORT_V25,
    PID_CSL_ELITE,
    PID_CSL_ELITE_PS4,
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
from fanalinux.core.tuning import TuningProfile

logger = logging.getLogger("fanalinux.device")


class FanatecDevice:
    def __init__(self, vendor_id: int = FANATEC_VENDOR_ID, product_id: int = PID_CSL_DD):
        self.vendor_id = vendor_id
        self.product_id = product_id
        self._fd: Optional[int] = None
        self.hidraw_path: Optional[str] = None
        self.connected = False
        self.product_name = "Fanatec CSL DD"
        self.rim_name = "ClubSport Steering Wheel Formula V2.5"
        self.firmware_base = "1.1.8.4"
        self.firmware_motor = "1.0.3.2"
        self.firmware_rim = "45"
        self._abort_vibration = False
        self._vibration_token = 0
        self.active_sen = 900
        self._lock = threading.RLock()

    def find_hidraw_path(self) -> Optional[str]:
        """
        Locate the Fanatec hidraw device node with intelligent preference for
        wheelbases over peripheral accessories (e.g. standalone USB pedals/shifters).
        """
        by_id_matches = glob.glob("/dev/input/by-id/*Fanatec*-hidraw*")
        if by_id_matches:
            # Prioritize wheelbases over pedals / shifters
            non_pedal = [m for m in by_id_matches if not any(x in m.lower() for x in ("pedal", "shifter", "handbrake"))]
            if non_pedal:
                return os.path.realpath(non_pedal[0])
            return os.path.realpath(by_id_matches[0])

        known_pids = (
            f"{PID_CSL_DD:04X}",
            f"{PID_DD_PRO:04X}",
            f"{PID_PODIUM_DD1:04X}",
            f"{PID_PODIUM_DD2:04X}",
            f"{PID_CLUBSPORT_V2:04X}",
            f"{PID_CLUBSPORT_V25:04X}",
            f"{PID_CSL_ELITE:04X}",
            f"{PID_CSL_ELITE_PS4:04X}",
        )

        candidates = []
        for entry in glob.glob("/sys/class/hidraw/hidraw*"):
            uevent_path = os.path.join(entry, "device", "uevent")
            if os.path.exists(uevent_path):
                try:
                    with open(uevent_path, "r") as f:
                        content = f.read().upper()
                        if f"{self.vendor_id:04X}" in content:
                            dev_name = os.path.basename(entry)
                            dev_path = f"/dev/{dev_name}"
                            score = 1
                            if not any(x in content for x in ("PEDAL", "SHIFTER", "HANDBRAKE")):
                                score = 2
                            if any(pid in content for pid in known_pids):
                                score = 3
                            candidates.append((score, dev_path))
                except Exception:
                    pass

        if candidates:
            # Return the highest scored wheelbase node
            candidates.sort(key=lambda c: c[0], reverse=True)
            return candidates[0][1]

        return None

    def connect(self) -> bool:
        """Find and open the native Fanatec hidraw node."""
        path = self.find_hidraw_path()
        if not path or not os.path.exists(path):
            logger.warning("No Fanatec hidraw node found.")
            self.connected = False
            return False

        try:
            self._fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
            self.hidraw_path = path
            self.connected = True
            logger.info(f"Connected to Fanatec on {path}")

            # Send initialization handshake
            self.initialize_hardware()
            return True
        except Exception as e:
            logger.error(f"Failed to open hidraw node {path}: {e}")
            self.connected = False
            self._fd = None
            return False

    def disconnect(self):
        """
        Close connection to device node.
        Note: Callers should ensure telemetry is stopped and best-effort display/LED
        blanking is performed prior to calling disconnect().
        """
        self.connected = False
        fd = self._fd
        self._fd = None
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass

    def check_connection(self) -> bool:
        """
        Verify device node presence and active connection.
        Returns True if connected and healthy, False otherwise.
        Automatically reconnects if the hardware is plugged back in.
        """
        if not self.connected or self._fd is None:
            path = self.find_hidraw_path()
            if path and os.path.exists(path):
                return self.connect()
            return False

        if not self.hidraw_path or not os.path.exists(self.hidraw_path):
            self.disconnect()
            return False

        try:
            _, _, x = select.select([self._fd], [], [self._fd], 0)
            if x:
                self.disconnect()
                return False
        except (OSError, ValueError):
            self.disconnect()
            return False

        return True

    def write_report(self, data: List[int]) -> int:
        """Write raw HID report buffer directly to hidraw with thread safety and non-blocking retry."""
        if self._fd is None or not self.connected:
            return 0
        should_disconnect = False
        bytes_written = 0
        with self._lock:
            if self._fd is None or not self.connected:
                return 0
            payload = bytes(data)
            for attempt in range(2):
                try:
                    bytes_written = os.write(self._fd, payload)
                    break
                except BlockingIOError:
                    time.sleep(0.002)
                    continue
                except (OSError, ValueError) as e:
                    err_code = getattr(e, 'errno', None)
                    if err_code in (errno.EAGAIN, errno.EWOULDBLOCK):
                        time.sleep(0.002)
                        continue
                    # Fatal hardware disconnection error (ENODEV, EIO, EBADF)
                    logger.warning(f"Fatal device error during write (disconnecting): {e}")
                    should_disconnect = True
                    break
                except Exception as e:
                    logger.error(f"Error writing report to hidraw: {e}")
                    break

        if should_disconnect:
            self.disconnect()

        return bytes_written

    def initialize_hardware(self):
        """Send standard initialization handshake."""
        payload = [REPORT_ID_LEGACY_CMD] + CMD_INIT
        self.write_report(payload)
        time.sleep(0.02)

    def set_revleds(self, colors: List[Tuple[int, int, int]]):
        """
        Set the 9 multi-color RevLEDs on the rim.
        colors: list of 9 (r, g, b) tuples, each component 0..255.
        """
        buf = [REPORT_ID_DIRECT_DRIVE, CMD_LED_MC, LED_SUB_RPM]
        for r, g, b in colors[:9]:
            val = encode_bgr565(r, g, b)
            buf.append((val >> 8) & 0xFF)
            buf.append(val & 0xFF)
        buf.extend([0x00] * (64 - len(buf)))
        self.write_report(buf)

    def set_flagleds(self, colors: List[Tuple[int, int, int]]):
        """
        Set the 6 multi-color Flag LEDs on the rim (3 left, 3 right).
        colors: list of 6 (r, g, b) tuples.
        """
        buf = [REPORT_ID_DIRECT_DRIVE, CMD_LED_MC, LED_SUB_FLAGS]
        for r, g, b in colors[:6]:
            val = encode_bgr565(r, g, b)
            buf.append((val >> 8) & 0xFF)
            buf.append(val & 0xFF)
        buf.extend([0x00] * (64 - len(buf)))
        self.write_report(buf)

    def set_display_text(self, text: str):
        """Send up to 3 characters to the rim's 7-segment / OLED display."""
        s1, s2, s3 = text_to_segment_bytes(text)
        payload = [REPORT_ID_LEGACY_CMD] + CMD_DISPLAY_PREFIX + [s1, s2, s3]
        self.write_report(payload)

    def clear_display(self):
        """Clear the rim display back to blank."""
        payload = [REPORT_ID_LEGACY_CMD] + CMD_DISPLAY_PREFIX + [0x00, 0x00, 0x00]
        self.write_report(payload)

    def apply_tuning_profile(self, profile: TuningProfile):
        """Write all tuning attributes from the profile into the hardware registers."""
        try:
            sen_val = int(getattr(profile, "sen", 900))
        except (ValueError, TypeError):
            sen_val = 900

        # Encode SEN safely: 0 = Auto, 90..2520 deg mapped to 9..252
        if sen_val <= 0 or sen_val < 45:
            raw_sen = 0
            self.active_sen = 900
        elif sen_val < 90:
            raw_sen = 9
            self.active_sen = 90
        else:
            raw_sen = max(9, min(252, sen_val // 10))
            self.active_sen = sen_val

        try:
            slot = max(1, min(5, int(getattr(profile, "slot", 1))))
        except (ValueError, TypeError):
            slot = 1

        # 1. Select Slot
        buf = [REPORT_ID_DIRECT_DRIVE, 0x03, 0x01, slot & 0xFF] + [0x00] * 60
        self.write_report(buf)
        time.sleep(0.01)

        # 2. Build full tuning report buffer with all registers populated safely coerced
        def safe_int(attr, default=0):
            try:
                return int(getattr(profile, attr, default))
            except (ValueError, TypeError):
                return default

        reg_values = {
            "SLOT": slot,
            "SEN": raw_sen,
            "FF": max(0, min(100, safe_int("ff", 100))),
            "FFS": 1 if bool(getattr(profile, "ffs", 1)) and str(getattr(profile, "ffs", 1)) not in ("0", "False") else 0,
            "NDP": max(0, min(100, safe_int("ndp", 20))),
            "NFR": max(0, min(100, safe_int("nfr", 5))),
            "NIN": max(0, min(100, safe_int("nin", 0))),
            "INT": max(0, min(20, safe_int("int_filter", 3))),
            "FEI": max(0, min(100, safe_int("fei", 100))),
            "FOR": max(0, min(12, safe_int("for_mult", 100) // 10)),
            "SPR": max(0, min(12, safe_int("spr_mult", 100) // 10)),
            "DPR": max(0, min(12, safe_int("dpr_mult", 100) // 10)),
            "SHO": max(0, min(10, safe_int("sho", 100) // 10)),
            "BLI": max(0, min(100, safe_int("bli", 85))),
            "BRF": max(0, min(100, safe_int("brf", 50))),
        }

        out_buf = [REPORT_ID_DIRECT_DRIVE, 0x03, 0x00] + [0x00] * 61
        for reg_name, raw_val in reg_values.items():
            if reg_name in TUNING_REGISTERS:
                addr = TUNING_REGISTERS[reg_name]
                out_buf[addr + 1] = int(raw_val) & 0xFF
        self.write_report(out_buf)
        time.sleep(0.01)

    def read_tuning_profile(self, slot: int = 1) -> Optional[TuningProfile]:
        """Request and parse the active tuning report from the wheel base."""
        if self._fd is None or not self.connected:
            return None
        try:
            clamped_slot = max(1, min(5, int(slot)))
        except (ValueError, TypeError):
            clamped_slot = 1

        try:
            # Send slot query command: [0xFF, 0x03, 0x01, clamped_slot]
            buf = [REPORT_ID_DIRECT_DRIVE, 0x03, 0x01, clamped_slot & 0xFF] + [0x00] * 60
            self.write_report(buf)
            time.sleep(0.02)

            if self._fd is None or not self.connected:
                return None

            # Check if an input report is ready (outside the USB lock)
            r, _, _ = select.select([self._fd], [], [], 0.08)
            if r and self._fd is not None:
                with self._lock:
                    if self._fd is None:
                        return None
                    data = os.read(self._fd, 64)

                if len(data) >= 32 and data[0] == 0xFF and data[1] == 0x03:
                    prof = TuningProfile(slot=clamped_slot)
                    # Parse all registers from buffer
                    raw_sen = data[TUNING_REGISTERS["SEN"] + 1]
                    prof.sen = 0 if raw_sen == 0 else raw_sen * 10
                    prof.ff = data[TUNING_REGISTERS["FF"] + 1]
                    prof.ndp = data[TUNING_REGISTERS["NDP"] + 1]
                    prof.nfr = data[TUNING_REGISTERS["NFR"] + 1]
                    prof.nin = data[TUNING_REGISTERS["NIN"] + 1]
                    prof.int_filter = data[TUNING_REGISTERS["INT"] + 1]
                    prof.fei = data[TUNING_REGISTERS["FEI"] + 1]
                    prof.for_mult = data[TUNING_REGISTERS["FOR"] + 1] * 10
                    prof.spr_mult = data[TUNING_REGISTERS["SPR"] + 1] * 10
                    prof.dpr_mult = data[TUNING_REGISTERS["DPR"] + 1] * 10
                    prof.sho = data[TUNING_REGISTERS["SHO"] + 1] * 10
                    prof.bli = data[TUNING_REGISTERS["BLI"] + 1]
                    prof.brf = data[TUNING_REGISTERS["BRF"] + 1]
                    prof.ffs = data[TUNING_REGISTERS["FFS"] + 1]
                    return prof
        except Exception as e:
            logger.debug(f"Could not read tuning report: {e}")
        return None

    def calibrate_center(self):
        """Trigger center calibration sequence in hardware."""
        payload = [REPORT_ID_LEGACY_CMD, 0xF8, 0x09, 0x01, 0x06, 0x01, 0x00, 0x00]
        self.write_report(payload)

    def send_constant_force(self, level: int):
        """
        Send constant torque command to direct drive motor.
        level: signed integer from -32768 (full left) to +32767 (full right). 0 = no force.
        """
        if self._fd is None or not self.connected:
            return
        if level == 0:
            # Disable slot 0
            payload = [REPORT_ID_LEGACY_CMD, 0x03, 0x08, 0x00, 0x80, 0x00, 0x00, 0x01]
        else:
            clamped = max(-32768, min(32767, int(level)))
            val = (clamped + 0x8000) & 0xFFFF
            payload = [REPORT_ID_LEGACY_CMD, 0x01, 0x08, val & 0xFF, (val >> 8) & 0xFF, 0x00, 0x00, 0x01]
        self.write_report(payload)

    def send_centering_spring(self, strength: int = 50):
        """
        Engage hardware autocenter spring effect.
        strength: 0 to 100% (0 disables the spring).
        """
        if self._fd is None or not self.connected:
            return
        if strength <= 0:
            payload = [REPORT_ID_LEGACY_CMD, 0x13, 0x0B, 0x80, 0x80, 0x00, 0x00, 0x00]
        else:
            coeff = max(1, min(15, int((strength / 100.0) * 15)))
            k = (coeff << 4) | coeff
            payload = [REPORT_ID_LEGACY_CMD, 0x11, 0x0B, 0x80, 0x80, k, 0x00, 0xFF]
        self.write_report(payload)

    def send_damper_friction(self, friction: int = 50):
        """
        Apply mechanical friction/damper resistance to wheel rotation.
        friction: 0 to 100% (0 disables friction).
        """
        if self._fd is None or not self.connected:
            return
        if friction <= 0:
            payload = [REPORT_ID_LEGACY_CMD, 0x43, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00]
        else:
            coeff = max(1, min(255, int((friction / 100.0) * 255)))
            payload = [REPORT_ID_LEGACY_CMD, 0x41, 0x0C, coeff, 0x00, coeff, 0x00, 0xFF]
        self.write_report(payload)

    def send_handle_vibration(self, left: int = 0, right: int = 0):
        """
        Trigger rim grip vibration motors and peripheral pedal rumble motors.
        left, right: 0 to 255 intensity.
        """
        if self._fd is None or not self.connected:
            return
        payload = [
            REPORT_ID_LEGACY_CMD,
            0xF8, 0x09, 0x01, 0x03,
            max(0, min(255, int(left))),
            max(0, min(255, int(right))),
            0x00
        ]
        self.write_report(payload)

    def vibrate_wheel(self, intensity: int = 100, duration: float = 1.0, freq: int = 18):
        """
        Execute symmetric zero-rotation tactile rumble through the direct drive motor
        and peripheral pedal rumble motors concurrently.
        intensity: 0 to 100%.
        duration: duration in seconds.
        freq: oscillation frequency in Hz (optimal 18 Hz for wheel mechanical inertia).
        """
        if self._fd is None or not self.connected:
            return

        with self._lock:
            self._vibration_token = getattr(self, "_vibration_token", 0) + 1
            current_token = self._vibration_token
            self._abort_vibration = False

        clamped_intensity = max(0, min(100, int(intensity)))
        amp = int((clamped_intensity / 100.0) * 6000)

        # Trigger peripheral pedal/handle rumble packet concurrently
        pedal_val = int((clamped_intensity / 100.0) * 255)
        self.send_handle_vibration(pedal_val, pedal_val)

        if amp <= 0:
            self.send_constant_force(0)
            self.send_handle_vibration(0, 0)
            return

        period = 1.0 / max(1, freq)
        half = period / 2.0
        end_time = time.time() + duration

        while time.time() < end_time and not self._abort_vibration and self._vibration_token == current_token:
            self.send_constant_force(amp)
            time.sleep(half)
            if self._abort_vibration or self._vibration_token != current_token:
                break
            self.send_constant_force(-amp)
            time.sleep(half)

        # Only reset forces if no newer vibration has superseded this one
        if self._vibration_token == current_token:
            self.send_constant_force(0)
            self.send_handle_vibration(0, 0)

    def stop_all_forces(self):
        """Emergency stop: zero and disable all active motor effects and vibrations."""
        self._abort_vibration = True
        self.send_constant_force(0)
        self.send_centering_spring(0)
        self.send_damper_friction(0)
        self.send_handle_vibration(0, 0)
