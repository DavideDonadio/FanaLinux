"""
DiRT Rally 2.0 & EA Sports WRC Telemetry Client for Linux.
Connects via Codemasters D-BOX / UDP extradata protocol (default port 20777).
"""

import logging
import struct
from collections.abc import Callable

from fanalinux.core.telemetry.base import UdpTelemetryClient

logger = logging.getLogger("fanalinux.telemetry.dirt")


class DirtRallyTelemetry(UdpTelemetryClient):
    UDP_IP = "127.0.0.1"
    UDP_PORT = 20777
    STREAM_LABEL = "DiRT / WRC UDP"
    RECV_SIZE = 512

    # Codemasters extradata=3 packet contains 64 single-precision floats (256 bytes)
    # Some revisions append 2 extra floats (264 bytes)
    STRUCT_FORMAT = "<64f"
    MIN_PACKET_SIZE = 256

    def __init__(self,
                 on_telemetry: Callable | None = None,
                 on_car_detected: Callable[[str], None] | None = None,
                 default_max_rpm: int = 7500,
                 port: int = 20777):
        super().__init__(on_telemetry=on_telemetry,
                         on_car_detected=on_car_detected,
                         default_max_rpm=default_max_rpm)
        self.UDP_PORT = port

    def process_packet(self, data: bytes):
        """Parse raw 64-float Codemasters packet and dispatch to listener."""
        try:
            floats = struct.unpack_from(self.STRUCT_FORMAT, data)

            # Speed: Index 7 is velocity in m/s
            speed_ms = floats[7]
            speed_kmh = max(0.0, float(speed_ms * 3.6))

            # RPM: Index 37 is RPM / 10
            rpm = max(0, int(floats[37] * 10.0))

            # Gear: Index 33 (0 = Neutral, 1-9 = Forward, >= 10 or < 0 = Reverse)
            raw_gear = int(floats[33])
            if raw_gear >= 10 or raw_gear < 0:
                gear = -1
            elif raw_gear == 0:
                gear = 0
            else:
                gear = raw_gear

            # Suspension travel (meters): FL (19), FR (20), RL (17), RR (18)
            suspension = (
                float(floats[19]),
                float(floats[20]),
                float(floats[17]),
                float(floats[18])
            )

            # Wheel speeds (m/s): RL (25), RR (26), FL (27), FR (28)
            wheel_speed = (
                float(floats[27]),
                float(floats[28]),
                float(floats[25]),
                float(floats[26])
            )

            # Steer angle: Index 30 is steering input [-1.0, 1.0]
            steer_angle = float(floats[30])

            # Inputs: Throttle (29), Brake (31)
            throttle = float(floats[29])
            brake = float(floats[31])

            # Derive signed wheel slip and detect brake lock / power spin
            abs_active = False
            tc_active = False
            if speed_ms > 1.0:
                # Signed slip: negative = locking, positive = spinning
                fl_slip = (wheel_speed[0] - speed_ms) / speed_ms
                fr_slip = (wheel_speed[1] - speed_ms) / speed_ms
                rl_slip = (wheel_speed[2] - speed_ms) / speed_ms
                rr_slip = (wheel_speed[3] - speed_ms) / speed_ms
                wheel_slip = (fl_slip, fr_slip, rl_slip, rr_slip)

                # Wheel lockup under braking: any tire slipping < -0.35
                if brake > 0.3 and any(s < -0.35 for s in wheel_slip):
                    abs_active = True

                # Driven wheel spin under acceleration: any tire slipping > 0.35
                if throttle > 0.4 and any(s > 0.35 for s in wheel_slip):
                    tc_active = True
            else:
                wheel_slip = (0.0, 0.0, 0.0, 0.0)

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
            return True
        except Exception as e:
            logger.error(f"Error parsing DiRT Rally packet: {e}")
