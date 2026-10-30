"""
Telemetry Manager: Bridges sim games to Fanatec LEDs and OLED Display.
Includes Adaptive Peak RPM Auto-Calibration and Car Database.
"""

import logging
from typing import Any

from fanalinux.core.dynamic_ffb_engine import DynamicFFBEngine
from fanalinux.core.haptics import HapticEngine
from fanalinux.core.telemetry.ac import AssettoCorsaTelemetry
from fanalinux.core.telemetry.ams2 import AMS2Telemetry
from fanalinux.core.telemetry.beamng import BeamNGTelemetry
from fanalinux.core.telemetry.dirt import DirtRallyTelemetry
from fanalinux.core.telemetry.f1 import F1Telemetry
from fanalinux.core.telemetry.forza import ForzaTelemetry
from fanalinux.core.telemetry.scs import SCSTelemetry

logger = logging.getLogger("fanalinux.telemetry.manager")

TELEMETRY_FACTORIES = {
    "ac_udp": AssettoCorsaTelemetry,
    "ams2_udp": AMS2Telemetry,
    "beamng_outgauge": BeamNGTelemetry,
    "dirt_udp": DirtRallyTelemetry,
    "f1_udp": F1Telemetry,
    "forza_udp": ForzaTelemetry,
    "scs_shm": SCSTelemetry,
}


