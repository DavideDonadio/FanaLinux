"""
Automated unit tests for multi-game telemetry parsers and TelemetryManager.
Replays packet fixtures for BeamNG.drive, DiRT Rally 2.0 / WRC, and EA F1.
"""

import struct
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fanalinux.core.detector import GameDetector
from fanalinux.core.telemetry.ams2 import AMS2Telemetry
from fanalinux.core.telemetry.beamng import BeamNGTelemetry
from fanalinux.core.telemetry.dirt import DirtRallyTelemetry
from fanalinux.core.telemetry.f1 import F1Telemetry
from fanalinux.core.telemetry.forza import ForzaTelemetry
from fanalinux.core.telemetry.manager import TelemetryManager
from fanalinux.core.telemetry.scs import SCSTelemetry

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)


class DummyDevice:
    def __init__(self):
        self.connected = True
        self.active_sen = 900
        self.revleds = []
        self.flagleds = []
        self.display_text = ""

    def set_revleds(self, colors):
        self.revleds = colors

    def set_flagleds(self, colors):
        self.flagleds = colors

    def set_display_text(self, text):
        self.display_text = text

    def clear_display(self):
        self.display_text = ""


class TestMultiGameTelemetry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 1. Create BeamNG OutGauge fixture (exact 92 bytes)
        # Format: <I 4s H b b 7f 2I 3f 16s 16s
        # showLights: (1 << 10) = ABS active
        beamng_pkt = struct.pack(
            BeamNGTelemetry.OUTGAUGE_FORMAT,
            12345,                      # time
            b"bol\x00",                 # car name
            0,                          # flags
            4,                          # raw_gear = 4 -> gear = 3 (3rd)
            0,                          # plid
            33.3333,                    # speed_ms (approx 120 km/h)
            6250.0,                     # rpm
            1.2, 90.0, 0.75, 4.5, 95.0, # turbo, engTemp, fuel, oilPressure, oilTemp
            0,                          # dashLights
            1 << 10,                    # showLights (ABS active)
            0.85, 0.40, 0.0,            # throttle, brake, clutch
            b"Fuel: 75%       ",        # display1
            b"Sport Mode      "         # display2
        )
        assert len(beamng_pkt) == 92, f"Expected 92 bytes, got {len(beamng_pkt)}"
        cls.beamng_fixture_path = FIXTURES_DIR / "beamng_outgauge.bin"
        with open(cls.beamng_fixture_path, "wb") as f:
            f.write(beamng_pkt)

        # 2. Create DiRT Rally 2.0 extradata=3 fixture (64 floats, 256 bytes)
        dirt_floats = [0.0] * 64
        dirt_floats[7] = 27.7778        # speed m/s (~100 km/h)
        dirt_floats[17] = 0.140         # RL suspension
        dirt_floats[18] = 0.138         # RR suspension
        dirt_floats[19] = 0.125         # FL suspension
        dirt_floats[20] = 0.120         # FR suspension
        # Wheel speeds (m/s): RL (25), RR (26), FL (27), FR (28)
        dirt_floats[25] = 27.5          # RL wheel
        dirt_floats[26] = 27.6          # RR wheel
        dirt_floats[27] = 27.7          # FL wheel
        dirt_floats[28] = 27.8          # FR wheel
        dirt_floats[29] = 0.75          # throttle
        dirt_floats[30] = -0.35         # steer
        dirt_floats[31] = 0.0           # brake
        dirt_floats[33] = 4.0           # 4th gear
        dirt_floats[37] = 680.0         # RPM / 10 -> 6800 RPM

        dirt_pkt = struct.pack("<64f", *dirt_floats)
        assert len(dirt_pkt) == 256
        cls.dirt_fixture_path = FIXTURES_DIR / "dirt_rally_extradata3.bin"
        with open(cls.dirt_fixture_path, "wb") as f:
            f.write(dirt_pkt)

        # 3. Create F1 2023 Car Telemetry & Status fixtures
        f1_telem_hdr = struct.pack(
            "<HBBBBBQfIIBB",
            2023, 23, 1, 0, 1,
            6,                          # Packet 6: Car Telemetry
            123456789, 45.2, 1000, 1000,
            0, 255
        ).ljust(29, b"\x00")
        
        # Player entry (60 bytes)
        player_entry = bytearray(60)
        struct.pack_into("<H", player_entry, 0, 245)    # 245 km/h
        struct.pack_into("<f", player_entry, 6, 0.12)   # steer
        struct.pack_into("<b", player_entry, 15, 6)     # 6th gear
        struct.pack_into("<H", player_entry, 16, 11800) # 11800 RPM
        cls.f1_telem_pkt = bytes(f1_telem_hdr) + bytes(player_entry) * 22

        # Status Packet (Packet 7) for F1 2023 (55 bytes per car)
        f1_status_hdr = struct.pack(
            "<HBBBBBQfIIBB",
            2023, 23, 1, 0, 1,
            7,                          # Packet 7: Car Status
            123456789, 45.2, 1000, 1000,
            0, 255
        ).ljust(29, b"\x00")
        player_status = bytearray(55)
        player_status[0] = 1            # Traction Control Active
        player_status[1] = 1            # ABS Active
        struct.pack_into("<H", player_status, 17, 13500) # maxRPM at offset 17: 13500
        cls.f1_status_pkt = bytes(f1_status_hdr) + bytes(player_status) * 22

    def test_shared_udp_loop_delivers_packets(self):
        """Loopback through the shared bind/select/dispatch worker."""
        import socket
        import time
        received = []
        client = BeamNGTelemetry(on_telemetry=lambda *a, **k: received.append((a, k)))
        free = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        free.bind(("127.0.0.1", 0))
        port = free.getsockname()[1]
        free.close()
        client.UDP_PORT = port
        client.start()
        try:
            with open(self.beamng_fixture_path, "rb") as f:
                data = f.read()
            sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            deadline = time.time() + 5
            while not received and time.time() < deadline:
                sender.sendto(data, ("127.0.0.1", port))
                time.sleep(0.1)
            sender.close()
            self.assertTrue(received)
            self.assertEqual(received[0][0][0], 6250)  # rpm from fixture
            self.assertTrue(client.is_connected)
        finally:
            client.stop()
        self.assertFalse(client.is_running)

    def test_beamng_telemetry_dispatch(self):
        received = []
        def _cb(*args, **kwargs):
            received.append((args, kwargs))

        client = BeamNGTelemetry(on_telemetry=_cb)
        with open(self.beamng_fixture_path, "rb") as f:
            data = f.read()
        self.assertEqual(len(data), 92)
        client.process_packet(data)

        self.assertEqual(len(received), 1)
        args, kwargs = received[0]
        rpm, gear, speed_kmh, abs_active, tc_active = args
        self.assertEqual(rpm, 6250)
        self.assertEqual(gear, 3) # 4 - 1
        self.assertAlmostEqual(speed_kmh, 120.0, delta=0.5)
        self.assertTrue(abs_active)
        self.assertFalse(tc_active)
        self.assertEqual(client.car_name, "bol")

    def test_dirt_rally_telemetry_dispatch(self):
        received = []
        def _cb(*args, **kwargs):
            received.append((args, kwargs))

        client = DirtRallyTelemetry(on_telemetry=_cb)
        with open(self.dirt_fixture_path, "rb") as f:
            data = f.read()
        self.assertEqual(len(data), 256)
        client.process_packet(data)

        self.assertEqual(len(received), 1)
        args, kwargs = received[0]
        rpm, gear, speed_kmh, abs_active, tc_active = args
        self.assertEqual(rpm, 6800)
        self.assertEqual(gear, 4)
        self.assertAlmostEqual(speed_kmh, 100.0, delta=0.5)
        self.assertAlmostEqual(kwargs["steer_angle"], -0.35, places=2)
        self.assertIn("suspension", kwargs)
        self.assertAlmostEqual(kwargs["suspension"][0], 0.125, places=3)
        self.assertIn("wheel_slip", kwargs)
        # Verify signed slip ratios
        fl_slip, fr_slip, rl_slip, rr_slip = kwargs["wheel_slip"]
        self.assertAlmostEqual(fl_slip, (27.7 - 27.7778) / 27.7778, places=3)
        self.assertAlmostEqual(rl_slip, (27.5 - 27.7778) / 27.7778, places=3)

    def test_f1_telemetry_dispatch(self):
        received = []
        def _cb(*args, **kwargs):
            received.append((args, kwargs))

        client = F1Telemetry(on_telemetry=_cb)
        # Feed status packet first (sets ABS / TC state and max_rpm from offset 17)
        client.process_packet(self.f1_status_pkt)
        self.assertEqual(client.max_rpm, 13500)

        # Feed telemetry packet
        client.process_packet(self.f1_telem_pkt)
        self.assertEqual(len(received), 1)
        args, kwargs = received[0]
        rpm, gear, speed_kmh, abs_active, tc_active = args
        self.assertEqual(rpm, 11800)
        self.assertEqual(gear, 6)
        self.assertEqual(speed_kmh, 245.0)
        self.assertTrue(abs_active)
        self.assertTrue(tc_active)

    def test_telemetry_manager_dynamic_switching_and_stop_all(self):
        dev = DummyDevice()
        mgr = TelemetryManager(dev)
        
        # Test start with BeamNG
        mgr.start(telemetry_type="beamng_outgauge")
        self.assertEqual(mgr.active_telemetry_type, "beamng_outgauge")
        self.assertIsInstance(mgr.active_client, BeamNGTelemetry)

        # Replay BeamNG packet into active client
        with open(self.beamng_fixture_path, "rb") as f:
            mgr.active_client.process_packet(f.read())
        self.assertEqual(dev.display_text, "3")

        # Test switch to DiRT
        mgr.start(telemetry_type="dirt_udp")
        self.assertEqual(mgr.active_telemetry_type, "dirt_udp")
        self.assertIsInstance(mgr.active_client, DirtRallyTelemetry)

        # Replay DiRT packet into active client
        with open(self.dirt_fixture_path, "rb") as f:
            mgr.active_client.process_packet(f.read())
        self.assertEqual(dev.display_text, "4")

        # Test stop: stops all instantiated clients
        mgr.stop()
        self.assertFalse(mgr.enabled)
        for c in mgr._clients.values():
            self.assertFalse(c._running)

    def test_assetto_corsa_dispatch(self):
        from fanalinux.core.telemetry.ac import parse_ac_packet
        pkt = bytearray(328)
        pkt[0] = ord('a')
        struct.pack_into("<f", pkt, 8, 55.5556)   # speed
        pkt[21] = 1                                # ABS on
        pkt[22] = 0                                # TC off
        struct.pack_into("<f", pkt, 68, 7200.0)   # rpm
        struct.pack_into("<i", pkt, 76, 4)        # raw gear 4 -> 3rd
        struct.pack_into("<f", pkt, 24, 0.12)     # steer angle
        parsed = parse_ac_packet(bytes(pkt))
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["rpm"], 7200)
        self.assertEqual(parsed["gear"], 3)
        self.assertAlmostEqual(parsed["speed_kmh"], 55.5556, places=3)
        self.assertTrue(parsed["abs_active"])
        self.assertFalse(parsed["tc_active"])
        self.assertAlmostEqual(parsed["steer_angle"], 0.12, places=4)
        self.assertIsNone(parse_ac_packet(b"junk"))
        self.assertIsNone(parse_ac_packet(bytes(100)))

    def test_forza_telemetry_dispatch(self):
        received = []
        def _cb(*args, **kwargs):
            received.append((args, kwargs))

        client = ForzaTelemetry(on_telemetry=_cb)
        forza_pkt = bytearray(324)
        struct.pack_into("<iI3f", forza_pkt, 0, 1, 1000, 8200.0, 800.0, 7200.0)
        struct.pack_into("<4f", forza_pkt, 68, 0.05, 0.05, 0.06, 0.06)
        struct.pack_into("<4f", forza_pkt, 84, 0.1, 0.1, 0.2, 0.2)
        struct.pack_into("<4f", forza_pkt, 100, 150.0, 150.0, 150.0, 150.0)
        struct.pack_into("<f", forza_pkt, 256, 50.0) # 50 m/s -> 180 km/h
        struct.pack_into("<BbBB", forza_pkt, 312, 4, -64, 200, 50) # gear 4 -> 3rd, steer -64

        client.process_packet(bytes(forza_pkt))
        self.assertEqual(len(received), 1)
        args, kwargs = received[0]
        rpm, gear, speed_kmh, abs_active, tc_active = args
        self.assertEqual(rpm, 7200)
        self.assertEqual(gear, 3)
        self.assertEqual(speed_kmh, 180.0)
        self.assertEqual(client.max_rpm, 8200)
        self.assertAlmostEqual(kwargs["steer_angle"], -64 / 127.0, places=2)

    def test_forza_telemetry_fm7_311_byte_dispatch(self):
        received = []
        def _cb(*args, **kwargs):
            received.append((args, kwargs))

        client = ForzaTelemetry(on_telemetry=_cb)
        # FM7 layout: exactly 311 bytes, speed at offset 244, inputs at offset 307
        fm7_pkt = bytearray(311)
        struct.pack_into("<iI3f", fm7_pkt, 0, 1, 1000, 7500.0, 800.0, 6800.0)
        struct.pack_into("<4f", fm7_pkt, 68, 0.05, 0.05, 0.06, 0.06)
        struct.pack_into("<4f", fm7_pkt, 84, 0.1, 0.1, 0.2, 0.2)
        struct.pack_into("<4f", fm7_pkt, 100, 140.0, 140.0, 140.0, 140.0)
        struct.pack_into("<f", fm7_pkt, 244, 45.0) # 45 m/s -> 162 km/h
        struct.pack_into("<BbBB", fm7_pkt, 307, 3, 32, 180, 0) # gear 3 -> 2nd, steer 32

        client.process_packet(bytes(fm7_pkt))
        self.assertEqual(len(received), 1)
        args, kwargs = received[0]
        rpm, gear, speed_kmh, abs_active, tc_active = args
        self.assertEqual(rpm, 6800)
        self.assertEqual(gear, 2)
        self.assertEqual(speed_kmh, 162.0)
        self.assertEqual(client.max_rpm, 7500)
        self.assertAlmostEqual(kwargs["steer_angle"], 32 / 127.0, places=2)

    def test_ams2_telemetry_dispatch(self):
        received = []
        def _cb(*args, **kwargs):
            received.append((args, kwargs))

        client = AMS2Telemetry(on_telemetry=_cb)
        ams2_pkt = bytearray(556)
        struct.pack_into("<IIBBBB", ams2_pkt, 0, 10, 10, 0, 1, 0, 2)
        struct.pack_into("<B", ams2_pkt, 17, 16 | 64) # CAR_ABS | CAR_TCS
        struct.pack_into("<f", ams2_pkt, 36, 41.6667) # ~150 km/h
        struct.pack_into("<HH", ams2_pkt, 40, 7500, 9000)
        struct.pack_into("<b", ams2_pkt, 44, 32)
        struct.pack_into("<B", ams2_pkt, 45, 5 | (6 << 4)) # 5th gear
        struct.pack_into("<4f", ams2_pkt, 160, 126.0, 126.0, 126.0, 126.0)
        struct.pack_into("<4f", ams2_pkt, 312, 0.05, 0.05, 0.06, 0.06)

        client.process_packet(bytes(ams2_pkt))
        self.assertEqual(len(received), 1)
        args, kwargs = received[0]
        rpm, gear, speed_kmh, abs_active, tc_active = args
        self.assertEqual(rpm, 7500)
        self.assertEqual(gear, 5)
        self.assertAlmostEqual(speed_kmh, 150.0, delta=0.5)
        self.assertEqual(client.max_rpm, 9000)
        self.assertTrue(abs_active)
        self.assertTrue(tc_active)

    def test_scs_telemetry_dispatch(self):
        received = []
        def _cb(*args, **kwargs):
            received.append((args, kwargs))

        client = SCSTelemetry(on_telemetry=_cb)
        scs_buf = bytearray(1024)
        struct.pack_into("<?", scs_buf, 4, False)
        struct.pack_into("<i", scs_buf, 504, 8)
        struct.pack_into("<f", scs_buf, 740, 2500.0)
        struct.pack_into("<5f", scs_buf, 948, 22.2222, 1450.0, 0.15, 0.8, 0.0)

        client.process_frame(scs_buf)
        self.assertEqual(len(received), 1)
        args, kwargs = received[0]
        rpm, gear, speed_kmh, abs_active, tc_active = args
        self.assertEqual(rpm, 1450)
        self.assertEqual(gear, 8)
        self.assertAlmostEqual(speed_kmh, 80.0, delta=0.5)
        self.assertEqual(client.max_rpm, 2500)
        self.assertAlmostEqual(kwargs["steer_angle"], 0.15, places=2)

    def test_detector_migration_to_v3(self):
        detector = GameDetector()
        # Verify that all supported games have auto_telemetry enabled
        supported_telemetry_games = (
            "ea_sports_f1", "dirt_rally_2", "ea_wrc", "beamng",
            "forza_motorsport", "ams2", "ets2", "ats"
        )
        for gid in supported_telemetry_games:
            mapping = detector.game_mappings.get(gid, {})
            self.assertTrue(mapping.get("auto_telemetry", False), f"{gid} should have auto_telemetry True")
        self.assertGreaterEqual(detector.config_version, 3)


if __name__ == "__main__":
    unittest.main()
