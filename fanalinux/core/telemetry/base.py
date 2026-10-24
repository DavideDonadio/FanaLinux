"""
Base Telemetry Client for Linux Sim Racing Suite.
Provides thread management, callback signature inspection, and safe dispatching.
"""

import inspect
import logging
import threading
from collections.abc import Callable

logger = logging.getLogger("fanalinux.telemetry.base")


class BaseTelemetryClient:
    def __init__(self,
                 on_telemetry: Callable | None = None,
                 on_car_detected: Callable[[str], None] | None = None,
                 default_max_rpm: int = 6500):
        self._on_telemetry = on_telemetry
        self.on_car_detected = on_car_detected
        self.default_max_rpm = default_max_rpm
        self.max_rpm = default_max_rpm
        self.car_name = "Unknown"
        self._running = False
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.is_connected = False
        self._callback_takes_extended = True
        self._inspect_callback()

    @property
    def is_running(self) -> bool:
        return bool(self._running or (self._thread and self._thread.is_alive()))

    @property
    def on_telemetry(self):
        return self._on_telemetry

    @on_telemetry.setter
    def on_telemetry(self, cb):
        self._on_telemetry = cb
        self._inspect_callback()

    def _inspect_callback(self):
        if not self._on_telemetry:
            self._callback_takes_extended = False
            return
        try:
            sig = inspect.signature(self._on_telemetry)
            params = sig.parameters
            has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
            self._callback_takes_extended = len(params) >= 6 or "wheel_speed" in params or has_var_keyword
        except Exception:
            self._callback_takes_extended = True

    def _dispatch_telemetry(self, rpm: int, gear: int, speed_kmh: float, abs_active: bool, tc_active: bool,
                            wheel_slip=(0.0, 0.0, 0.0, 0.0),
                            wheel_speed=(0.0, 0.0, 0.0, 0.0),
                            suspension=(0.0, 0.0, 0.0, 0.0),
                            steer_angle=0.0):
        """Invoke on_telemetry callback safely supporting both 5-arg and extended 9-arg signatures."""
        if not self.on_telemetry:
            return
        try:
            if getattr(self, "_callback_takes_extended", True):
                self.on_telemetry(
                    rpm, gear, speed_kmh, abs_active, tc_active,
                    wheel_slip=wheel_slip,
                    wheel_speed=wheel_speed,
                    suspension=suspension,
                    steer_angle=steer_angle
                )
            else:
                self.on_telemetry(rpm, gear, speed_kmh, abs_active, tc_active)
        except Exception as e:
            logger.error(f"Error calling telemetry callback: {e}")

    def start(self):
        """Start background polling thread."""
        if self._running:
            return
        old = self._thread
        if old is not None and old.is_alive():
            # Previous worker outlived stop()'s join; wait it out so two
            # workers never run against the same client and socket.
            old.join(timeout=2.0)
            if old.is_alive():
                logger.warning(f"{self.__class__.__name__} previous worker still alive; not starting a second one")
                return
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True, name=f"{self.__class__.__name__}Thread")
        self._thread.start()
        logger.info(f"{self.__class__.__name__} started")

    def stop(self):
        """Stop background worker thread."""
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.5)
            if self._thread.is_alive():
                # Keep the handle so start()'s guard can see the survivor.
                logger.warning(f"{self.__class__.__name__} worker did not exit; keeping handle for restart guard")
            else:
                self._thread = None
        self.is_connected = False
        logger.info(f"{self.__class__.__name__} stopped")

    def _worker(self):
        raise NotImplementedError
