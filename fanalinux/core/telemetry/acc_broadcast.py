"""
Assetto Corsa Competizione Broadcast Telemetry Client for Linux.

Speaks the Kunos ACC Broadcasting UDP protocol (the same pipe SimHub and
CrewChief use on Windows): register once on the game's listener port
(default 127.0.0.1:9000, configured in the game's broadcasting.json),
then parse realtime car updates into standard telemetry frames.

Protocol ground truth: ACC SDK BroadcastingNetworkProtocol.cs
(<game>/SDK/Broadcasting/Testclient). Strings are uint16-length-prefixed
UTF-8, everything little-endian.

Known protocol limit (by design, not a bug here): the broadcast feed
carries gear, speed, position and lap timing only. RPM, pedals and tyre
data exist solely in Windows shared memory (acpmf_physics), which is
invisible to Linux processes under Proton. So rpm is dispatched as 0:
the OLED shows gear/speed, the rev LEDs stay dark. Honest, not broken.
"""

import logging
import select
import socket
import struct
import time
from collections.abc import Callable

from fanalinux.core.telemetry.base import BaseTelemetryClient

logger = logging.getLogger("fanalinux.telemetry.acc")


def _pack_string(s: str) -> bytes:
    raw = s.encode("utf-8")
    return struct.pack("<H", len(raw)) + raw


class ACCBroadcastTelemetry(BaseTelemetryClient):
    # Outbound (client -> game)
    MSG_REGISTER = 1
    MSG_UNREGISTER = 9
    MSG_REQUEST_ENTRY_LIST = 10
    MSG_REQUEST_TRACK_DATA = 11
    # Inbound (game -> client)
    MSG_REGISTRATION_RESULT = 1
    MSG_REALTIME_UPDATE = 2
    MSG_REALTIME_CAR_UPDATE = 3

    PROTOCOL_VERSION = 2

    def __init__(self,
                 on_telemetry: Callable | None = None,
                 on_car_detected: Callable[[str], None] | None = None,
                 default_max_rpm: int = 6500,
                 host: str = "127.0.0.1",
                 port: int = 9000,
                 display_name: str = "FanaLinux",
                 connection_password: str = "asd",
                 command_password: str = "",
                 update_interval_ms: int = 50):
        super().__init__(on_telemetry=on_telemetry,
                         on_car_detected=on_car_detected,
                         default_max_rpm=default_max_rpm)
        self._target = (host, port)
        self._display_name = display_name
        self._connection_password = connection_password
        self._command_password = command_password
        self._interval_ms = update_interval_ms
        self._sock: socket.socket | None = None
        self._connection_id: int | None = None
        self._focused_car: int | None = None
        self._latched_car: int | None = None
        self._last_rx = 0.0
        self._last_register_at = 0.0

    def stop(self):
        self._unregister()
        super().stop()
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self.is_connected = False
        self._connection_id = None

    def _register(self):
        pkt = (struct.pack("<BB", self.MSG_REGISTER, self.PROTOCOL_VERSION)
               + _pack_string(self._display_name)
               + _pack_string(self._connection_password)
               + struct.pack("<i", self._interval_ms)
               + _pack_string(self._command_password))
        try:
            self._sock.sendto(pkt, self._target)
            self._last_register_at = time.monotonic()
        except OSError as e:
            logger.debug(f"ACC register send failed: {e}")

    def _unregister(self):
        if self._sock is not None and self._connection_id is not None:
            try:
                self._sock.sendto(struct.pack("<Bi", self.MSG_UNREGISTER, self._connection_id),
                                  self._target)
            except OSError:
                pass

    def _handle_message(self, data: bytes):
        """Parse one inbound datagram; dispatch a frame if it is our car."""
        if len(data) < 2:
            return
        msg_type = data[0]
        self._last_rx = time.monotonic()

        if msg_type == self.MSG_REGISTRATION_RESULT:
            if len(data) < 7:
                return
            conn_id, success = struct.unpack_from("<iB", data, 1)
            if success:
                self._connection_id = conn_id
                self.is_connected = True
                logger.info(f"ACC broadcast connected (id={conn_id})")
                try:
                    self._sock.sendto(struct.pack("<Bi", self.MSG_REQUEST_ENTRY_LIST, conn_id),
                                      self._target)
                    self._sock.sendto(struct.pack("<Bi", self.MSG_REQUEST_TRACK_DATA, conn_id),
                                      self._target)
                except OSError:
                    pass
            else:
                logger.error("ACC rejected broadcast registration (check connectionPassword "
                             "in broadcasting.json)")
        elif msg_type == self.MSG_REALTIME_UPDATE:
            # FocusedCarIndex sits after event/session/type/phase/time/endtime.
            if len(data) >= 19:
                self._focused_car = struct.unpack_from("<i", data, 15)[0]
        elif msg_type == self.MSG_REALTIME_CAR_UPDATE:
            if len(data) < 21:
                return
            car_index, _driver, gear_raw = struct.unpack_from("<HHB", data, 1)
            speed_kmh = float(struct.unpack_from("<H", data, 19)[0])
            gear = int(gear_raw) - 2  # 0=R(-1), 1=N(0), 2+=forward
            if gear < -1 or gear > 8:
                return
            # Drive the focused car; latch the first one seen until told.
            if self._focused_car is not None and car_index != self._focused_car:
                return
            if self._latched_car is None:
                self._latched_car = car_index
            if car_index != self._latched_car:
                return
            self.is_connected = True
            # No RPM on this feed (shared-memory only): dispatch 0 so the
            # rev LEDs stay dark rather than show garbage.
            self._dispatch_telemetry(0, gear, speed_kmh, False, False)

    def _worker(self):
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.bind(("0.0.0.0", 0))  # Ephemeral port; game replies here.
            self._sock.setblocking(False)
        except OSError as e:
            logger.error(f"ACC broadcast socket failed: {e}")
            self._running = False
            return
        logger.info(f"ACC broadcast client targeting {self._target[0]}:{self._target[1]} "
                    "(enable broadcasting in the game's broadcasting.json)")
        self._register()

        while self._running:
            if self._connection_id is None and time.monotonic() - self._last_register_at > 5.0:
                self._register()
            r, _, _ = select.select([self._sock], [], [], 0.5)
            if not r:
                if self.is_connected and time.monotonic() - self._last_rx > 4.0:
                    self.is_connected = False
                continue
            try:
                data, _addr = self._sock.recvfrom(65535)
            except OSError:
                continue
            try:
                self._handle_message(data)
            except Exception as e:
                logger.debug(f"ACC packet parse failed: {e}")
