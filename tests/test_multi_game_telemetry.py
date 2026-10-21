"""
Automated unit tests for multi-game telemetry parsers and TelemetryManager.
Replays packet fixtures for BeamNG.drive, DiRT Rally 2.0 / WRC, and EA F1.
"""

import os
import sys
import struct
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fanalinux.core.telemetry.manager import TelemetryManager
from fanalinux.core.telemetry.beamng import BeamNGTelemetry
from fanalinux.core.telemetry.dirt import DirtRallyTelemetry
from fanalinux.core.telemetry.f1 import F1Telemetry
from fanalinux.core.detector import BUILTIN_GAMES

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
        # 1. Create BeamNG OutGauge fixture (92 bytes)
        # Format: <I 4s 4s H b b 7f 2I 3f 16s 16s
        # showLights: (1 << 10) = ABS active
        beamng_pkt = struct.pack(
            BeamNGTelemetry.OUTGAUGE_FORMAT,
            12345,                      # time
            b"bol\x00",                 # car name
            b"beam",                    # code
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
        cls.beamng_fixture_path = FIXTURES_DIR / "beamng_outgauge.bin"
        with open(cls.beamng_fixture_path, "wb") as f:
            f.write(beamng_pkt)

        # 2. Create DiRT Rally 2.0 extradata=3 fixture (64 floats, 256 bytes)
        dirt_floats = [0.0] * 64
        dirt_floats[7] = 27.7778        # speed m/s (~100 km/h)
        dirt_floats[33] = 4.0           # 4th gear
        dirt_floats[37] = 680.0         # RPM / 10 -> 6800 RPM
        dirt_floats[19] = 0.125         # FL suspension
        dirt_floats[20] = 0.120         # FR suspension
        dirt_floats[17] = 0.140         # RL suspension
        dirt_floats[18] = 0.138         # RR suspension
        dirt_floats[3] = 0.25           # steer
        dirt_pkt = struct.pack("<64f", *dirt_floats)
        cls.dirt_fixture_path = FIXTURES_DIR / "dirt_rally_extradata3.bin"
        with open(cls.dirt_fixture_path, "wb") as f:
            f.write(dirt_pkt)

        # 3. Create F1 2023 Car Telemetry & Status fixtures
        # F1 2023 Header: 29 bytes
        # packetFormat (2023: H), gameYear (23: B), gameMajor (1: B), gameMinor (0: B), packetVer (1: B), packetId (6: B)
        # sessionUID (Q), sessionTime (f), frameId (I), overallFrameId (I), playerCarIndex (0: B), secIndex (255: B)
        f1_telem_hdr = struct.pack(
            "<HBBBBBQfIIBB",
            2023, 23, 1, 0, 1,
            6,                          # Packet 6: Car Telemetry
            123456789, 45.2, 1000, 1000,
            0, 255
        )
        # Pad header to 29 bytes
        f1_telem_hdr = f1_telem_hdr.ljust(29, b"\x00")
        
        # Player entry (60 bytes)
        # speed (uint16: 245), throttle (float), steer (float: 0.12), brake (float), clutch (uint8), gear (int8: 6), rpm (uint16: 11800)
        player_entry = bytearray(60)
        struct.pack_into("<H", player_entry, 0, 245)    # 245 km/h
        struct.pack_into("<f", player_entry, 6, 0.12)   # steer
        struct.pack_into("<b", player_entry, 15, 6)     # 6th gear
        struct.pack_into("<H", player_entry, 16, 11800) # 11800 RPM
        cls.f1_telem_pkt = bytes(f1_telem_hdr) + bytes(player_entry) * 22

        # Status Packet (Packet 7)
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
        struct.pack_into("<H", player_status, 14, 13500) # maxRPM: 13500
        cls.f1_status_pkt = bytes(f1_status_hdr) + bytes(player_status) * 22

    def test_beamng_telemetry_dispatch(self):
        received = []
        def _cb(*args, **kwargs):
            received.append((args, kwargs))

        client = BeamNGTelemetry(on_telemetry=_cb)
        with open(self.beamng_fixture_path, "rb") as f:
            data = f.read()
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
        client.process_packet(data)

        self.assertEqual(len(received), 1)
        args, kwargs = received[0]
        rpm, gear, speed_kmh, abs_active, tc_active = args
        self.assertEqual(rpm, 6800)
        self.assertEqual(gear, 4)
        self.assertAlmostEqual(speed_kmh, 100.0, delta=0.5)
        self.assertIn("suspension", kwargs)
        self.assertAlmostEqual(kwargs["suspension"][0], 0.125, places=3)

    def test_f1_telemetry_dispatch(self):
        received = []
        def _cb(*args, **kwargs):
            received.append((args, kwargs))

        client = F1Telemetry(on_telemetry=_cb)
        # Feed status packet first (sets ABS / TC state)
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

    def test_telemetry_manager_dynamic_switching(self):
        dev = DummyDevice()
        mgr = TelemetryManager(dev)
        
        # Test start with BeamNG
        mgr.start(telemetry_type="beamng_outgauge")
        self.assertEqual(mgr.active_telemetry_type, "beamng_outgauge")
        self.assertIsInstance(mgr.active_client, BeamNGTelemetry)

        # Replay BeamNG packet into active client
        with open(self.beamng_fixture_path, "rb") as f:
            mgr.active_client.process_packet(f.read())
        self.assertEqual(dev.display_text, "3") # 3rd gear on OLED

        # Test switch to DiRT
        mgr.start(telemetry_type="dirt_udp")
        self.assertEqual(mgr.active_telemetry_type, "dirt_udp")
        self.assertIsInstance(mgr.active_client, DirtRallyTelemetry)

        # Replay DiRT packet into active client
        with open(self.dirt_fixture_path, "rb") as f:
            mgr.active_client.process_packet(f.read())
        self.assertEqual(dev.display_text, "4") # 4th gear on OLED

        # Stop
        mgr.stop()
        self.assertFalse(mgr.enabled)


if __name__ == "__main__":
    unittest.main()
