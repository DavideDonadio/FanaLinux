"""
EA Sports / Codemasters F1 Series Telemetry Client for Linux.
Connects via Codemasters F1 UDP protocol (port 20777).
Compatible with F1 2020 through F1 25.
"""

import logging
import struct
from collections.abc import Callable

from fanalinux.core.telemetry.base import UdpTelemetryClient

logger = logging.getLogger("fanalinux.telemetry.f1")


class F1Telemetry(UdpTelemetryClient):
    UDP_IP = "127.0.0.1"
    UDP_PORT = 20777
    STREAM_LABEL = "F1"
    MIN_PACKET_SIZE = 24

    # Packet IDs
    PACKET_ID_CAR_TELEMETRY = 6
    PACKET_ID_CAR_STATUS = 7

    def __init__(self,
                 on_telemetry: Callable | None = None,
                 on_car_detected: Callable[[str], None] | None = None,
                 default_max_rpm: int = 13500,
                 port: int = 20777):
        super().__init__(on_telemetry=on_telemetry,
                         on_car_detected=on_car_detected,
                         default_max_rpm=default_max_rpm)
        self.UDP_PORT = port
        self._last_abs = False
        self._last_tc = False

    def process_packet(self, data: bytes):
        """Parse F1 UDP packet header and route payload."""
        try:
            # Common Header:
            # H: m_packetFormat (e.g. 2020..2024)
            # B: m_gameYear (in 2023+) or m_gameMajorVersion
            # B: m_gameMajorVersion / m_gameMinorVersion
            # B: m_gameMinorVersion / m_packetVersion
            # B: m_packetVersion
            # B: m_packetId (byte 5 or 6 depending on header format)
            packet_format = struct.unpack_from("<H", data, 0)[0]
            if packet_format < 2018 or packet_format > 2030:
                return

            # In F1 2020..2022 header size is 24 bytes, 2023+ is 29 bytes
            # Packet ID is at byte offset 5 or 6
            if packet_format >= 2023:
                header_size = 29
                packet_id = data[6]
                player_car_index = data[27] if len(data) > 27 else 0
            else:
                header_size = 24
                packet_id = data[5]
                player_car_index = data[22] if len(data) > 22 else 0

            if player_car_index > 21:
                player_car_index = 0

            # Packet 6: Car Telemetry
            if packet_id == self.PACKET_ID_CAR_TELEMETRY:
                # Dynamic telemetry stride calculation
                remaining = len(data) - header_size
                entry_size = max(60, remaining // 22)
                offset = header_size + (player_car_index * entry_size)
                if len(data) >= offset + 18:
                    speed_kmh = float(struct.unpack_from("<H", data, offset)[0])
                    # offset + 2: throttle (f, 4 bytes)
                    steer = float(struct.unpack_from("<f", data, offset + 6)[0])
                    # offset + 10: brake (f, 4 bytes)
                    # offset + 14: clutch (uint8)
                    # offset + 15: gear (int8)
                    gear = int(struct.unpack_from("<b", data, offset + 15)[0])
                    engine_rpm = int(struct.unpack_from("<H", data, offset + 16)[0])

                    self._dispatch_telemetry(
                        rpm=engine_rpm,
                        gear=gear,
                        speed_kmh=speed_kmh,
                        abs_active=self._last_abs,
                        tc_active=self._last_tc,
                        steer_angle=steer
                    )

            # Packet 7: Car Status
            elif packet_id == self.PACKET_ID_CAR_STATUS:
                # Dynamic status stride: remaining // 22 (adapts automatically to 2020..2024 layouts)
                remaining = len(data) - header_size
                entry_size = max(45, remaining // 22)
                offset = header_size + (player_car_index * entry_size)
                if len(data) >= offset + 19:
                    tc_val = data[offset]
                    abs_val = data[offset + 1]
                    self._last_tc = bool(tc_val > 0)
                    self._last_abs = bool(abs_val > 0)
                    # maxRPM offset is byte 17 across all packed layouts
                    try:
                        max_rpm = struct.unpack_from("<H", data, offset + 17)[0]
                        if 8000 <= max_rpm <= 18000:
                            self.max_rpm = max_rpm
                    except Exception:
                        pass

        except Exception as e:
            logger.debug(f"Error parsing F1 packet: {e}")
