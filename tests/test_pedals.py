"""USB pedal mapping tests; no real controller is opened or grabbed."""

import tempfile
import os
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from evdev import AbsInfo, InputDevice, InputEvent, UInput, ecodes

from fanalinux.core import pedals


def event(etype, code, value=0):
    return InputEvent(0, 0, etype, code, value)


class PedalTests(unittest.TestCase):
    def test_scaling_and_bounds(self):
        for raw in (0, 1, 500, 4095):
            self.assertEqual(pedals.scale_brake(raw, 100, 0, 4095), raw)
        self.assertEqual(pedals.scale_brake(819, 20, 0, 4095), 4095)
        self.assertEqual(pedals.scale_brake(400, 20, 0, 4095), 2000)
        self.assertEqual(pedals.scale_brake(30, 50, 10, 110), 50)
        self.assertEqual(pedals.scale_brake(-90, 50, -110, -10), -70)
        self.assertEqual(pedals.scale_brake(-10, 20, 0, 100), 0)
        self.assertEqual(pedals.scale_brake(200, 20, 0, 100), 100)
        for value, expected in [(0, 1), (500, 100), (None, 100), ("bad", 100)]:
            self.assertEqual(pedals.clamp_force(value), expected)

    def test_settings_roundtrip_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pedals.json"
            with patch.object(pedals, "SETTINGS_PATH", path):
                self.assertEqual(pedals.PedalSettings.load(), pedals.PedalSettings())
                settings = pedals.PedalSettings(True, 20)
                self.assertTrue(settings.save())
                self.assertEqual(pedals.PedalSettings.load(), settings)
                path.write_text('{"enabled": "false", "brake_force": 0}')
                self.assertEqual(pedals.PedalSettings.load(), pedals.PedalSettings(False, 1))
                path.write_text('[]')
                self.assertEqual(pedals.PedalSettings.load(), pedals.PedalSettings())

    def make_device(self, product=0x183B, name="ClubSport Pedals V3", bus=ecodes.BUS_USB):
        device = MagicMock()
        device.info = SimpleNamespace(vendor=0x0EB7, product=product, bustype=bus, version=1)
        device.name = name
        device.capabilities.return_value = {
            ecodes.EV_ABS: [ecodes.ABS_X, ecodes.ABS_Y, ecodes.ABS_Z],
            ecodes.EV_KEY: [ecodes.BTN_0],
        }
        device.absinfo.side_effect = lambda code: AbsInfo(40 if code == ecodes.ABS_Y else 7, 0, 100, 0, 0, 0)
        device.active_keys.return_value = [ecodes.BTN_0]
        # Match evdev's default: ABS codes include AbsInfo unless opted out.
        caps = device.capabilities.return_value
        device.capabilities.side_effect = lambda absinfo=True: {
            **caps, ecodes.EV_ABS: [(code, device.absinfo(code)) for code in caps[ecodes.EV_ABS]]
            if absinfo else caps[ecodes.EV_ABS],
        }
        return device

    def test_discovery_matches_all_supported_sets(self):
        for product, name in pedals.PEDAL_SETS.items():
            device = self.make_device(product=product, name=name)
            with patch.object(pedals, "list_devices", return_value=["a"]), \
                    patch.object(pedals, "InputDevice", return_value=device):
                self.assertIs(pedals.PedalMapper._find_pedals(), device)

    def test_discovery_excludes_wheelbases_and_own_output(self):
        devices = [self.make_device(product=0x0005),
                   self.make_device(name=pedals.VIRTUAL_NAME),
                   self.make_device(bus=ecodes.BUS_VIRTUAL), self.make_device()]
        with patch.object(pedals, "list_devices", return_value=list("abcd")), \
                patch.object(pedals, "InputDevice", side_effect=devices):
            self.assertIs(pedals.PedalMapper._find_pedals(), devices[-1])
        for device in devices[:-1]:
            device.close.assert_called_once()
        devices[-1].close.assert_not_called()

    def run_session(self, mapper, device, poll):
        virtual = MagicMock()
        virtual.__enter__.return_value = virtual
        with patch.object(pedals.UInput, "from_device", return_value=virtual), \
                patch.object(pedals.select, "select", side_effect=poll):
            mapper._session(device)
        return virtual

    def test_snapshot_passthrough_and_grab_cleanup(self):
        mapper = pedals.PedalMapper(20)
        device = self.make_device()
        throttle = event(ecodes.EV_ABS, ecodes.ABS_X, 60)
        brake = event(ecodes.EV_ABS, ecodes.ABS_Y, 10)
        button = event(ecodes.EV_KEY, ecodes.BTN_0, 0)
        sync = event(ecodes.EV_SYN, ecodes.SYN_REPORT)
        device.read.return_value = [throttle, brake, button, sync]

        def poll(*_):
            mapper._stop.set()
            return [device], [], []

        virtual = self.run_session(mapper, device, poll)
        virtual.write.assert_any_call(ecodes.EV_ABS, ecodes.ABS_Y, 100)
        virtual.write.assert_any_call(ecodes.EV_ABS, ecodes.ABS_Y, 50)
        virtual.write.assert_any_call(ecodes.EV_ABS, ecodes.ABS_Z, 7)
        virtual.write_event.assert_any_call(throttle)
        virtual.write_event.assert_any_call(button)
        virtual.write_event.assert_any_call(sync)
        self.assertEqual(mapper.input, 0.1)
        self.assertEqual(mapper.output, 0.5)
        device.grab.assert_called_once()
        device.ungrab.assert_called_once()
        virtual.__exit__.assert_called_once()

    def test_force_change_updates_a_held_brake(self):
        mapper = pedals.PedalMapper(100)
        device = self.make_device()
        polls = 0

        def poll(*_):
            nonlocal polls
            polls += 1
            if polls == 1:
                mapper.set_force(50)
            else:
                mapper._stop.set()
            return [], [], []

        virtual = self.run_session(mapper, device, poll)
        virtual.write.assert_any_call(ecodes.EV_ABS, ecodes.ABS_Y, 80)
        self.assertEqual(mapper.output, 0.8)

    def test_disconnect_and_failed_grab_close_output(self):
        for fail_grab in (False, True):
            with self.subTest(fail_grab=fail_grab):
                mapper = pedals.PedalMapper()
                device = self.make_device()
                virtual = MagicMock()
                virtual.__enter__.return_value = virtual
                if fail_grab:
                    device.grab.side_effect = OSError("already grabbed")
                with patch.object(pedals.UInput, "from_device", return_value=virtual), \
                        patch.object(pedals.select, "select", side_effect=OSError("unplugged")):
                    with self.assertRaises(OSError):
                        mapper._session(device)
                virtual.__exit__.assert_called_once()
                self.assertEqual(device.ungrab.call_count, 0 if fail_grab else 1)

    def test_syn_dropped_resnapshots_and_discards_stale_events(self):
        mapper = pedals.PedalMapper(50)
        device = self.make_device()
        stale = event(ecodes.EV_ABS, ecodes.ABS_X, 99)
        device.read.return_value = [event(ecodes.EV_SYN, ecodes.SYN_DROPPED), stale,
                                    event(ecodes.EV_SYN, ecodes.SYN_REPORT)]

        def poll(*_):
            mapper._stop.set()
            return [device], [], []

        virtual = self.run_session(mapper, device, poll)
        virtual.write_event.assert_not_called()
        self.assertEqual(virtual.syn.call_count, 2)
        self.assertEqual(mapper.output, 0.8)

    def test_stop_wakes_reconnect_wait_and_can_restart(self):
        mapper = pedals.PedalMapper()
        with patch.object(mapper, "_find_pedals", return_value=None):
            mapper.start()
            thread = mapper._thread
            mapper.start()
            self.assertIs(mapper._thread, thread)
            mapper.stop()
            self.assertFalse(thread.is_alive())
            mapper.start()
            mapper.stop()
        self.assertEqual(mapper.status, "Disabled")

    def test_uinput_permission_errors_are_reported_and_retried(self):
        mapper = pedals.PedalMapper()
        device = self.make_device()
        device.__enter__.return_value = device
        mapper._stop = MagicMock()
        mapper._stop.is_set.side_effect = [False, True]
        with patch.object(mapper, "_find_pedals", return_value=device), \
                patch.object(mapper, "_session", side_effect=pedals.UInputError("no access")):
            mapper._worker()
        self.assertIn("no access", mapper.status)
        self.assertIn("uinput", mapper.status)
        mapper._stop.wait.assert_called_once_with(1.0)
        device.__exit__.assert_called_once()

    def test_worker_reconnects_after_unplug(self):
        mapper = pedals.PedalMapper()
        devices = [self.make_device(), self.make_device()]
        for device in devices:
            device.__enter__.return_value = device
        mapper._stop = MagicMock()
        mapper._stop.is_set.side_effect = [False, False, True]
        with patch.object(mapper, "_find_pedals", side_effect=devices), \
                patch.object(mapper, "_session", side_effect=[OSError("unplugged"), None]) as session:
            mapper._worker()
        self.assertEqual(session.call_count, 2)
        for device in devices:
            device.__exit__.assert_called_once()


