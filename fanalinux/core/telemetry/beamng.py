"""
BeamNG.drive Telemetry Client for Linux.
Connects via native OutGauge UDP protocol (default port 4444).
"""

import socket
import select
import struct
import time
import logging
from typing import Callable, Optional
from fanalinux.core.telemetry.base import BaseTelemetryClient

logger = logging.getLogger("fanalinux.telemetry.beamng")


class BeamNGTelemetry(BaseTelemetryClient):
    UDP_IP = "127.0.0.1"
    UDP_PORT = 4444

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
                 on_telemetry: Optional[Callable] = None,
                 on_car_detected: Optional[Callable[[str], None]] = None,
                 default_max_rpm: int = 6500,
                 port: int = 4444):
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
                logger.info(f"Listening for BeamNG OutGauge telemetry on {self.UDP_IP}:{self.UDP_PORT}")

                timeout_count = 0
                while self._running:
                    r, _, _ = select.select([self._sock], [], [], 0.5)
                    if not r:
                        if self.is_connected:
                            timeout_count += 1
                            if timeout_count > 6:
                                logger.info("BeamNG OutGauge telemetry stream timed out")
                                self.is_connected = False
                        continue

                    timeout_count = 0
                    data, _ = self._sock.recvfrom(512)
                    if len(data) >= self.MIN_PACKET_SIZE:
                        if not self.is_connected:
                            self.is_connected = True
                            logger.info("Connected to BeamNG OutGauge telemetry stream")

                        self.process_packet(data)

            except Exception as e:
                if self._running:
                    logger.debug(f"BeamNG telemetry socket error: {e}")
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
