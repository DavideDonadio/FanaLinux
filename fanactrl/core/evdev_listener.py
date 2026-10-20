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

logger = logging.getLogger("fanactrl.evdev")

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
            try:
                fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK)
                buf = bytearray(256)
                fcntl.ioctl(fd, EVIOCGNAME, buf)
                os.close(fd)
                name = buf.split(b'\x00')[0].decode('utf-8', errors='ignore')
                if "FANATEC" in name.upper():
                    return node
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
            self._running = True
            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()
            logger.info(f"EvdevListener started on {node}")
            return True
        except Exception as e:
            logger.error(f"Failed to open evdev node {node}: {e}")
            return False

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
                    logger.error(f"Error reading evdev events: {e}")
                break

    def _process_event(self, etype: int, code: int, value: int):
        if etype == EV_ABS:
            if code == ABS_X and self.on_steering:
                # 0..65535, center ~32768 -> -1.0 .. +1.0
                normalized = (value - 32768.0) / 32768.0
                self.on_steering(normalized, value)
            elif code == ABS_Z and self.on_throttle:
                # 0..65535, inverting if needed (0 = released, 65535 = pressed)
                # Fanatec raw 16-bit is often 65535 unpressed -> 0 pressed
                norm = 1.0 - (value / 65535.0)
                self.on_throttle(max(0.0, min(1.0, norm)))
            elif code == ABS_RZ and self.on_brake:
                norm = 1.0 - (value / 65535.0)
                self.on_brake(max(0.0, min(1.0, norm)))
            elif code == ABS_THROTTLE and self.on_clutch:
                norm = 1.0 - (value / 255.0)
                self.on_clutch(max(0.0, min(1.0, norm)))

        elif etype == EV_KEY and self.on_button:
            is_pressed = (value == 1)
            self.on_button(code, is_pressed)
