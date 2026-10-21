"""
Forza Motorsport & Forza Horizon Telemetry Client for Linux.
Connects via Turn 10 / Playground Games "Data Out" UDP protocol (default port 5300).
Supports Forza Motorsport (2023 / FM7) and Forza Horizon 4 / 5.
"""

import socket
import select
import struct
import time
import logging
from typing import Callable, Optional
from fanalinux.core.telemetry.base import BaseTelemetryClient

logger = logging.getLogger("fanalinux.telemetry.forza")


class ForzaTelemetry(BaseTelemetryClient):
    """
    Forza 'Data Out' UDP receiver.
    Listens for Dash (Car Dash) 324-byte packets.
    """
    UDP_IP = "127.0.0.1"
    UDP_PORT = 5300

    # Minimum packet length for Forza 'Car Dash' packet format
    MIN_PACKET_SIZE = 311
    DASH_PACKET_SIZE = 324

    def __init__(self,
                 on_telemetry: Optional[Callable] = None,
                 on_car_detected: Optional[Callable[[str], None]] = None,
                 default_max_rpm: int = 7000,
                 port: int = 5300):
        super().__init__(on_telemetry=on_telemetry,
                         on_car_detected=on_car_detected,
                         default_max_rpm=default_max_rpm)
        self.UDP_PORT = port
        self._sock: Optional[socket.socket] = None

    def stop(self):
        super().stop()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def _worker(self):
        while self._running:
            try:
                self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._sock.bind((self.UDP_IP, self.UDP_PORT))
                self._sock.setblocking(False)
                logger.info(f"Listening for Forza UDP telemetry on {self.UDP_IP}:{self.UDP_PORT}")

                timeout_count = 0
                while self._running:
                    r, _, _ = select.select([self._sock], [], [], 0.5)
                    if not r:
                        if self.is_connected:
                            timeout_count += 1
                            if timeout_count > 6:
                                logger.info("Forza telemetry stream timed out")
                                self.is_connected = False
                        continue

                    timeout_count = 0
                    data, _ = self._sock.recvfrom(1024)
                    if len(data) >= self.MIN_PACKET_SIZE:
                        if not self.is_connected:
                            self.is_connected = True
                            logger.info(f"Connected to Forza telemetry stream ({len(data)} bytes)")

                        self.process_packet(data)

            except Exception as e:
                if self._running:
                    logger.debug(f"Forza telemetry socket error: {e}")
                self.is_connected = False
                time.sleep(2.0)
            finally:
                if self._sock:
                    try:
                        self._sock.close()
                    except Exception:
                        pass
                    self._sock = None

    def process_packet(self, data: bytes):
        """
        Parse raw Forza 'Data Out' packet and dispatch to listener.
        Standard layout:
          0: s32 IsRaceOn
          4: u32 TimestampMS
          8: f32 EngineMaxRpm
         12: f32 EngineIdleRpm
         16: f32 CurrentEngineRpm
         68-84: f32 NormalizedSuspensionTravel FL, FR, RL, RR
         84-100: f32 TireSlipRatio FL, FR, RL, RR
         100-116: f32 WheelRotationSpeed FL, FR, RL, RR
         256: f32 Speed (m/s)
         312: u8 Gear (0 = Reverse, 1 = Neutral, 2 = 1st, 3 = 2nd...)
         313: s8 Steering (-127 to 127)
         314: u8 Throttle (0 to 255)
         315: u8 Brake (0 to 255)
         316: u8 Clutch (0 to 255)
        """
        try:
            if len(data) < self.MIN_PACKET_SIZE:
                return

            # Header & Engine block (first 20 bytes)
            is_race_on, timestamp_ms, engine_max_rpm, engine_idle_rpm, current_engine_rpm = struct.unpack_from(
                "<iI3f", data, 0
            )

            # Update redline dynamically if valid
            if engine_max_rpm > 1000.0:
                self.max_rpm = int(engine_max_rpm)

            rpm = max(0, int(current_engine_rpm))

            # If race is not on (e.g. paused / menus), suppress output
            if not is_race_on:
                self._dispatch_telemetry(
                    rpm=0,
                    gear=0,
                    speed_kmh=0.0,
                    abs_active=False,
                    tc_active=False
                )
                return

            # Suspension travel FL, FR, RL, RR at offset 68
            susp_fl, susp_fr, susp_rl, susp_rr = struct.unpack_from("<4f", data, 68)
            suspension = (float(susp_fl), float(susp_fr), float(susp_rl), float(susp_rr))

            # Tire slip ratio FL, FR, RL, RR at offset 84
            # Slip ratio: 0 = full grip, negative = brake lock/slip, positive = drive spin
            slip_fl, slip_fr, slip_rl, slip_rr = struct.unpack_from("<4f", data, 84)
            wheel_slip = (float(slip_fl), float(slip_fr), float(slip_rl), float(slip_rr))

            # Wheel rotation speed FL, FR, RL, RR (rad/s) at offset 100
            ws_fl, ws_fr, ws_rl, ws_rr = struct.unpack_from("<4f", data, 100)
            wheel_speed = (float(ws_fl), float(ws_fr), float(ws_rl), float(ws_rr))

            # Speed at offset 256 (m/s)
            speed_ms = struct.unpack_from("<f", data, 256)[0]
            speed_kmh = max(0.0, float(speed_ms * 3.6))

            # Gear and inputs at offset 312
            raw_gear, raw_steer, raw_throttle, raw_brake = struct.unpack_from("<BbBB", data, 312)

            # Gear mapping: 0 = Reverse (-1), 1 = Neutral (0), 2 = 1st (1), 3 = 2nd (2)...
            if raw_gear == 0:
                gear = -1
            elif raw_gear == 1:
                gear = 0
            else:
                gear = raw_gear - 1

            steer_angle = float(raw_steer) / 127.0
            throttle = float(raw_throttle) / 255.0
            brake = float(raw_brake) / 255.0

            # Derive ABS and TC states from slip ratios and driver inputs
            abs_active = False
            tc_active = False

            if speed_kmh > 5.0:
                # Brake lockup: braking hard and any wheel slip magnitude exceeds lock threshold
                # In Forza slip ratio is normalized: ~1.0 means 100% slip
                if brake > 0.25 and any(abs(s) > 0.35 for s in wheel_slip):
                    abs_active = True

                # Traction loss: throttle applied and driven wheels spinning significantly
                if throttle > 0.35 and any(s > 0.40 for s in wheel_slip[2:]):  # rear wheels or all
                    tc_active = True

            self._dispatch_telemetry(
                rpm=rpm,
                gear=gear,
                speed_kmh=speed_kmh,
                abs_active=abs_active,
                tc_active=tc_active,
                wheel_slip=wheel_slip,
                wheel_speed=wheel_speed,
                suspension=suspension,
                steer_angle=steer_angle
            )
        except Exception as e:
            logger.error(f"Error parsing Forza packet: {e}")
