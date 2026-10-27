"""
Forza Motorsport & Forza Horizon Telemetry Client for Linux.
Connects via Turn 10 / Playground Games "Data Out" UDP protocol (default port 5300).
Supports Forza Motorsport (2023 / FM7) and Forza Horizon 4 / 5.
"""

import logging
import struct
from collections.abc import Callable

from fanalinux.core.telemetry.base import UdpTelemetryClient

logger = logging.getLogger("fanalinux.telemetry.forza")


class ForzaTelemetry(UdpTelemetryClient):
    """
    Forza 'Data Out' UDP receiver.
    Listens for Dash (Car Dash) 324-byte packets.
    """
    UDP_IP = "127.0.0.1"
    UDP_PORT = 5300
    UDP_PORT = 5300
    STREAM_LABEL = "Forza UDP"
    RECV_SIZE = 1024

    # Minimum packet lengths for Forza 'Car Dash' packet format:
    # - 311 bytes: Forza Motorsport 7 Dash format
    # - 324 bytes: Forza Horizon 4/5 & Forza Motorsport (2023) Dash format
    MIN_PACKET_SIZE = 311
    FM7_PACKET_SIZE = 311
    DASH_PACKET_SIZE = 324
    SLED_PACKET_SIZE = 232

    def __init__(self,
                 on_telemetry: Callable | None = None,
                 on_car_detected: Callable[[str], None] | None = None,
                 default_max_rpm: int = 7000,
                 port: int = 5300):
        super().__init__(on_telemetry=on_telemetry,
                         on_car_detected=on_car_detected,
                         default_max_rpm=default_max_rpm)
        self.UDP_PORT = port
        self._sled_warned = False

    def _handle_short_packet(self, data: bytes):
        if len(data) == self.SLED_PACKET_SIZE and not self._sled_warned:
            logger.warning(
                "Received 232-byte Forza 'Sled' packet. "
                "Please change Data Out Packet Format to 'Dash' or 'Car Dash' in game settings."
            )
            self._sled_warned = True

    def process_packet(self, data: bytes):
        """
        Parse raw Forza 'Data Out' packet and dispatch to listener.
        Supports both:
          - FM7 311-byte layout (speed at 244, inputs at 307)
          - FH4/FH5/FM2023 324-byte layout (speed at 256, inputs at 312)
        """
        try:
            pkt_len = len(data)
            if pkt_len < self.MIN_PACKET_SIZE:
                return

            # Header & Engine block (first 20 bytes, shared by all Dash variants)
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

            # Branch offsets by packet version:
            # - FM7 Dash format: 311 bytes (speed at 244, gear at 307, steer at 308)
            # - FH4 / FH5 / FM2023 Car Dash format: >= 324 bytes (speed at 256, gear at 312, steer at 313)
            if pkt_len >= self.DASH_PACKET_SIZE:
                speed_ms = struct.unpack_from("<f", data, 256)[0]
                raw_gear, raw_steer, raw_throttle, raw_brake = struct.unpack_from("<BbBB", data, 312)
            else:
                speed_ms = struct.unpack_from("<f", data, 244)[0]
                raw_gear, raw_steer, raw_throttle, raw_brake = struct.unpack_from("<BbBB", data, 307)

            speed_kmh = max(0.0, float(speed_ms * 3.6))

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
