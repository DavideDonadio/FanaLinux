"""
High-Performance Linux Evdev Input Monitor.

Reads low-latency steering, pedal axes, and button matrix states
from /dev/input/ event nodes.
"""

import os
import glob
import struct
import select
import threading
import logging
from typing import Callable, Optional, Dict

from fanalinux.core.calibration import load_calibration_settings, save_calibration_settings, CalibrationSettings

logger = logging.getLogger("fanalinux.evdev")

# struct input_event { timeval time; __u16 type; __u16 code; __s32 value; }
EVENT_FORMAT = 'qqHHi'
EVENT_SIZE = struct.calcsize(EVENT_FORMAT)

EV_KEY = 0x01
EV_ABS = 0x03

ABS_X = 0x00       # Steering
ABS_Y = 0x01       # Additional Axis
ABS_Z = 0x02       # Throttle / Accelerator
ABS_RZ = 0x05      # Brake
ABS_THROTTLE = 0x06 # Clutch / Aux
ABS_HAT0X = 0x10   # D-Pad / FunkySwitch Hat X
ABS_HAT0Y = 0x11   # D-Pad / FunkySwitch Hat Y


class EvdevListener:
    def __init__(self,
                 on_steering: Optional[Callable[[float, int], None]] = None,
                 on_throttle: Optional[Callable[[float], None]] = None,
                 on_brake: Optional[Callable[[float], None]] = None,
                 on_clutch: Optional[Callable[[float], None]] = None,
                 on_button: Optional[Callable[[int, bool], None]] = None):
        self.on_steering = on_steering
        self.on_throttle = on_throttle
        self.on_brake = on_brake
        self.on_clutch = on_clutch
        self.on_button = on_button

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._fd: Optional[int] = None
        self.device_node: Optional[str] = None

        # Steering Calibration Offset (Persistent)
        self.calibration: CalibrationSettings = load_calibration_settings()
        self.center_raw: int = self.calibration.center_raw
        self.last_raw_steering: int = self.center_raw

    def set_center_raw(self, raw_val: int):
        """Set the calibrated center position and persist to disk."""
        self.center_raw = int(raw_val)
        self.calibration.center_raw = self.center_raw
        save_calibration_settings(self.calibration)
        logger.info(f"Steering center updated to raw value {self.center_raw}")

    def reset_center(self):
        """Reset steering center to factory default (32768)."""
        self.set_center_raw(32768)

    def find_device_node(self) -> Optional[str]:
        """Locate the Fanatec joystick event node with auto-probing."""
        # Check by-id symlinks first
        patterns = [
            "/dev/input/by-id/*Fanatec*-event-joystick",
            "/dev/input/by-id/*FANATEC*-event-joystick",
            "/dev/input/by-id/*Fanatec*-event*",
            "/dev/input/by-id/*FANATEC*-event*",
        ]
        for pat in patterns:
            matches = glob.glob(pat)
            if matches:
                return matches[0]

        # Scan all /dev/input/event* nodes by querying hardware name
        import fcntl
        EVIOCGNAME = 0x82004506
        for node in glob.glob("/dev/input/event*"):
            fd = None
            try:
                fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK)
                buf = bytearray(256)
                fcntl.ioctl(fd, EVIOCGNAME, buf)
                name = buf.split(b'\x00')[0].decode('utf-8', errors='ignore')
                if "FANATEC" in name.upper():
                    return node
            except Exception:
                pass
            finally:
                if fd is not None:
                    try:
                        os.close(fd)
                    except Exception:
                        pass
        return None

    def start(self) -> bool:
        """Start the background evdev polling thread."""
        node = self.find_device_node()
        if not node:
            logger.warning("No Fanatec evdev node found.")
            return False

        try:
            self._fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK)
            self.device_node = node

            # Probe axis min/max values dynamically using EVIOCGABS
            self._axis_ranges = {}
            import fcntl
            EVIOCGABS = lambda axis: 0x80184540 + axis
            for axis_code in [ABS_X, ABS_Z, ABS_RZ, ABS_THROTTLE]:
                buf = bytearray(24)
                try:
                    fcntl.ioctl(self._fd, EVIOCGABS(axis_code), buf)
                    _, min_v, max_v, _, _, _ = struct.unpack("iiiiii", buf)
                    self._axis_ranges[axis_code] = (min_v, max_v)
                except Exception:
                    pass

            self._running = True
            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()
            logger.info(f"EvdevListener started on {node}")
            return True
        except Exception as e:
            logger.error(f"Failed to open evdev node {node}: {e}")
            return False

    def is_running(self) -> bool:
        """Check if listener is actively running with an open event node."""
        return self._running and self._fd is not None

    def stop(self):
        """Stop the background polling thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._fd is not None:
            try:
                os.close(self._fd)
            except Exception:
                pass
            self._fd = None

    def _worker(self):
        """Worker loop reading events."""
        while self._running and self._fd is not None:
            try:
                r, _, _ = select.select([self._fd], [], [], 0.05)
                if not r:
                    continue

                raw = os.read(self._fd, EVENT_SIZE * 32)
                for i in range(0, len(raw), EVENT_SIZE):
                    chunk = raw[i:i + EVENT_SIZE]
                    if len(chunk) == EVENT_SIZE:
                        sec, usec, etype, code, value = struct.unpack(EVENT_FORMAT, chunk)
                        self._process_event(etype, code, value)
            except Exception as e:
                if self._running:
                    logger.info(f"Evdev device disconnected: {e}")
                self._running = False
                if self._fd is not None:
                    try:
                        os.close(self._fd)
                    except Exception:
                        pass
                    self._fd = None
                break

    def _normalize_pedal(self, code: int, value: int) -> float:
        ranges = getattr(self, "_axis_ranges", {})
        default_max = 255 if code == ABS_THROTTLE else 65535
        min_v, max_v = ranges.get(code, (0, default_max))
        span = max(1, max_v - min_v)
        # Invert: raw unpressed is max, raw fully pressed is min
        norm = 1.0 - ((value - min_v) / float(span))
        return max(0.0, min(1.0, norm))

    def _process_event(self, etype: int, code: int, value: int):
        if etype == EV_ABS:
            if code == ABS_X and self.on_steering:
                self.last_raw_steering = value
                # 0..65535, calibrated against self.center_raw
                normalized = (value - float(self.center_raw)) / 32768.0
                normalized = max(-1.0, min(1.0, normalized))
                self.on_steering(normalized, value)
            elif code == ABS_Z and self.on_throttle:
                self.on_throttle(self._normalize_pedal(code, value))
            elif code == ABS_RZ and self.on_brake:
                self.on_brake(self._normalize_pedal(code, value))
            elif code == ABS_THROTTLE and self.on_clutch:
                self.on_clutch(self._normalize_pedal(code, value))
            elif code == ABS_HAT0X and self.on_button:
                # D-Pad / FunkySwitch X: -1 = Left, 1 = Right, 0 = Released
                prev_x = getattr(self, "_hat_x", 0)
                if prev_x != value:
                    if prev_x == -1:
                        self.on_button("HAT_LEFT", False)
                    elif prev_x == 1:
                        self.on_button("HAT_RIGHT", False)
                    if value == -1:
                        self.on_button("HAT_LEFT", True)
                    elif value == 1:
                        self.on_button("HAT_RIGHT", True)
                    self._hat_x = value
            elif code == ABS_HAT0Y and self.on_button:
                # D-Pad / FunkySwitch Y: -1 = Up, 1 = Down, 0 = Released
                prev_y = getattr(self, "_hat_y", 0)
                if prev_y != value:
                    if prev_y == -1:
                        self.on_button("HAT_UP", False)
                    elif prev_y == 1:
                        self.on_button("HAT_DOWN", False)
                    if value == -1:
                        self.on_button("HAT_UP", True)
                    elif value == 1:
                        self.on_button("HAT_DOWN", True)
                    self._hat_y = value

        elif etype == EV_KEY and self.on_button:
            # Map Linux evdev joystick key codes to 1-based button numbers
            if 288 <= code <= 303:
                btn_num = code - 288 + 1      # Buttons 1..16 (BTN_TRIGGER..BTN_TOP2)
            elif 704 <= code <= 767:
                btn_num = code - 704 + 17     # Buttons 17..80 (BTN_TRIGGER_HAPPY1..64)
            elif 304 <= code <= 319:
                btn_num = code - 304 + 81     # Gamepad buttons mapped to 81..96 (non-overlapping)
            else:
                btn_num = code
            is_pressed = (value == 1)
            self.on_button(btn_num, is_pressed)
