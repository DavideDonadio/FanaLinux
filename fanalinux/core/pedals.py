"""Software brake force for USB ClubSport V3 pedals, as in BrakeTune.

Only the standalone USB pedal device is grabbed; wheelbases are never mapped.
The worker owns all descriptors and releases them on disable, exit or unplug.
"""

import logging
import math
import os
import select
import threading
from contextlib import ExitStack
from dataclasses import asdict, dataclass

from evdev import InputDevice, UInput, ecodes, list_devices
from evdev.uinput import UInputError

from fanalinux.core.persistence import CONFIG_DIR, load_json_dict, save_json_dict

logger = logging.getLogger("fanalinux.pedals")
SETTINGS_PATH = os.path.join(CONFIG_DIR, "pedals.json")
VIRTUAL_NAME = "FanaLinux Pedals"
BRAKE_AXIS = ecodes.ABS_Y


def clamp_force(value):
    try:
        return max(1, min(100, int(value)))
    except (TypeError, ValueError, OverflowError):
        return 100


def scale_brake(raw, percent, minimum, maximum):
    """100% passes through; at 20%, one fifth of the range gives full braking."""
    scaled = minimum + (raw - minimum) * 100 / clamp_force(percent)
    return max(minimum, min(maximum, math.floor(scaled + 0.5)))


@dataclass
class PedalSettings:
    enabled: bool = False
    brake_force: int = 100

    @classmethod
    def load(cls):
        data = load_json_dict(SETTINGS_PATH) or {}
        return cls(data.get("enabled") is True, clamp_force(data.get("brake_force", 100)))

    def save(self):
        return save_json_dict(SETTINGS_PATH, asdict(self))


class PedalMapper:
    def __init__(self, brake_force=100):
        self.percent = clamp_force(brake_force)
        self.status = "Disabled"
        self.input = 0.0
        self.output = 0.0
        self._stop = threading.Event()
        self._thread = None

    def set_force(self, value):
        self.percent = clamp_force(value)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.status = "Waiting for USB ClubSport V3 pedals"
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join()
            self._thread = None
        self.status = "Disabled"
        self.input = self.output = 0.0

    @staticmethod
    def _find_pedals():
        for path in list_devices():
            device = None
            try:
                device = InputDevice(path)
                if (device.info.vendor == 0x0EB7
                        and device.info.product == 0x183B
                        and device.info.bustype == ecodes.BUS_USB
                        and device.name != VIRTUAL_NAME
                        and BRAKE_AXIS in device.capabilities(absinfo=False).get(ecodes.EV_ABS, [])):
                    return device
            except OSError as exc:
                logger.debug("Cannot inspect %s: %s", path, exc)
            if device is not None:
                device.close()
        return None

    def _worker(self):
        while not self._stop.is_set():
            try:
                device = self._find_pedals()
                if device is None:
                    self.status = "Waiting for USB ClubSport V3 pedals (check input permissions)"
                else:
                    with device:
                        self._session(device)
            except (OSError, UInputError) as exc:
                self.status = f"Pedals unavailable: {exc}. Check udev permissions and uinput."
                logger.warning(self.status)
            finally:
                self.input = self.output = 0.0
            self._stop.wait(1.0)

    def _write_brake(self, virtual, raw, percent, axis):
        value = scale_brake(raw, percent, axis.min, axis.max)
        span = axis.max - axis.min
        self.input = max(0.0, min(1.0, (raw - axis.min) / span))
        self.output = max(0.0, min(1.0, (value - axis.min) / span))
        virtual.write(ecodes.EV_ABS, BRAKE_AXIS, value)

    def _snapshot(self, device, virtual, percent, axis):
        """Initialize/resync all axes and keys, including pedals already held."""
        raw = axis.min
        capabilities = device.capabilities(absinfo=False)
        for code in capabilities.get(ecodes.EV_ABS, []):
            value = device.absinfo(code).value
            if code == BRAKE_AXIS:
                raw = value
                self._write_brake(virtual, raw, percent, axis)
            else:
                virtual.write(ecodes.EV_ABS, code, value)
        active = set(device.active_keys())
        for code in capabilities.get(ecodes.EV_KEY, []):
            virtual.write(ecodes.EV_KEY, code, int(code in active))
        virtual.syn()
        return raw

    def _session(self, device):
        axis = device.absinfo(BRAKE_AXIS)
        if axis.max <= axis.min:
            raise OSError("USB pedals expose an invalid brake axis range")
        with ExitStack() as stack:
            # Create output before taking exclusive input ownership. Closing the
            # source also releases EVIOCGRAB if explicit ungrab ever fails.
            virtual = stack.enter_context(UInput.from_device(
                device, name=VIRTUAL_NAME, vendor=device.info.vendor,
                product=device.info.product, version=device.info.version,
                bustype=ecodes.BUS_VIRTUAL))
            device.grab()
            stack.callback(device.ungrab)
            percent = self.percent
            raw = self._snapshot(device, virtual, percent, axis)
            self.status = f"Connected — select {VIRTUAL_NAME} in your game"
            dropped = False
            while not self._stop.is_set():
                current = self.percent
                if current != percent:
                    percent = current
                    self._write_brake(virtual, raw, percent, axis)
                    virtual.syn()
                ready, _, _ = select.select([device], [], [], 0.05)
                if not ready:
                    continue
                for event in device.read():
                    if event.type == ecodes.EV_SYN and event.code == ecodes.SYN_DROPPED:
                        dropped = True
                        continue
                    if dropped:
                        if event.type == ecodes.EV_SYN and event.code == ecodes.SYN_REPORT:
                            raw = self._snapshot(device, virtual, percent, axis)
                            dropped = False
                        continue
                    if event.type == ecodes.EV_ABS and event.code == BRAKE_AXIS:
                        raw = event.value
                        self._write_brake(virtual, raw, percent, axis)
                    else:
                        virtual.write_event(event)
