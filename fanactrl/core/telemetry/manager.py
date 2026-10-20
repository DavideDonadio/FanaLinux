"""
Telemetry Manager: Bridges sim games to Fanatec LEDs and OLED Display.
"""

import time
import logging
from typing import Optional, Callable
from fanactrl.core.telemetry.ac import AssettoCorsaTelemetry

logger = logging.getLogger("fanactrl.telemetry.manager")


class TelemetryManager:
    def __init__(self, device, on_status_change: Optional[Callable[[bool, str], None]] = None):
        self.device = device
        self.on_status_change = on_status_change
        self.enabled = False
        self.display_mode = "gear"  # "gear", "speed", or "custom"
        self.max_rpm = 9000

        self.ac_client = AssettoCorsaTelemetry(on_telemetry=self._handle_telemetry)
        self._last_gear = None
        self._limiter_strobe = False

    def start(self):
        self.enabled = True
        self.ac_client.start()

    def stop(self):
        self.enabled = False
        self.ac_client.stop()
        if self.device and self.device.connected:
            self.device.set_revleds([(0, 0, 0)] * 9)
            self.device.clear_display()

    def _handle_telemetry(self, rpm: int, gear: int, speed_kmh: float, abs_active: bool, tc_active: bool):
        if not self.enabled or not self.device or not self.device.connected:
            return

        # 1. Update OLED Display
        if self.display_mode == "gear":
            if gear != self._last_gear:
                self._last_gear = gear
                gear_str = "R" if gear < 0 else ("N" if gear == 0 else str(gear))
                self.device.set_display_text(gear_str)
        elif self.display_mode == "speed":
            speed_int = max(0, min(999, int(speed_kmh)))
            self.device.set_display_text(f"{speed_int:03d}")

        # 2. Update 9 RevLEDs
        pct = max(0.0, min(1.0, rpm / max(1000, self.max_rpm)))
        
        # Shift spectrum: Green (LED 1..3), Yellow (4..6), Red (7..8), Blue (9)
        colors = [
            (0, 255, 0), (0, 255, 0), (0, 255, 0),
            (255, 255, 0), (255, 255, 0), (255, 255, 0),
            (255, 0, 0), (255, 0, 0), (0, 0, 255)
        ]

        if pct >= 0.98:
            # Shift limit reached: Strobe all blue/white
            self._limiter_strobe = not self._limiter_strobe
            active_colors = [(0, 150, 255)] * 9 if self._limiter_strobe else [(0, 0, 0)] * 9
        elif pct >= 0.65:
            # Map 65%..98% range across the 9 LEDs
            active_count = int(((pct - 0.65) / 0.33) * 9)
            active_count = max(1, min(9, active_count))
            active_colors = colors[:active_count] + [(0, 0, 0)] * (9 - active_count)
        else:
            active_colors = [(0, 0, 0)] * 9

        self.device.set_revleds(active_colors)

        # 3. Handle Flag LEDs on ABS / TC alerts
        if abs_active:
            self.device.set_flagleds([(255, 255, 0)] * 6)  # Yellow ABS warning
        elif tc_active:
            self.device.set_flagleds([(0, 100, 255)] * 6)   # Blue TC warning