@unittest.skipUnless(os.environ.get("FANALINUX_UINPUT_TESTS") == "1",
                     "set FANALINUX_UINPUT_TESTS=1 to test synthetic kernel input devices")
class KernelPedalTests(unittest.TestCase):
    def test_real_uinput_mapping_and_release(self):
        """Exercise actual evdev metadata, grabbing and output without real pedals."""
        capabilities = {ecodes.EV_ABS: [
            (ecodes.ABS_X, AbsInfo(0, 0, 4095, 0, 0, 0)),
            (ecodes.ABS_Y, AbsInfo(0, 0, 4095, 0, 0, 0)),
            (ecodes.ABS_Z, AbsInfo(0, 0, 4095, 0, 0, 0)),
        ], ecodes.EV_KEY: [ecodes.BTN_TRIGGER]}
        mapper = pedals.PedalMapper(20)
        errors, outputs = [], []
        real_factory = UInput.from_device

        def factory(*args, **kwargs):
            output = real_factory(*args, **kwargs)
            outputs.append(output)
            return output

        def wait_until(condition):
            deadline = time.monotonic() + 3
            while not condition():
                if errors:
                    raise errors[0]
                if time.monotonic() > deadline:
                    self.fail("Timed out waiting for synthetic mapper")
                time.sleep(0.01)

        with UInput(capabilities, name="FanaLinux synthetic pedal test", vendor=1, product=1) as source:
            if source.device is None:
                self.skipTest("Synthetic event nodes are not accessible to this user; input permissions required")
            with InputDevice(source.device.path) as device:
                def run():
                    try:
                        mapper._session(device)
                    except Exception as exc:
                        errors.append(exc)

                with patch.object(pedals.UInput, "from_device", side_effect=factory):
                    thread = threading.Thread(target=run)
                    thread.start()
                    try:
                        wait_until(lambda: mapper.status.startswith("Connected"))
                        output = outputs[0].device
                        self.assertEqual(output.absinfo(ecodes.ABS_Y).max, 4095)
                        source.write(ecodes.EV_ABS, ecodes.ABS_Y, 400)
                        source.write(ecodes.EV_ABS, ecodes.ABS_X, 700)
                        source.write(ecodes.EV_KEY, ecodes.BTN_TRIGGER, 1)
                        source.syn()
                        wait_until(lambda: output.absinfo(ecodes.ABS_Y).value == 2000)
                        self.assertEqual(output.absinfo(ecodes.ABS_X).value, 700)
                        self.assertIn(ecodes.BTN_TRIGGER, output.active_keys())
                        mapper.set_force(100)
                        wait_until(lambda: output.absinfo(ecodes.ABS_Y).value == 400)
                    finally:
                        mapper._stop.set()
                        thread.join(timeout=3)
                    self.assertFalse(thread.is_alive())
                    self.assertEqual(errors, [])
                device.grab()  # Session must have released exclusive ownership.
                device.ungrab()


if __name__ == "__main__":
    unittest.main()
