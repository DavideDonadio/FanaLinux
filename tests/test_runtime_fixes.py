"""Regression tests for review findings #3, #4, #5 (offline, no hardware)."""
import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestConnectReturnValue(unittest.TestCase):
    def test_init_failure_returns_false(self):
        """connect() must not report success when init disconnects internally."""
        from fanalinux.core.device import FanatecDevice
        dev = FanatecDevice()
        dev.find_hidraw_path = lambda: os.devnull

        def fatal_write(data):
            dev.disconnect()
            return 0

        dev.write_report = fatal_write
        self.assertFalse(dev.connect())
        self.assertFalse(dev.connected)


class TestSteeringNormalization(unittest.TestCase):
    def _listener(self, center, min_v, max_v):
        from fanalinux.core.evdev_listener import ABS_X, EV_ABS, EvdevListener
        l = EvdevListener()
        l.center_raw = center
        l._axis_ranges = {ABS_X: (min_v, max_v)}
        got = []
        l.on_steering = lambda norm, raw: got.append((norm, raw))
        l._process_event(EV_ABS, ABS_X, 65535)
        l._process_event(EV_ABS, ABS_X, 0)
        l._process_event(EV_ABS, ABS_X, center)
        return [n for n, _ in got]

    def test_symmetric_full_range(self):
        right, left, middle = self._listener(32768, 0, 65535)
        self.assertAlmostEqual(right, 1.0)
        self.assertAlmostEqual(left, -1.0)
        self.assertAlmostEqual(middle, 0.0)

    def test_off_center_no_early_clip(self):
        """Off-midpoint calibrated center must still reach +/-1.0 at the stops."""
        right, left, middle = self._listener(33768, 0, 65535)
        self.assertAlmostEqual(right, 1.0)
        self.assertAlmostEqual(left, -1.0)
        self.assertAlmostEqual(middle, 0.0)


