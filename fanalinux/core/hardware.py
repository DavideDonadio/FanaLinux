"""
Hardware Profile Detection & Management for Fanatec Wheelbases and Steering Wheels.
Handles auto-detection from USB Vendor/Product IDs and user-selected rim hardware.
"""

import os
import json
import logging
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional

logger = logging.getLogger("fanalinux.hardware")

CONFIG_PATH = os.path.expanduser("~/.config/fanalinux/hardware.json")

# Known Wheelbases by USB Product ID (Vendor ID always 0x0EB7)
KNOWN_BASES: Dict[int, Dict[str, str]] = {
    0x0020: {
        "name": "Fanatec CSL DD",
        "desc": "Direct Drive Wheel Base (PC Mode, Red LED)",
        "image": "csl_dd.png",
    },
    0x0021: {
        "name": "Fanatec Gran Turismo DD Pro",
        "desc": "Direct Drive Wheel Base (PC Mode, Red LED)",
        "image": "csl_dd.png",
    },
    0x0001: {
        "name": "Fanatec Podium Wheel Base DD1",
        "desc": "Direct Drive Wheel Base (High-Torque)",
        "image": "csl_dd.png",
    },
    0x0002: {
        "name": "Fanatec Podium Wheel Base DD2",
        "desc": "Direct Drive Wheel Base (High-Torque)",
        "image": "csl_dd.png",
    },
    0x0004: {
        "name": "Fanatec ClubSport Wheel Base V2.5",
        "desc": "Belt-Driven Wheel Base",
        "image": "csl_dd.png",
    },
    0x0005: {
        "name": "Fanatec CSL Elite Wheel Base",
        "desc": "Belt-Driven Wheel Base",
        "image": "csl_dd.png",
    },
}

