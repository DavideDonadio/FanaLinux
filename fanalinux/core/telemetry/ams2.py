"""
Automobilista 2 (AMS2) & Project CARS 2 Telemetry Client for Linux.
Connects via native Project CARS 2 UDP protocol (default port 5606).
"""

import logging
import struct
from collections.abc import Callable

from fanalinux.core.telemetry.base import UdpTelemetryClient

logger = logging.getLogger("fanalinux.telemetry.ams2")


class AMS2Telemetry(UdpTelemetryClient):
    """
    Automobilista 2 / Project CARS 2 UDP receiver.
    Listens for eCarPhysics packets (mPacketType == 0).
    """
    # Bind 0.0.0.0 to permit LAN / console forwarding from external rigs
    UDP_IP = "0.0.0.0"
    UDP_PORT = 5606
    STREAM_LABEL = "AMS2 UDP"

    HEADER_SIZE = 12
    HEADER_FORMAT = "<IIBBBB"
    # Worker dispatch gate; full eCarPhysics packets are CAR_PHYSICS_SIZE.
    MIN_PACKET_SIZE = HEADER_SIZE
    # sTelemetryData (eCarPhysics) packet size in Project CARS 2 / AMS2 spec
    CAR_PHYSICS_SIZE = 556

    # CarFlags bitmask constants
    CAR_HEADLIGHT = 1 << 0
    CAR_ENGINE_ACTIVE = 1 << 1
    CAR_ENGINE_WARNING = 1 << 2
    CAR_SPEED_LIMITER = 1 << 3
    CAR_ABS = 1 << 4
    CAR_HANDBRAKE = 1 << 5
    CAR_TCS = 1 << 6
    CAR_SCS = 1 << 7

    def __init__(self,
                 on_telemetry: Callable | None = None,
                 on_car_detected: Callable[[str], None] | None = None,
                 default_max_rpm: int = 8000,
                 port: int = 5606):
        super().__init__(on_telemetry=on_telemetry,
                         on_car_detected=on_car_detected,
                         default_max_rpm=default_max_rpm)
        self.UDP_PORT = port

    def process_packet(self, data: bytes):
        """
        Parse raw AMS2 / PCars2 UDP packet and dispatch to listener.
        Header:
          0: u32 mPacketNumber
          4: u32 mCategoryPacketNumber
          8: u8  mPartialPacketIndex
          9: u8  mPartialPacketNumber
         10: u8  mPacketType (0 = eCarPhysics)
         11: u8  mPacketVersion
        """
        try:
            if len(data) < self.HEADER_SIZE:
                return

            p_num, cat_num, p_idx, p_total, packet_type, p_ver = struct.unpack_from(self.HEADER_FORMAT, data, 0)

            # Only eCarPhysics (packet_type == 0) contains live vehicle telemetry
            if packet_type != 0 or len(data) < self.CAR_PHYSICS_SIZE:
                return

            # Car state & Flags
            car_flags = struct.unpack_from("<B", data, 17)[0]
            abs_active = bool(car_flags & self.CAR_ABS)
            tc_active = bool(car_flags & self.CAR_TCS)

            # Core physics
            speed_ms = struct.unpack_from("<f", data, 36)[0]
            speed_kmh = max(0.0, float(speed_ms * 3.6))

            rpm, max_rpm = struct.unpack_from("<HH", data, 40)
            if max_rpm > 1000:
                self.max_rpm = int(max_rpm)

            raw_steer = struct.unpack_from("<b", data, 44)[0]
            steer_angle = float(raw_steer) / 127.0

            gear_byte = struct.unpack_from("<B", data, 45)[0]
            raw_gear = gear_byte & 0x0F
            if raw_gear == 15:
                gear = -1
            elif raw_gear == 0:
                gear = 0
            else:
                gear = raw_gear

            # Tyre angular velocity (rad/s): FL, FR, RL, RR at offset 160
            ws = struct.unpack_from("<4f", data, 160)
            wheel_speed = (float(ws[0]), float(ws[1]), float(ws[2]), float(ws[3]))

            # Suspension travel: FL, FR, RL, RR at offset 312
            susp = struct.unpack_from("<4f", data, 312)
            suspension = (float(susp[0]), float(susp[1]), float(susp[2]), float(susp[3]))

            # Derive approximate slip if wheel speed and linear speed are known
            if speed_ms > 1.0:
                # Estimate tire linear speed from RPS with a typical tire radius ~0.33m
                r = 0.33
                wheel_slip = (
                    (ws[0] * r - speed_ms) / speed_ms,
                    (ws[1] * r - speed_ms) / speed_ms,
                    (ws[2] * r - speed_ms) / speed_ms,
                    (ws[3] * r - speed_ms) / speed_ms,
                )
            else:
                wheel_slip = (0.0, 0.0, 0.0, 0.0)

            self._dispatch_telemetry(
                rpm=int(rpm),
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
            logger.error(f"Error parsing AMS2 packet: {e}")
