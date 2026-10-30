"""
Telemetry-Driven Haptic Feedback Engine.
Executes real-time rim & pedal vibration pulses responding to in-game telemetry events.
"""

import logging
import threading
import time

from fanalinux.core.vibration import VibrationSettings, load_vibration_settings

logger = logging.getLogger("fanalinux.haptics")


class HapticEngine:
    def __init__(self, device, settings: VibrationSettings | None = None):
        self.device = device
        self.settings = settings or load_vibration_settings()
        self._running = False
        self._lock = threading.Lock()

        # Active pulse state
        self._pulse_end_time = 0.0
        self._pulse_intensity = 0  # 0 to 100
        self._pulse_active = False

        # Continuous engine vibration level
        self._engine_vibration_level = 0  # 0 to 100

        # Cooldown / repeat throttling
        self._last_abs_pulse = 0.0
        self._last_tc_pulse = 0.0
        self._last_rev_pulse = 0.0
        self._last_lock_pulse = 0.0
        self._last_spin_pulse = 0.0
        self._last_slip_pulse = 0.0
        self._last_oversteer_pulse = 0.0
        self._last_susp_pulse = 0.0
        self._last_suspension = [0.0, 0.0, 0.0, 0.0]
        self._suspension_primed = False

        # Worker thread
        self._worker_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self):
        """Start the background haptic synthesis worker."""
        if self._running:
            return
        self._running = True
        self._suspension_primed = False
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._haptic_loop, daemon=True)
        self._worker_thread.start()
        logger.info("Haptic engine worker started")

    def stop(self):
        """Stop worker and zero all motor forces."""
        self._running = False
        self._suspension_primed = False
        self._stop_event.set()
        if self._worker_thread:
            self._worker_thread.join(timeout=0.5)
            self._worker_thread = None
        self._zero_forces()

    def _zero_forces(self):
        if self.device and self.device.connected:
            try:
                self.device.send_constant_force(0)
                self.device.send_handle_vibration(0, 0)
            except Exception:
                pass

    def zero_outputs(self):
        """Clear stuck motor outputs without stopping the worker.
        Stream-loss path: the loop keeps running, so just drop the levels
        it re-drives from and zero the hardware once."""
        with self._lock:
            self._pulse_active = False
            self._pulse_intensity = 0
            self._engine_vibration_level = 0
        self._zero_forces()

    def trigger_pulse(self, intensity_pct: int, duration_sec: float):
        """Request a high-priority vibration pulse (e.g. ABS, TC, Rev Limiter)."""
        now = time.time()
        bounded = max(10, min(100, int(intensity_pct)))
        with self._lock:
            # A weaker event must not dilute a stronger pulse already running.
            if self._pulse_active and now < self._pulse_end_time:
                self._pulse_intensity = max(self._pulse_intensity, bounded)
            else:
                self._pulse_intensity = bounded
            self._pulse_end_time = max(self._pulse_end_time, now + max(0.02, duration_sec))
            self._pulse_active = True

    def update_telemetry(self, rpm: int, max_rpm: int, abs_active: bool, tc_active: bool, speed_kmh: float = 0.0,
                         wheel_slip=(0.0, 0.0, 0.0, 0.0),
                         wheel_speed=(0.0, 0.0, 0.0, 0.0),
                         suspension=(0.0, 0.0, 0.0, 0.0),
                         steer_angle=0.0):
        """Process incoming telemetry frame and dispatch vibration effects."""
        if not self._running or not self.device or not self.device.connected:
            return

        now = time.time()
        effective_max = max(3000, max_rpm)
        rpm_ratio = max(0.0, min(1.0, rpm / effective_max))

        # 1. ABS Event
        if abs_active and self.settings.abs_enabled:
            duration_s = max(0.04, self.settings.abs_duration / 1000.0)
            if (now - self._last_abs_pulse) >= (duration_s * 0.9):
                self._last_abs_pulse = now
                intensity = max(10, min(100, self.settings.abs_strength * 10))
                self.trigger_pulse(intensity, duration_s)

        # 2. Traction Control (TC) Event
        if tc_active and self.settings.tc_enabled:
            duration_s = max(0.04, self.settings.tc_duration / 1000.0)
            if (now - self._last_tc_pulse) >= (duration_s * 0.9):
                self._last_tc_pulse = now
                intensity = max(10, min(100, self.settings.tc_strength * 10))
                self.trigger_pulse(intensity, duration_s)

        # 3. Rev Limiter Shudder
        rev_threshold_ratio = (self.settings.rev_threshold / 100.0)
        if self.settings.rev_enabled and rpm_ratio >= rev_threshold_ratio:
            if (now - self._last_rev_pulse) >= 0.06:
                self._last_rev_pulse = now
                intensity = max(10, min(100, self.settings.rev_strength * 10))
                self.trigger_pulse(intensity, 0.05)

        # 4. Wheel Lock (individual tire lockup during braking)
        if self.settings.wheel_lock_enabled and speed_kmh > 15.0:
            is_locked = any(s < -0.25 for s in wheel_slip)
            if is_locked and (now - self._last_lock_pulse) >= 0.08:
                self._last_lock_pulse = now
                intensity = max(10, min(100, self.settings.wheel_lock_strength * 10))
                self.trigger_pulse(intensity, 0.07)

        # 5. Wheel Spin (driven wheel loss of traction under power)
        if self.settings.wheel_spin_enabled and speed_kmh > 5.0:
            is_spinning = any(s > 0.30 for s in wheel_slip)
            if is_spinning and (now - self._last_spin_pulse) >= 0.08:
                self._last_spin_pulse = now
                intensity = max(10, min(100, self.settings.wheel_spin_strength * 10))
                self.trigger_pulse(intensity, 0.07)

        # 6. Understeer & Oversteer Slip Angle Vibration
        fl_slip, fr_slip, rl_slip, rr_slip = wheel_slip if len(wheel_slip) >= 4 else (0, 0, 0, 0)
        front_slip = max(abs(fl_slip), abs(fr_slip))
        rear_slip = max(abs(rl_slip), abs(rr_slip))

        # Evaluated independently: either end can step out regardless of the other.
        if self.settings.understeer_enabled and speed_kmh > 20.0 and abs(steer_angle) > 0.1:
            # Front tires scrubbing significantly more than rear
            if (front_slip - rear_slip) > 0.15 and (now - self._last_slip_pulse) >= 0.09:
                self._last_slip_pulse = now
                intensity = max(10, min(100, self.settings.understeer_strength * 10))
                self.trigger_pulse(intensity, 0.08)
        if self.settings.oversteer_enabled and speed_kmh > 20.0:
            # Rear tires stepping out
            if (rear_slip - front_slip) > 0.20 and (now - self._last_oversteer_pulse) >= 0.09:
                self._last_oversteer_pulse = now
                intensity = max(10, min(100, self.settings.oversteer_strength * 10))
                self.trigger_pulse(intensity, 0.08)

        # 7. Suspension Travel / Curb Strike Vibration
        if len(suspension) >= 4:
            if not self._suspension_primed:
                self._last_suspension = list(suspension)
                self._suspension_primed = True
            else:
                if self.settings.suspension_enabled:
                    susp_thresh = max(0.01, self.settings.suspension_threshold / 100.0)
                    deltas = [abs(curr - prev) for curr, prev in zip(suspension, self._last_suspension)]
                    if any(d > susp_thresh for d in deltas) and (now - self._last_susp_pulse) >= 0.08:
                        self._last_susp_pulse = now
                        intensity = max(10, min(100, self.settings.suspension_strength * 10))
                        self.trigger_pulse(intensity, 0.06)
                self._last_suspension = list(suspension)

        # 8. Engine Vibration baseline
        if self.settings.engine_enabled and rpm > 300:
            initial_thresh = (self.settings.engine_initial / 100.0)
            if rpm_ratio >= initial_thresh:
                scaled = (rpm_ratio - initial_thresh) / max(0.01, 1.0 - initial_thresh)
                self._engine_vibration_level = int(scaled * (self.settings.engine_strength * 6))
            else:
                self._engine_vibration_level = 0
        else:
            self._engine_vibration_level = 0

    def _haptic_loop(self):
        """
        Synthesizes 18 Hz symmetric alternating direct-drive torque pulses
        concurrently with peripheral handle/pedal vibration.
        """
        freq = 18
        half_period = (1.0 / freq) / 2.0  # ~27ms
        toggle_state = False
        was_active = False

        while not self._stop_event.is_set():
            now = time.time()
            active_intensity = 0

            with self._lock:
                if self._pulse_active:
                    if now < self._pulse_end_time:
                        active_intensity = self._pulse_intensity
                    else:
                        self._pulse_active = False
                        self._pulse_intensity = 0

            # If no active pulse, check continuous engine vibration
            if active_intensity == 0 and self._engine_vibration_level > 0:
                active_intensity = self._engine_vibration_level

            if active_intensity > 0 and self.device and self.device.connected:
                was_active = True
                # Direct drive torque amplitude
                amp = int((active_intensity / 100.0) * 5500)
                torque = amp if toggle_state else -amp
                toggle_state = not toggle_state

                # Pedal and handle rumble
                pedal_rumble = int((active_intensity / 100.0) * 255)

                try:
                    self.device.send_constant_force(torque)
                    self.device.send_handle_vibration(pedal_rumble, pedal_rumble)
                except Exception:
                    pass
                time.sleep(half_period)
            else:
                # Idle: zero forces ONCE upon transition from active, then sleep without USB chatter
                if was_active:
                    self._zero_forces()
                    was_active = False
                time.sleep(0.04)