class TestGameSwitchTelemetry(unittest.TestCase):
    def _window_with_fake_mgr(self):
        from gi.repository import Adw
        Adw.init()
        from fanalinux.ui.window import MainWindow
        win = MainWindow()
        calls = []

        class FakeMgr:
            enabled = False

            def start(self, telemetry_type=None):
                self.enabled = True
                calls.append(("start", telemetry_type))

            def stop(self):
                self.enabled = False
                calls.append(("stop",))

        win.telemetry_mgr = FakeMgr()
        return win, calls

    def test_direct_switch_stops_previous(self):
        """A->B with B telemetry off must stop A's telemetry (no stopped event fires)."""
        win, calls = self._window_with_fake_mgr()
        try:
            game_a = {"id": "ac", "name": "Assetto Corsa", "telemetry_type": "ac_udp"}
            game_b = {"id": "ams2", "name": "Automobilista 2"}
            win._apply_game_started(game_a, "Default", True)
            self.assertIn(("start", "ac_udp"), calls)
            win._apply_game_started(game_b, "Default", False)
            self.assertIn(("stop",), calls)
            self.assertEqual(len([c for c in calls if c[0] == "start"]), 1)
        finally:
            win.detector.stop()

    def test_update_check_retries_when_offline(self):
        """Failed startup check must schedule a retry instead of giving up."""
        from unittest import mock
        from gi.repository import Adw
        Adw.init()
        from fanalinux.ui.window import MainWindow
        win = MainWindow()
        try:
            scheduled = []
            with mock.patch("fanalinux.ui.views.overview.check_latest", return_value=(None, None)):
                with mock.patch("fanalinux.ui.views.overview.GLib.timeout_add_seconds",
                                 side_effect=lambda s, cb: scheduled.append((s, cb)) or 1):
                    win.overview_view._check_updates_bg()
                    self.assertEqual(len(scheduled), 1)
                    self.assertEqual(scheduled[0][0], 900)
                    with mock.patch("threading.Thread"):
                        self.assertFalse(scheduled[0][1]())  # one-shot timer
        finally:
            win.detector.stop()

    def test_manual_telemetry_survives_new_game(self):
        """Telemetry with no game behind it must not be killed by a game detection."""
        win, calls = self._window_with_fake_mgr()
        try:
            win.telemetry_mgr.enabled = True  # manually started, no game
            game_b = {"id": "ams2", "name": "Automobilista 2"}
            win._apply_game_started(game_b, "Default", False)
            self.assertNotIn(("stop",), calls)
        finally:
            win.detector.stop()

    def test_same_game_restart_keeps_session(self):
        """Same game re-detected (e.g. new PID) must not bounce telemetry."""
        win, calls = self._window_with_fake_mgr()
        try:
            game_a = {"id": "ac", "name": "Assetto Corsa", "telemetry_type": "ac_udp"}
            win._apply_game_started(game_a, "Default", True)
            win._apply_game_started(game_a, "Default", True)
            self.assertNotIn(("stop",), calls)
        finally:
            win.detector.stop()

    def test_stale_stop_does_not_kill_new_session(self):
        """A late stop event for game A must not kill game B's session."""
        win, calls = self._window_with_fake_mgr()
        try:
            game_a = {"id": "ac", "name": "Assetto Corsa", "telemetry_type": "ac_udp"}
            game_b = {"id": "ams2", "name": "Automobilista 2", "telemetry_type": "ams2_udp"}
            win._apply_game_started(game_a, "Default", True)
            win._apply_game_started(game_b, "Default", True)
            calls.clear()
            win._apply_game_stopped(game_a, "Default")
            self.assertNotIn(("stop",), calls)
            self.assertEqual(win._telemetry_owner, "ams2")
        finally:
            win.detector.stop()

    def test_owner_exit_stops_owned_session(self):
        """Exiting the owning game stops telemetry and clears ownership."""
        win, calls = self._window_with_fake_mgr()
        try:
            game_a = {"id": "ac", "name": "Assetto Corsa", "telemetry_type": "ac_udp"}
            win._apply_game_started(game_a, "Default", True)
            calls.clear()
            win._apply_game_stopped(game_a, "Default")
            self.assertIn(("stop",), calls)
            self.assertIsNone(win._telemetry_owner)
        finally:
            win.detector.stop()

    def test_haptic_engines_obey_emergency_inhibit(self):
        """Inhibited device must swallow every force output (cutoff is global)."""
        from unittest import mock
        from fanalinux.core.device import FanatecDevice
        dev = FanatecDevice()
        dev._fd = 1
        dev.connected = True
        with mock.patch.object(FanatecDevice, "write_report") as wr:
            dev.send_constant_force(5000)
            dev.send_centering_spring(50)
            dev.send_damper_friction(50)
            dev.send_handle_vibration(100, 100)
            self.assertEqual(wr.call_count, 4)
            dev.output_inhibited = True
            dev.send_constant_force(5000)
            dev.send_centering_spring(50)
            dev.send_damper_friction(50)
            dev.send_handle_vibration(100, 100)
            self.assertEqual(wr.call_count, 4)
            dev.output_inhibited = False
            dev.send_damper_friction(50)
            self.assertEqual(wr.call_count, 5)

    def test_product_id_parsed_from_uevent(self):
        """Podium DD1 uevent must resolve to its product id, junk to None."""
        from fanalinux.core.device import parse_hid_ids
        from fanalinux.core.protocol import PID_CSL_DD
        sample = "HID_ID=0003:00000EB7:00000020\nHID_NAME=Fanatec CSL DD\n"
        self.assertEqual(parse_hid_ids(sample), (0x0EB7, PID_CSL_DD))
        self.assertIsNone(parse_hid_ids("HID_NAME=nope\n"))

    def test_oversteer_fires_without_understeer(self):
        """Rear stepping out must pulse even when the understeer gate is open."""
        from fanalinux.core.haptics import HapticEngine
        from fanalinux.core.vibration import VibrationSettings
        fired = []
        engine = HapticEngine(device=type("D", (), {"connected": True})(),
                              settings=VibrationSettings(understeer_enabled=True,
                                                         oversteer_enabled=True,
                                                         wheel_spin_enabled=False))
        engine._running = True  # skip worker thread, exercise dispatch logic only
        engine.trigger_pulse = lambda intensity, dur: fired.append((intensity, dur))
        # Understeer outer gate open (steering + speed) but front not scrubbing;
        # rear clearly stepping out.
        engine.update_telemetry(rpm=1000, max_rpm=8000, abs_active=False, tc_active=False,
                                speed_kmh=60.0, wheel_slip=(0.05, 0.05, 0.45, 0.45),
                                wheel_speed=(0, 0, 0, 0), suspension=(0, 0, 0, 0),
                                steer_angle=0.5)
        self.assertTrue(fired)

    def test_dkms_version_parsing(self):
        """Only installed module lines count; unknown lines are skipped."""
        from unittest import mock
        from fanalinux.core import driver_setup
        out = ("hid-fanatec/0.2.3-18-g6e58466, 7.2.11-200.fc44.x86_64, x86_64: installed\n"
               "hid-fanatec/0.2.2, 7.2.11-200.fc44.x86_64, x86_64: built\n"
               "v4l2loopback/0.1.0, 7.2.11-200.fc44.x86_64, x86_64: installed\n")
        with mock.patch("subprocess.run") as sr:
            sr.return_value.stdout = out
            self.assertEqual(driver_setup._dkms_versions(), ["0.2.3-18-g6e58466"])
            sr.return_value.stdout = ""
            self.assertEqual(driver_setup._dkms_versions(), [])

    def test_car_database_loads(self):
        """The packaged car database must be present and non-empty."""
        from fanalinux.core.telemetry.manager import CAR_DATABASE
        self.assertTrue(len(CAR_DATABASE) > 0)

    def test_emergency_gate_is_atomic(self):
        """A send blocked on the device lock must observe a gate set meanwhile.
        Fails if the inhibit check ever moves outside the lock."""
        import threading
        import time
        from unittest import mock
        from fanalinux.core.device import FanatecDevice
        dev = FanatecDevice()
        dev._fd = 1
        dev.connected = True
        with mock.patch.object(FanatecDevice, "write_report") as wr:
            dev._lock.acquire()
            try:
                t = threading.Thread(target=lambda: dev.send_damper_friction(50))
                t.start()
                time.sleep(0.2)  # sender is now parked on the device lock
                dev.output_inhibited = True  # emergency gate, lock already held
            finally:
                dev._lock.release()
            t.join(timeout=5)
            self.assertFalse(t.is_alive())
            wr.assert_not_called()

    def test_force_storm_survives_emergency(self):
        """Hammering force outputs around repeated cutoffs must not deadlock."""
        import threading
        from unittest import mock
        from fanalinux.core.device import FanatecDevice
        dev = FanatecDevice()
        dev._fd = 1
        dev.connected = True
        stop = threading.Event()
        def storm():
            while not stop.is_set():
                dev.send_constant_force(1000)
                dev.send_damper_friction(50)
                dev.send_centering_spring(50)
                dev.send_handle_vibration(100, 100)
        with mock.patch.object(FanatecDevice, "write_report"):
            workers = [threading.Thread(target=storm) for _ in range(4)]
            for w in workers:
                w.start()
            for _ in range(5):
                dev.emergency_stop()
                dev.output_inhibited = False
            stop.set()
            for w in workers:
                w.join(timeout=10)
                self.assertFalse(w.is_alive())


