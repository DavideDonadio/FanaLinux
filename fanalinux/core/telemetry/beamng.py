"""
BeamNG.drive Telemetry Client for Linux.
Connects via native OutGauge UDP protocol (default port 4444).
"""

import logging
import struct
from collections.abc import Callable

from fanalinux.core.telemetry.base import UdpTelemetryClient

logger = logging.getLogger("fanalinux.telemetry.beamng")


class BeamNGTelemetry(UdpTelemetryClient):
    UDP_IP = "127.0.0.1"
    UDP_PORT = 4444
    STREAM_LABEL = "BeamNG OutGauge"
    RECV_SIZE = 512

    # OutGauge packet: 92 bytes base (without trailing optional id)
    # I: time (4)
    # 4s: car (4)
    # H: flags (2)
    # b: gear (1)
    # b: plid (1)
    # 7f: speed(f), rpm(f), turbo(f), engTemp(f), fuel(f), oilPressure(f), oilTemp(f)
    # 2I: dashLights(I), showLights(I)
    # 3f: throttle(f), brake(f), clutch(f)
    # 16s: display1(16)
    # 16s: display2(16)
    OUTGAUGE_FORMAT = "<I 4s H b b 7f 2I 3f 16s 16s"
    MIN_PACKET_SIZE = 92

    # showLights bitmasks
    DL_TC = 1 << 4    # 16
    DL_ABS = 1 << 10  # 1024

    def __init__(self,
                 on_telemetry: Callable | None = None,
                 on_car_detected: Callable[[str], None] | None = None,
                 default_max_rpm: int = 6500,
                 port: int = 4444):
        super().__init__(on_telemetry=on_telemetry,
                         on_car_detected=on_car_detected,
                         default_max_rpm=default_max_rpm)
        self.UDP_PORT = port

    def process_packet(self, data: bytes):
        """Parse raw OutGauge binary packet and dispatch to listener."""
        try:
            fields = struct.unpack_from(self.OUTGAUGE_FORMAT, data)
            raw_car = fields[1].decode("ascii", errors="ignore").strip("\x00")
            if raw_car and raw_car != self.car_name:
                self.car_name = raw_car
                if self.on_car_detected:
                    self.on_car_detected(self.car_name)

            raw_gear = fields[3]
            # OutGauge: 0=R, 1=N, 2=1st, 3=2nd ...
            gear = raw_gear - 1

            speed_ms = fields[5]
            speed_kmh = max(0.0, float(speed_ms * 3.6))
            rpm = max(0, int(fields[6]))

            show_lights = fields[13]
            abs_active = bool(show_lights & self.DL_ABS)
            tc_active = bool(show_lights & self.DL_TC)

            self._dispatch_telemetry(
                rpm=rpm,
                gear=gear,
                speed_kmh=speed_kmh,
                abs_active=abs_active,
                tc_active=tc_active
            )
        except Exception as e:
            logger.error(f"Error parsing BeamNG packet: {e}")
