"""
isiMotor Pulse telemetry client for rFactor 2 and Le Mans Ultimate.

Reads the open-source isiMotor_Pulse plugin (Apache-2.0, not bundled:
installed from the game row on demand) over ZeroMQ TCP on localhost.
TelemInfo carries gear, RPM and speed at 60-100 Hz — the full dashboard,
rev LEDs included.

The third-party parsing lives in isimotor-pulse-client; this module only
translates TelemInfo into standard manager frames and owns the worker
lifecycle. The import is lazy so the app never breaks when the optional
dependency is missing.
"""

import logging
import time
import urllib.request
from collections.abc import Callable

from fanalinux.core.telemetry.base import BaseTelemetryClient

logger = logging.getLogger("fanalinux.telemetry.pulse")

from pathlib import Path

PULSE_DLL_CACHE = Path.home() / ".local" / "share" / "fanalinux" / "isiMotor_Pulse.dll"


class Redirected(Exception):
    def __init__(self, url: str):
        super().__init__(url)
        self.url = url


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise Redirected(newurl)


class PulseTelemetry(BaseTelemetryClient):
    def __init__(self,
                 on_telemetry: Callable | None = None,
                 on_car_detected: Callable[[str], None] | None = None,
                 default_max_rpm: int = 6500,
                 host: str = "127.0.0.1",
                 base_port: int = 5000,
                 poll_interval: float = 1.0 / 60.0):
        super().__init__(on_telemetry=on_telemetry,
                         on_car_detected=on_car_detected,
                         default_max_rpm=default_max_rpm)
        self._host = host
        self._base_port = base_port
        self._poll_interval = poll_interval
        self._client = None

    @staticmethod
    def is_available() -> bool:
        try:
            import isimotor_pulse_client  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def ensure_plugin_dll() -> Path:
        """Fetch the prebuilt plugin DLL once; cache it locally."""
        import zipfile
        if PULSE_DLL_CACHE.exists() and PULSE_DLL_CACHE.stat().st_size > 0:
            return PULSE_DLL_CACHE
        # Quota-free: follow the /latest redirect to learn the tag, then
        # build the asset URL (avoids the rate-limited releases API).
        latest_url = ("https://github.com/marcgardent/isiMotor-Pulse-Plugin"
                      "/releases/latest/download/isiMotor-Pulse-Plugin-")
        opener = urllib.request.build_opener(NoRedirect())
        try:
            opener.open("https://github.com/marcgardent/isiMotor-Pulse-Plugin"
                        "/releases/latest", timeout=20)
            raise RuntimeError("Could not resolve the latest isiMotor Pulse release.")
        except Redirected as redir:
            tag = redir.url.rstrip("/").rsplit("/", 1)[-1]
        asset_url = f"{latest_url}{tag}-Windows-x64-MinGW-w64.zip"
        tmp_zip = PULSE_DLL_CACHE.with_suffix(".zip")
        PULSE_DLL_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(asset_url, timeout=120) as resp, open(tmp_zip, "wb") as f:
            f.write(resp.read())
        with zipfile.ZipFile(tmp_zip) as zf:
            dll_names = [n for n in zf.namelist() if n.lower().endswith("isimotor_pulse.dll")]
            if not dll_names:
                raise RuntimeError("Downloaded archive contains no isiMotor_Pulse.dll.")
            with zf.open(dll_names[0]) as src, open(PULSE_DLL_CACHE, "wb") as f:
                f.write(src.read())
        try:
            tmp_zip.unlink()
        except OSError:
            pass
        return PULSE_DLL_CACHE

    def stop(self):
        super().stop()
        client, self._client = self._client, None
        if client is not None:
            try:
                client.stop()
            except Exception:
                pass
        self.is_connected = False

    def _worker(self):
        try:
            from isimotor_pulse_client import IsiMotorClient
        except ImportError:
            logger.error("isimotor-pulse-client not installed; Pulse telemetry unavailable")
            self._running = False
            return
        try:
            self._client = IsiMotorClient(host=self._host, base_port=self._base_port)
            self._client.start()
        except Exception as e:
            logger.error(f"Pulse client failed to start: {e}")
            self._running = False
            return
        logger.info(f"Pulse telemetry listening on {self._host}:{self._base_port} "
                    "(install the isiMotor Pulse plugin from the game row)")

        silent_for = 0.0
        while self._running:
            try:
                telem = self._client.get_latest_telemetry()
            except Exception as e:
                logger.debug(f"Pulse poll failed: {e}")
                telem = None
            if telem is not None:
                silent_for = 0.0
                if not self.is_connected:
                    self.is_connected = True
                    logger.info("Connected to Pulse telemetry stream")
                try:
                    gear = int(telem.gear)
                    rpm = int(telem.engine_rpm)
                    speed_kmh = float(telem.forward_speed_kmh)
                    ecu = getattr(telem, "ecu", None)
                    abs_active = bool(getattr(ecu, "abs_active", False))
                    tc_active = bool(getattr(ecu, "tc_active", False))
                    if -1 <= gear <= 8 and rpm >= 0:
                        self._dispatch_telemetry(rpm, gear, speed_kmh, abs_active, tc_active)
                except Exception as e:
                    logger.debug(f"Pulse frame rejected: {e}")
            else:
                silent_for += self._poll_interval
                if self.is_connected and silent_for > 4.0:
                    self.is_connected = False
            time.sleep(self._poll_interval)
