"""
Assetto Corsa Telemetry Client for Linux.

Connects directly to Assetto Corsa's native UDP remote telemetry server (port 9996)
to stream RPM, gear, speed, ABS, and TC events in real time.
"""

import socket
import struct
import select
import threading
import time
import logging
from typing import Callable, Optional

logger = logging.getLogger("fanactrl.telemetry.ac")


class AssettoCorsaTelemetry:
    UDP_IP = "127.0.0.1"
    UDP_PORT = 9996

    HANDSHAKE = 0
    SUBSCRIBE_UPDATE = 1
    SUBSCRIBE_SPOT = 2
    DISMISS = 3

    def __init__(self,
                 on_telemetry: Optional[Callable[[int, int, float, bool, bool], None]] = None,
                 on_car_detected: Optional[Callable[[str], None]] = None,
                 default_max_rpm: int = 6500):
        """
        on_telemetry callback: (rpm, gear, speed_kmh, abs_active, tc_active)
        """
        self.on_telemetry = on_telemetry
        self.on_car_detected = on_car_detected
        self.default_max_rpm = default_max_rpm
        self.max_rpm = default_max_rpm
        self.car_name = "Unknown"
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None
        self.is_connected = False

    def start(self):
        """Start the background telemetry polling thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        logger.info("Assetto Corsa telemetry thread started")

    def stop(self):
        """Stop telemetry thread and send dismiss packet."""
        self._running = False
        if self._sock:
            try:
                self._send_command(self.DISMISS)
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        self.is_connected = False

    def _send_command(self, operation: int):
        if not self._sock:
            return
        payload = bytearray([
            0x00, 0x00, 0x00, 0x02,  # Identifier
            0x00, 0x00, 0x00, 0x00,  # Version
            operation, 0x00, 0x00, 0x00  # Operation ID
        ])
        self._sock.sendto(payload, (self.UDP_IP, self.UDP_PORT))

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
                    time.sleep(1.0)

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
                    if len(data) >= 80:
                        speed_kmh = float(struct.unpack("<f", data[8:12])[0])
                        abs_active = bool(data[21])
                        tc_active = bool(data[22])
                        rpm = int(struct.unpack("<f", data[68:72])[0])
                        raw_gear = int.from_bytes(data[76:80], byteorder="little")
                        # Gear: 0 = R, 1 = N, 2 = 1st, 3 = 2nd...
                        gear = raw_gear - 1

                        if self.on_telemetry:
                            self.on_telemetry(rpm, gear, speed_kmh, abs_active, tc_active)

            except Exception as e:
                if self._running:
                    logger.debug(f"Telemetry socket reconnecting: {e}")
                self.is_connected = False
                time.sleep(2.0)
            finally:
                if self._sock:
                    try:
                        self._sock.close()
                    except Exception:
                        pass
                    self._sock = None