class TestTelemetryLifecycle(unittest.TestCase):
    def test_stop_wakes_blocked_worker(self):
        """stop() must interrupt a worker stuck in backoff and leave no zombie."""
        import threading
        import time

        from fanalinux.core.telemetry.ac import AssettoCorsaTelemetry
        client = AssettoCorsaTelemetry()
        entered = threading.Event()

        def slow_worker():
            entered.set()
            client._stop_event.wait(30.0)

        client._worker = slow_worker
        client.start()
        self.assertTrue(entered.wait(2.0))
        t0 = time.monotonic()
        client.stop()
        self.assertLess(time.monotonic() - t0, 5.0)
        self.assertFalse(client._thread is not None and client._thread.is_alive())

    def test_unresponsive_worker_blocks_restart(self):
        """A worker surviving stop() must remain visible to start()'s guard."""
        import threading
        import time
        from fanalinux.core.telemetry.ac import AssettoCorsaTelemetry
        client = AssettoCorsaTelemetry()
        release = threading.Event()

        def stubborn_worker():
            while not release.is_set():
                time.sleep(0.1)

        client._worker = stubborn_worker
        client.start()
        first = client._thread
        self.assertTrue(first.is_alive())
        client.stop()  # join times out; handle must be preserved
        self.assertTrue(first.is_alive())
        self.assertIs(client._thread, first)
        client.start()  # must refuse: no second worker
        self.assertIs(client._thread, first)
        alive = [t for t in threading.enumerate()
                 if t.name == "AssettoCorsaTelemetryThread" and t.is_alive()]
        self.assertEqual(len(alive), 1)
        release.set()
        first.join(timeout=2.0)
        client.start()  # survivor gone: restart proceeds with a new thread
        self.assertIsNot(client._thread, first)
        client.stop()

    def test_no_zombie_accumulation(self):
        """Rapid start/stop cycles must never leave more than one worker."""
        import threading
        import time

        from fanalinux.core.telemetry.ac import AssettoCorsaTelemetry
        client = AssettoCorsaTelemetry()

        def quick_worker():
            while client._running:
                client._stop_event.wait(0.05)

        client._worker = quick_worker

        def alive_workers():
            return [t for t in threading.enumerate()
                    if t.name == "AssettoCorsaTelemetryThread" and t.is_alive()]

        for _ in range(3):
            client.start()
            client.stop()
        time.sleep(0.2)
        self.assertEqual(len(alive_workers()), 0)
        client.start()
        self.assertEqual(len(alive_workers()), 1)
        client.stop()


