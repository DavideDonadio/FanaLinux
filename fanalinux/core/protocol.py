"""
Fanatec USB HID Protocol Definitions and Constants.

Reverse-engineered specifications for Fanatec Wheelbases, Rims, and Peripherals.
Clean-room implementation designed for Linux interoperability.
"""


# USB Identifiers
FANATEC_VENDOR_ID = 0x0EB7

# Known Wheelbase Product IDs (PID)
PID_CSL_DD = 0x0020
PID_DD_PRO = 0x0021
PID_PODIUM_DD1 = 0x0001
PID_PODIUM_DD2 = 0x0002
PID_CLUBSPORT_V2 = 0x0003
PID_CLUBSPORT_V25 = 0x0004
PID_CSL_ELITE = 0x0005
PID_CSL_ELITE_PS4 = 0x0006

# Report IDs
REPORT_ID_STD_INPUT = 0x01       # 64 bytes: joystick, 16-bit axes, buttons
REPORT_ID_ALT_INPUT = 0x02       # Alternative input layout
REPORT_ID_DIRECT_DRIVE = 0xFF    # 64 bytes: Tuning menu, LED MC, vendor telemetry
REPORT_ID_LEGACY_CMD = 0x01      # 7 bytes payload for legacy commands

# DirectDrive Sub-Commands (Report ID 0xFF)
CMD_LED_MC = 0x01                # Multicolor LED control (RPM or Flags)
CMD_TUNING = 0x03                # Tuning menu read/write

# Multicolor LED Sub-types
LED_SUB_RPM = 0x00               # 9 multicolor RevLEDs
LED_SUB_FLAGS = 0x01             # 6 multicolor Flag LEDs (3 left, 3 right)

# Legacy Command Prefixes (Report ID 0x01)
CMD_INIT = [0xF5, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
CMD_DISPLAY_PREFIX = [0xF8, 0x09, 0x01, 0x02]
CMD_LEGACY_LED_PREFIX = [0xF8, 0x09, 0x08]
CMD_LEGACY_RUMBLE_PREFIX = [0xF8, 0x09, 0x01, 0x03]

# Tuning Parameter Register Offsets (Within CMD_TUNING Report 0xFF)
# Buffer: [0xFF, 0x03, 0x00, ...] -> register offset is index + 1
TUNING_REGISTERS = {
    "SLOT": 0x02,   # Profile Slot (1 to 5)
    "SEN":  0x03,   # Sensitivity / Steering Range
    "FF":   0x04,   # Force Feedback Strength (0 - 100%)
    "SHO":  0x05,   # Shock / Grip Vibration (0 - 100%)
    "BLI":  0x06,   # Brake Level Indicator (0 - 100%)
    "FFS":  0x07,   # FFB Scaling (0 = Linear, 1 = Peak)
    "DRI":  0x09,   # Drift Mode (-5 to 3)
    "FOR":  0x0A,   # Force Effect Strength (0 - 120%)
    "SPR":  0x0B,   # Spring Effect Strength (0 - 120%)
    "DPR":  0x0C,   # Damper Effect Strength (0 - 120%)
    "NDP":  0x0D,   # Natural Damper (0 - 100%)
    "NFR":  0x0E,   # Natural Friction (0 - 100%)
    "BRF":  0x10,   # Brake Force / Load Cell Sensitivity (0 - 100%)
    "FEI":  0x11,   # Force Effect Intensity (0 - 100%)
    "ACP":  0x13,   # Analogue Paddle Mode (1 to 4)
    "INT":  0x14,   # FFB Interpolation Filter (0 - 20)
    "NIN":  0x15,   # Natural Inertia (0 - 100%)
    "FUL":  0x16,   # FullForce (0 - 100%)
}

# Steering Wheel Rim Type IDs (Extracted from wheel report)
RIM_TYPES: dict[int, str] = {
    0x0A: "ClubSport Steering Wheel Formula V2 / V2.5",
    0x0D: "Podium Button Module Endurance",
    0x0E: "CSL Elite Steering Wheel WRC",
    0x0F: "Podium Steering Wheel Bentley GT3",
    0x10: "Podium Steering Wheel BMW M4 GT3",
    0x11: "Podium Steering Wheel DD GT",
    0x12: "CSL Steering Wheel Universal Hub",
    0x13: "ClubSport Steering Wheel BMW V2",
    0x14: "ClubSport Steering Wheel RS",
    0x15: "ClubSport Universal Hub V2",
    0x16: "ClubSport Steering Wheel F1 Esports V2",
    0x17: "Podium Steering Wheel DD GT X",
    0x18: "CSL Elite Steering Wheel McLaren GT3 V2",
}

# 7-Segment / OLED character font mapping table
SEVEN_SEGMENT_MAP: dict[str, int] = {
    '': 0x00, ' ': 0x00,
    '0': 0x3F, '1': 0x06, '2': 0x5B, '3': 0x4F, '4': 0x66,
    '5': 0x6D, '6': 0x7D, '7': 0x07, '8': 0x7F, '9': 0x6F,
    'A': 0x77, 'B': 0x7C, 'C': 0x39, 'D': 0x5E, 'E': 0x79, 'F': 0x71,
    'G': 0x3D, 'H': 0x76, 'I': 0x06, 'J': 0x1E, 'K': 0x76, 'L': 0x38,
    'M': 0x15, 'N': 0x54, 'O': 0x5C, 'P': 0x73, 'Q': 0x67, 'R': 0x50,
    'S': 0x6D, 'T': 0x78, 'U': 0x1C, 'V': 0x2A, 'W': 0x2A, 'X': 0x76,
    'Y': 0x6E, 'Z': 0x5B,
    '-': 0x40, '_': 0x08, '.': 0x80
}


def encode_bgr565(r: int, g: int, b: int) -> int:
    """Encode 8-bit RGB color components into Fanatec BGR565 16-bit format."""
    r_clamped = max(0, min(255, r))
    g_clamped = max(0, min(255, g))
    b_clamped = max(0, min(255, b))
    return ((b_clamped >> 3) << 11) | ((g_clamped >> 2) << 5) | (r_clamped >> 3)


def text_to_segment_bytes(text: str) -> tuple[int, int, int]:
    """Convert up to a 3-character string into 7-segment / OLED font bytes."""
    cleaned = text.upper().ljust(3)[:3]
    return (
        SEVEN_SEGMENT_MAP.get(cleaned[0], 0x00),
        SEVEN_SEGMENT_MAP.get(cleaned[1], 0x00),
        SEVEN_SEGMENT_MAP.get(cleaned[2], 0x00),
    )