# Known Steering Wheel Rims with Dedicated Image Assets
KNOWN_RIMS = [
    {
        "id": "formula_v2",
        "name": "ClubSport Steering Wheel F1 Esports V2 / Formula V2",
        "subtitle": "ClubSport Steering Wheel F1 Esports V2 (Alcantara, RevLEDs)",
        "image": "formula_v2.png",
        "active_buttons": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 22, 25, 26, 28],
        "button_count": 16,
        "has_dpad": True,
    },
    {
        "id": "formula_v25",
        "name": "ClubSport Steering Wheel Formula V2.5",
        "subtitle": "ClubSport Steering Wheel Formula V2.5 (15 Multi-Color LEDs)",
        "image": "formula_v25.png",
        "button_count": 28,
        "has_dpad": True,
    },
    {
        "id": "formula_v25x",
        "name": "ClubSport Steering Wheel Formula V2.5 X",
        "subtitle": "ClubSport Steering Wheel Formula V2.5 X (Alcantara Grips)",
        "image": "formula_v25x.png",
        "button_count": 28,
        "has_dpad": True,
    },
    {
        "id": "formula_v3",
        "name": "ClubSport Steering Wheel Formula V3",
        "subtitle": "ClubSport Steering Wheel Formula V3 (2.7\" OLED, Magnetic Paddles)",
        "image": "formula_v3.png",
        "button_count": 28,
        "has_dpad": True,
    },
    {
        "id": "mclaren_gt3",
        "name": "CSL Elite Steering Wheel McLaren GT3 V2",
        "subtitle": "CSL Elite Steering Wheel McLaren GT3 V2 (Dual Clutch)",
        "image": "mclaren_gt3.png",
        "button_count": 20,
        "has_dpad": True,
    },
    {
        "id": "csl_gt3",
        "name": "CSL Steering Wheel GT3",
        "subtitle": "CSL Steering Wheel GT3 (Dual Analog Clutches)",
        "image": "csl_gt3.png",
        "button_count": 18,
        "has_dpad": True,
    },
    {
        "id": "bmw_gt3",
        "name": "Podium Steering Wheel BMW M4 GT3",
        "subtitle": "Podium Steering Wheel BMW M4 GT3 (Carbon Chassis)",
        "image": "bmw_gt3.png",
        "button_count": 24,
        "has_dpad": True,
    },
    {
        "id": "porsche_gt3",
        "name": "Podium Steering Wheel Porsche 911 GT3 R",
        "subtitle": "Podium Steering Wheel Porsche 911 GT3 R (Leather)",
        "image": "porsche_gt3.png",
        "button_count": 24,
        "has_dpad": True,
    },
    {
        "id": "porsche_vision_gt",
        "name": "CSL Elite Steering Wheel Porsche Vision GT",
        "subtitle": "CSL Elite Steering Wheel Porsche Vision GT (Concept Livery)",
        "image": "porsche_vision_gt.png",
        "button_count": 20,
        "has_dpad": True,
    },
    {
        "id": "endurance_gt3",
        "name": "Podium Steering Wheel GT3 Endurance",
        "subtitle": "Podium Steering Wheel GT3 Endurance (Button Module Endurance)",
        "image": "endurance_gt3.png",
        "button_count": 24,
        "has_dpad": True,
    },
    {
        "id": "csl_wrc",
        "name": "CSL Elite Steering Wheel WRC",
        "subtitle": "CSL Elite Steering Wheel WRC (Alcantara, Orange Accents)",
        "image": "csl_wrc.png",
        "button_count": 12,
        "has_dpad": True,
    },
    {
        "id": "csl_p1_v2",
        "name": "CSL Steering Wheel P1 V2",
        "subtitle": "CSL Steering Wheel P1 V2 (RevStrips, Lightweight)",
        "image": "csl_p1_v2.png",
        "button_count": 12,
        "has_dpad": True,
    },
    {
        "id": "round_rs",
        "name": "ClubSport Steering Wheel RS (Round)",
        "subtitle": "ClubSport Steering Wheel RS (Leather, RevLEDs)",
        "image": "round_rs.png",
        "button_count": 16,
        "has_dpad": True,
    },
    {
        "id": "drift_v2",
        "name": "ClubSport Steering Wheel Drift V2",
        "subtitle": "ClubSport Steering Wheel Drift V2 (Deep Dish Leather)",
        "image": "drift_v2.png",
        "button_count": 16,
        "has_dpad": True,
    },
    {
        "id": "sparco_gt",
        "name": "ClubSport Steering Wheel SPARCO® GT",
        "subtitle": "ClubSport Steering Wheel SPARCO® GT (Official Sparco Suede)",
        "image": "sparco_gt.png",
        "button_count": 16,
        "has_dpad": True,
    },
]


@dataclass
class HardwareConfig:
    rim_id: str = "formula_v2"


def load_hardware_config() -> HardwareConfig:
    """Load hardware configuration from ~/.config/fanalinux/hardware.json."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
                return HardwareConfig(**data)
        except Exception as e:
            logger.warning(f"Could not load hardware config: {e}")
    return HardwareConfig(rim_id="formula_v2")


def save_hardware_config(config: HardwareConfig):
    """Save hardware configuration to ~/.config/fanalinux/hardware.json."""
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(asdict(config), f, indent=4)
        logger.info(f"Saved hardware config: rim_id={config.rim_id}")
    except Exception as e:
        logger.error(f"Could not save hardware config: {e}")


def get_base_info(product_id: int) -> Dict[str, str]:
    """Retrieve wheelbase model name and image by USB Product ID."""
    return KNOWN_BASES.get(product_id, {
        "name": f"Fanatec Wheelbase (PID 0x{product_id:04X})",
        "desc": f"USB Product ID: 0x{product_id:04X}",
        "image": "csl_dd.png",
    })


def get_rim_info(rim_id: str) -> Dict[str, str]:
    """Retrieve steering wheel rim details by rim ID."""
    for rim in KNOWN_RIMS:
        if rim["id"] == rim_id:
            return rim
    return KNOWN_RIMS[0]