class TelemetryManager:
    def __init__(self, device):
        self.device = device
        self.enabled = False
        self.display_mode = "gear"  # "gear", "speed", or "custom"
        self.max_rpm = 6500         # Sane baseline (adaptive tracking will refine)
        self.peak_rpm_seen = 0
        self.auto_detect_rpm = True

        self._clients: dict[str, Any] = {}
        self.active_telemetry_type = "ac_udp"
        self.active_client = self._get_client("ac_udp")
        self.ac_client = self.active_client  # Backwards compatibility

        self.haptic_engine = HapticEngine(self.device)
        self.dynamic_ffb_engine = DynamicFFBEngine(self.device)
        self._last_gear = None
        self._last_speed_txt = None
        self._last_flag_state = None
        self._limiter_strobe = False
        self._stream_was_alive = False

    def _get_client(self, telem_type: str):
        if telem_type not in self._clients:
            factory = TELEMETRY_FACTORIES.get(telem_type, AssettoCorsaTelemetry)
            self._clients[telem_type] = factory(
                on_telemetry=self._handle_telemetry,
                on_car_detected=self.set_car_name
            )
        return self._clients[telem_type]

    def invalidate_output_caches(self):
        """Forget cached hardware state after emergency stops and reconnects."""
        try:
            self.dynamic_ffb_engine.invalidate_cache()
        except Exception:
            pass

    def check_stream_health(self):
        """Zero stuck motor outputs if the stream died silently.
        Polled from the UI heartbeat: on the connected->lost transition,
        clear haptic levels and the damper overlay (timeout path never
        calls stop(), so without this the last forces stick on the wheel).
        Also covers a game exit while Auto-Profile is disabled."""
        if not self.enabled:
            self._stream_was_alive = False
            return
        alive = bool(self.active_client and getattr(self.active_client, "is_connected", False))
        if self._stream_was_alive and not alive:
            logger.warning("Telemetry stream lost: clearing haptic and damper outputs")
            try:
                self.haptic_engine.zero_outputs()
            except Exception:
                pass
            try:
                self.dynamic_ffb_engine.reset()
            except Exception:
                pass
        self._stream_was_alive = alive

    @property
    def is_connected(self) -> bool:
        return bool(self.active_client and getattr(self.active_client, "is_connected", False))

    @property
    def is_running(self) -> bool:
        return bool(self.enabled or (self.active_client and getattr(self.active_client, "is_running", False)))

    def start(self, telemetry_type: str | None = None):
        self.enabled = True
        self._last_gear = None
        self._last_speed_txt = None
        self._last_flag_state = None

        target_type = telemetry_type or self.active_telemetry_type or "ac_udp"
        # Stop previous client whenever type differs to free ports (e.g. 20777)
        if self.active_client and self.active_telemetry_type != target_type:
            try:
                self.active_client.stop()
            except Exception:
                pass

        self.active_telemetry_type = target_type
        self.active_client = self._get_client(target_type)
        self.ac_client = self.active_client  # Backwards compatibility
        self.active_client.start()
        self.haptic_engine.start()

    def stop(self):
        self.enabled = False
        self._last_gear = None
        self._last_speed_txt = None
        self._last_flag_state = None
        # Stop all instantiated clients to prevent socket leaks / port conflicts
        for client in self._clients.values():
            try:
                client.stop()
            except Exception:
                pass
        self.haptic_engine.stop()
        self.dynamic_ffb_engine.reset()
        if self.device and self.device.connected:
            self.device.set_revleds([(0, 0, 0)] * 9)
            self.device.set_flagleds([(0, 0, 0)] * 6)
            self.device.clear_display()

    def set_car_name(self, car_name: str):
        """Seed the redline from the car class; live learning refines it."""
        cleaned = car_name.lower().strip()
        self.peak_rpm_seen = 0
        # Heuristics for common car classes
        if "formula4" in cleaned or "f4" in cleaned or "tatuus" in cleaned:
            self.max_rpm = 6500
        elif "gt3" in cleaned or "gt4" in cleaned:
            self.max_rpm = 7500
        elif "formula" in cleaned or "f1" in cleaned:
            self.max_rpm = 13500
        else:
            self.max_rpm = 6500

    def _handle_telemetry(self, rpm: int, gear: int, speed_kmh: float, abs_active: bool, tc_active: bool,
                          wheel_slip=(0.0, 0.0, 0.0, 0.0),
                          wheel_speed=(0.0, 0.0, 0.0, 0.0),
                          suspension=(0.0, 0.0, 0.0, 0.0),
                          steer_angle=0.0):
        if not self.enabled or not self.device or not self.device.connected:
            return

        # Adaptive Peak Tracking: learn the car's actual rev ceiling live.
        # Over-rev guard: a real pull climbs gradually, a downshift money-shift
        # arrives as a huge single-frame jump — ignore jumps over 500 rpm so a
        # spike can't ratchet the redline up and silence the shift lights.
        if self.auto_detect_rpm:
            if rpm > self.peak_rpm_seen and (self.peak_rpm_seen == 0 or rpm - self.peak_rpm_seen <= 500):
                self.peak_rpm_seen = rpm
                if self.peak_rpm_seen > 4000:
                    self.max_rpm = self.peak_rpm_seen

        # 1. Update OLED Display
        if self.display_mode == "gear":
            if gear != self._last_gear:
                self._last_gear = gear
                gear_str = "R" if gear < 0 else ("N" if gear == 0 else str(gear))
                self.device.set_display_text(gear_str)
        elif self.display_mode == "speed":
            speed_int = max(0, min(999, int(speed_kmh)))
            speed_txt = f"{speed_int:03d}"
            if speed_txt != getattr(self, "_last_speed_txt", None):
                self._last_speed_txt = speed_txt
                self.device.set_display_text(speed_txt)

        # 2. Update 9 RevLEDs
        # Scale: rev lights start at 60% of redline and reach full at 96%
        effective_max = max(3000, self.max_rpm)
        pct = max(0.0, min(1.0, rpm / effective_max))
        
        # Shift spectrum: Green (LED 1..3), Yellow (4..6), Red (7..8), Blue (9)
        colors = [
            (0, 255, 0), (0, 255, 0), (0, 255, 0),
            (255, 255, 0), (255, 255, 0), (255, 255, 0),
            (255, 0, 0), (255, 0, 0), (0, 0, 255)
        ]

        if pct >= 0.96:
            # Shift limit reached: Strobe all blue/white
            self._limiter_strobe = not self._limiter_strobe
            active_colors = [(0, 150, 255)] * 9 if self._limiter_strobe else [(0, 0, 0)] * 9
        elif pct >= 0.55:
            # Map 55%..96% range linearly across the 9 LEDs
            active_count = int(((pct - 0.55) / 0.41) * 9)
            active_count = max(1, min(9, active_count))
            active_colors = colors[:active_count] + [(0, 0, 0)] * (9 - active_count)
        else:
            active_colors = [(0, 0, 0)] * 9

        self.device.set_revleds(active_colors)

        # 3. Handle Flag LEDs on ABS / TC alerts with state tracking and black turn-off
        flag_state = "ABS" if abs_active else ("TC" if tc_active else "OFF")
        if flag_state != getattr(self, "_last_flag_state", None):
            self._last_flag_state = flag_state
            if abs_active:
                self.device.set_flagleds([(255, 255, 0)] * 6)  # Yellow ABS warning
            elif tc_active:
                self.device.set_flagleds([(0, 100, 255)] * 6)   # Blue TC warning
            else:
                self.device.set_flagleds([(0, 0, 0)] * 6)        # Turn off LEDs

        # 4. Trigger Haptic Vibration Pulses (ABS, TC, Rev Limiter, Engine, Wheel Lock/Spin, Slip)
        self.haptic_engine.update_telemetry(
            rpm, effective_max, abs_active, tc_active, speed_kmh,
            wheel_slip=wheel_slip,
            wheel_speed=wheel_speed,
            suspension=suspension,
            steer_angle=steer_angle
        )

        # 5. Execute Dynamic FFB Damper Overlay (Speed-Sensitive & Reverse Driving Damper)
        active_sen = getattr(self.device, "active_sen", 900)
        if active_sen <= 0:
            active_sen = 900
        self.dynamic_ffb_engine.update_telemetry(
            speed_kmh, gear, steer_angle,
            wheel_speed=wheel_speed,
            active_sen=active_sen
        )
