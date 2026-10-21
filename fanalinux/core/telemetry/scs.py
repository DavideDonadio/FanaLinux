"""
Euro Truck Simulator 2 & American Truck Simulator Telemetry Client for Linux.
Reads from POSIX Shared Memory (/dev/shm/SCSTelemetry or /dev/shm/SimTelemetryETS2)
created by the SCS SDK plugin on Linux.
"""

import os
import mmap
import time
import struct
import logging
from typing import Callable, Optional
from fanalinux.core.telemetry.base import BaseTelemetryClient

logger = logging.getLogger("fanalinux.telemetry.scs")

# Possible Linux shared memory paths for SCS Telemetry
SHM_PATHS = [
    "/dev/shm/SCSTelemetry",
    "/dev/shm/SimTelemetryETS2"
]


class SCSTelemetry(BaseTelemetryClient):
    """
    SCS Software Telemetry reader for Euro Truck Simulator 2 and American Truck Simulator.
    Reads binary shared memory at ~40Hz.
    """
    def __init__(self,
                 on_telemetry: Optional[Callable] = None,
                 on_car_detected: Optional[Callable[[str], None]] = None,
                 default_max_rpm: int = 2500,
                 poll_rate_hz: float = 40.0):
        super().__init__(on_telemetry=on_telemetry,
                         on_car_detected=on_car_detected,
                         default_max_rpm=default_max_rpm)
        self.poll_interval = 1.0 / max(10.0, min(100.0, poll_rate_hz))
        self._mmap_obj: Optional[mmap.mmap] = None
        self._fd: Optional[int] = None

    def stop(self):
        super().stop()
        self._close_shm()

    def _close_shm(self):
        if self._mmap_obj:
            try:
                self._mmap_obj.close()
            except Exception:
                pass
            self._mmap_obj = None
        if self._fd is not None:
            try:
                os.close(self._fd)
            except Exception:
                pass
            self._fd = None
        self.is_connected = False

    def _try_open_shm(self) -> bool:
        for path in SHM_PATHS:
            if os.path.exists(path):
                try:
                    fd = os.open(path, os.O_RDONLY)
                    size = os.path.getsize(path)
                    if size >= 1000:
                        mm = mmap.mmap(fd, length=0, access=mmap.ACCESS_READ)
                        self._fd = fd
                        self._mmap_obj = mm
                        self.is_connected = True
                        logger.info(f"Connected to SCS telemetry shared memory at {path} ({size} bytes)")
                        return True
                    else:
                        os.close(fd)
                except Exception as e:
                    logger.debug(f"Failed to open shared memory at {path}: {e}")
        return False

    def _worker(self):
        while self._running:
            if not self.is_connected or not self._mmap_obj:
                if not self._try_open_shm():
                    time.sleep(1.0)
                    continue

            try:
                self.process_frame(self._mmap_obj)
            except Exception as e:
                logger.debug(f"Error reading SCS shared memory: {e}")
                self._close_shm()
                time.sleep(1.0)
                continue

            time.sleep(self.poll_interval)

    def process_frame(self, mm: mmap.mmap):
        """
        Parse SCS Telemetry structure (v1.10 - v1.12 layout).
        Key offsets:
          4: bool paused
          504: int32 gear (-1=Rev, 0=Neutral, 1+=Fwd)
          740: float32 engineRpmMax
          948: float32 speed (m/s)
          952: float32 engineRpm
          956: float32 userSteer
          960: float32 userThrottle
          964: float32 userBrake
        """
        if len(mm) < 968:
            return

        # Paused check at offset 4
        paused = struct.unpack_from("<?", mm, 4)[0]
        if paused:
            self._dispatch_telemetry(
                rpm=0,
                gear=0,
                speed_kmh=0.0,
                abs_active=False,
                tc_active=False
            )
            return

        gear = struct.unpack_from("<i", mm, 504)[0]
        rpm_max = struct.unpack_from("<f", mm, 740)[0]
        speed_ms, rpm, steer, throttle, brake = struct.unpack_from("<5f", mm, 948)

        if rpm_max > 500.0:
            self.max_rpm = int(rpm_max)

        speed_kmh = max(0.0, float(speed_ms * 3.6))
        rpm_int = max(0, int(rpm))

        # Truck gear representation: gear < 0 is reverse (-1, -2...), 0 is neutral, > 0 forward
        display_gear = gear if gear >= 0 else -1

        self._dispatch_telemetry(
            rpm=rpm_int,
            gear=display_gear,
            speed_kmh=speed_kmh,
            abs_active=False,
            tc_active=False,
            steer_angle=float(steer)
        )
