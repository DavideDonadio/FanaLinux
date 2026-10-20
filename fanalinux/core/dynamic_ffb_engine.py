"""
Dynamic Force Feedback Engine (FanaLab 'FFB Dynamique' Parity).
Calculates and injects real-time PC-side telemetry damping overlays:
1. Speed-Sensitive Dynamic Damper (Stabilizes high-speed straights)
2. Reverse Driving Safety Damper (Prevents violent DD wheel snapping when rolling backwards)
"""

import time
import math
import logging
from typing import Optional
from fanalinux.core.dynamic_ffb import DynamicFFBSettings, load_dynamic_ffb_settings

logger = logging.getLogger("fanalinux.dynamic_ffb")


class DynamicFFBEngine:
    def __init__(self, device, settings: Optional[DynamicFFBSettings] = None):
        self.device = device
        self.settings = settings or load_dynamic_ffb_settings()
        self._last_applied_damping = -1
        self._reverse_fade_current = 0.0  # Smooth ramping for reverse damper

    def reload_settings(self):
        """Reload settings from disk."""
        self.settings = load_dynamic_ffb_settings()

    def update_telemetry(self, speed_kmh: float, gear: int, steer_angle: float):
        """
        Process incoming sim telemetry frame and compute damper overlay.
        steer_angle is normalized from -1.0 to 1.0 (-450 to +450 degrees).
        """
        if not self.device or not self.device.connected:
            return

        target_damping = 0

        # 1. Reverse Driving Safety Damper
        is_reverse = (gear < 0) or (gear == 0 and speed_kmh < -2.0)
        if self.settings.reverse_damper_enabled and is_reverse and abs(speed_kmh) > 3.0:
            # Ramp in reverse damper based on fade-in intensity (1..10)
            ramp_step = max(0.1, self.settings.reverse_fade_in / 10.0)
            self._reverse_fade_current = min(1.0, self._reverse_fade_current + ramp_step)
            target_damping = int(self.settings.reverse_damper_strength * self._reverse_fade_current)
        else:
            self._reverse_fade_current = 0.0

            # 2. Speed-Sensitive Dynamic Damper
            if self.settings.speed_sensitive_enabled and speed_kmh >= self.settings.speed_threshold_min:
                # Calculate speed scaling factor (0.0 to 1.0)
                speed_range = max(10, self.settings.speed_threshold_max - self.settings.speed_threshold_min)
                speed_factor = min(1.0, max(0.0, (speed_kmh - self.settings.speed_threshold_min) / speed_range))

                # Calculate angle window factor
                # steer_angle is -1.0..1.0 where 1.0 = 450 deg (or 900 deg rotation)
                actual_deg = abs(steer_angle * 450.0)
                half_range = max(5.0, self.settings.damper_effect_range / 2.0)

                if actual_deg <= half_range:
                    angle_factor = 1.0 - (actual_deg / half_range) * 0.5
                else:
                    # Taper off beyond the configured range so cornering feel is preserved
                    angle_factor = max(0.0, 1.0 - ((actual_deg - half_range) / 30.0))

                target_damping = int(self.settings.damper_effect_strength * speed_factor * angle_factor)

        # Apply target damping to hardware if changed
        target_damping = max(0, min(100, target_damping))
        if target_damping != self._last_applied_damping:
            self._last_applied_damping = target_damping
            try:
                self.device.send_damper_friction(target_damping)
            except Exception as e:
                logger.debug(f"Could not apply dynamic damping: {e}")

    def reset(self):
        """Reset applied damping back to zero."""
        self._reverse_fade_current = 0.0
        if self._last_applied_damping > 0:
            self._last_applied_damping = 0
            if self.device and self.device.connected:
                try:
                    self.device.send_damper_friction(0)
                except Exception:
                    pass