class TestEvdevWatchdog(unittest.TestCase):
    def test_retry_recovers_listener(self):
        """Failed evdev start must be retried with backoff while HID is online."""
        from gi.repository import Adw
        Adw.init()
        from fanalinux.ui.window import MainWindow
        win = MainWindow()
        try:
            class FakeListener:
                def __init__(self):
                    self.calls = 0
                    self.running = False
                    self.device_node = None

                def is_running(self):
                    return self.running

                def start(self):
                    self.calls += 1
                    if self.calls >= 2:
                        self.running = True
                        return True
                    return False

            win.evdev_listener = FakeListener()
            win.device.check_connection = lambda: True
            win._last_evdev_retry = 0.0
            win._check_hardware_connection()  # transition: attempt 1 fails
            self.assertEqual(win.evdev_listener.calls, 1)
            win._check_hardware_connection()  # backoff: no immediate retry
            self.assertEqual(win.evdev_listener.calls, 1)
            win._last_evdev_retry -= 6.0  # 6s pass
            win._check_hardware_connection()  # watchdog: attempt 2 succeeds
            self.assertEqual(win.evdev_listener.calls, 2)
            self.assertTrue(win.evdev_listener.is_running())
        finally:
            win.detector.stop()


class TestFfDriverProbe(unittest.TestCase):
    def test_decode_effects(self):
        from fanalinux.core.evdev_listener import decode_ff_effects
        self.assertEqual(decode_ff_effects(0), [])
        got = decode_ff_effects((1 << 0x52) | (1 << 0x55))
        self.assertEqual(got, ["Constant", "Damper"])

    def test_query_no_node(self):
        from fanalinux.core.evdev_listener import query_ff_effects
        self.assertEqual(query_ff_effects(None), [])
        self.assertEqual(query_ff_effects("/dev/input/nonexistent999"), [])

    def test_driver_version_compare(self):
        from fanalinux.core import driver_setup
        self.assertTrue(driver_setup.is_upstream_newer("0.2.2", "0.2.3"))
        self.assertFalse(driver_setup.is_upstream_newer("0.2.3", "0.2.3"))
        self.assertFalse(driver_setup.is_upstream_newer("0.2.3-18-g6e58466", "0.2.3"))
        self.assertTrue(driver_setup.is_upstream_newer("unknown", "0.2.3"))
        self.assertFalse(driver_setup.is_upstream_newer("0.2.3", None))
        self.assertIsInstance(driver_setup.installed_version(), (str, type(None)))

    def test_match_game_process_ignores_wrappers(self):
        from fanalinux.core.detector import match_game_process
        # Real game: Windows-path argv[0] or comm
        self.assertTrue(match_game_process("", ["Z:\\mnt\\games\\assettocorsa\\acs.exe"], "acs.exe"))
        self.assertTrue(match_game_process("acs.exe", [], "acs.exe"))
        # Wrappers carry the game path in later args: must not match
        self.assertFalse(match_game_process("", ["/home/dd/.steam/root/ubuntu12_32/reaper",
            "SteamLaunch", "AppId=244210", "--", "/mnt/games/assettocorsa/AssettoCorsa.exe"],
            "assettocorsa.exe"))
        self.assertFalse(match_game_process("", ["/usr/bin/bwrap", "--args", "26", "/path/acs.exe"], "acs.exe"))
        self.assertFalse(match_game_process("", [], "acs.exe"))

    def test_detection_keys_on_race_not_launcher(self):
        # Launchers (CM, BeamNG UI) outlive the race: detecting them makes a
        # dead race look still active (frozen OLED, no stopped event).
        from fanalinux.core.detector import BUILTIN_GAMES
        by_id = {g["id"]: g for g in BUILTIN_GAMES}
        self.assertNotIn("assettocorsa.exe", by_id["assetto_corsa"]["executables"])
        self.assertNotIn("beamng.drive.ui.x64.exe", by_id["beamng"]["executables"])


class TestUdevRule(unittest.TestCase):
    def test_no_world_writable_mode(self):
        rule = PROJECT_ROOT / "udev" / "99-fanatec-fanalinux.rules"
        text = rule.read_text()
        self.assertNotIn("0666", text)
        self.assertIn("uaccess", text)


if __name__ == "__main__":
    unittest.main()
