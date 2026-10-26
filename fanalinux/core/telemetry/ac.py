"""
Assetto Corsa Telemetry Client for Linux.

Connects directly to Assetto Corsa's native UDP remote telemetry server (port 9996)
to stream RPM, gear, speed, ABS, and TC events in real time.
"""

import logging
import select
import socket
import struct
from collections.abc import Callable

from fanalinux.core.telemetry.base import BaseTelemetryClient

logger = logging.getLogger("fanalinux.telemetry.ac")


def parse_ac_packet(data: bytes) -> dict | None:
    """Parse an Assetto Corsa RTCarUpdate packet (328-388 bytes, starts with 'a').
    Returns the telemetry fields or None for anything else. Pure: no I/O."""
    if not data or not (320 <= len(data) <= 400 and data[0] == ord('a')):
        return None
    try:
        return {
            "speed_kmh": float(struct.unpack("<f", data[8:12])[0]),
            "abs_active": bool(data[21]),
            "tc_active": bool(data[22]),
            "rpm": int(struct.unpack("<f", data[68:72])[0]),
            # Gear: 0 = R, 1 = N, 2 = 1st, 3 = 2nd...
            "gear": int.from_bytes(data[76:80], byteorder="little") - 1,
            "steer_angle": float(struct.unpack_from("<f", data, 24)[0]),
            "wheel_slip": tuple(struct.unpack_from("<4f", data, 56)),
            "wheel_speed": tuple(struct.unpack_from("<4f", data, 104)),
            "suspension": tuple(struct.unpack_from("<4f", data, 184)),
        }
    except Exception:
        return None


class AssettoCorsaTelemetry(BaseTelemetryClient):
    UDP_IP = "127.0.0.1"
    UDP_PORT = 9996

    HANDSHAKE = 0
    SUBSCRIBE_UPDATE = 1
    SUBSCRIBE_SPOT = 2
    DISMISS = 3

    def __init__(self,
                 on_telemetry: Callable | None = None,
                 on_car_detected: Callable[[str], None] | None = None,
                 default_max_rpm: int = 6500):
        super().__init__(on_telemetry=on_telemetry,
                         on_car_detected=on_car_detected,
                         default_max_rpm=default_max_rpm)
        self._sock: socket.socket | None = None

    def stop(self):
        """Stop telemetry thread and send dismiss packet."""
        if self._sock:
            try:
                self._send_command(self.DISMISS)
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        super().stop()

    def _send_command(self, operation: int):
        if not self._sock:
            return
        payload = bytearray([
            0x00, 0x00, 0x00, 0x02,  # Identifier
            0x00, 0x00, 0x00, 0x00,  # Version
            operation, 0x00, 0x00, 0x00  # Operation ID
        ])
        try:
            self._sock.sendto(payload, (self.UDP_IP, self.UDP_PORT))
        except Exception:
            pass

    def _worker(self):
        while self._running:
            try:
                self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._sock.setblocking(False)

                # Attempt handshake loop
                while self._running:
                    self._send_command(self.HANDSHAKE)
                    r, _, _ = select.select([self._sock], [], [], 1.5)
                    if r:
                        resp = self._sock.recv(2048)
                        if len(resp) >= 50:
                            car_str = resp[:50].decode('utf-8', errors='ignore').strip('\x00').replace('\x00', '')
                            if car_str:
                                self.car_name = car_str
                                logger.info(f"Connected to Assetto Corsa session: Car={self.car_name}")
                                if self.on_car_detected:
                                    self.on_car_detected(self.car_name)
                        self._send_command(self.SUBSCRIBE_UPDATE)
                        self.is_connected = True
                        break
                    self._stop_event.wait(1.0)

                # Stream packets loop
                timeout_count = 0
                while self._running and self.is_connected:
                    r, _, _ = select.select([self._sock], [], [], 0.5)
                    if not r:
                        timeout_count += 1
                        if timeout_count > 6:
                            logger.info("Assetto Corsa session ended or timed out")
                            self.is_connected = False
                            break
                        continue

                    timeout_count = 0
                    data = self._sock.recv(2048)
                    parsed = parse_ac_packet(data)
                    if parsed is not None:
                        self._dispatch_telemetry(
                            parsed["rpm"], parsed["gear"], parsed["speed_kmh"],
                            parsed["abs_active"], parsed["tc_active"],
                            wheel_slip=parsed["wheel_slip"],
                            wheel_speed=parsed["wheel_speed"],
                            suspension=parsed["suspension"],
                            steer_angle=parsed["steer_angle"]
                        )

            except Exception as e:
                if self._running:
                    logger.debug(f"Telemetry socket reconnecting: {e}")
                self.is_connected = False
                self._stop_event.wait(2.0)
            finally:
                if self._sock:
                    try:
                        self._sock.close()
                    except Exception:
                        pass
                    self._sock = None
