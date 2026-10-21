"""
Fanatec Hardware Tuning Parameters and Preset Model.

Handles parameter normalization, hardware conversion functions,
and JSON preset loading/saving.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional
import json


@dataclass
class TuningProfile:
    name: str = "Default"
    slot: int = 1
    # Core Steering and Force Feedback
    sen: int = 900          # Steering angle in degrees (90 to 2520, 0 = Auto)
    ff: int = 100           # Overall Force Feedback strength (0 - 100%)
    ffs: int = 1            # FFB Scaling: 0 = Linear, 1 = Peak
    # Mechanical and Dynamic Damping
    ndp: int = 20           # Natural Damper (0 - 100%)
    nfr: int = 5            # Natural Friction (0 - 100%)
    nin: int = 0            # Natural Inertia (0 - 100%)
    # Filters and Detail
    int_filter: int = 3     # FFB Interpolation Filter (0 = Off, 1 - 20)
    fei: int = 100          # Force Effect Intensity (0 - 100%)
    # Game Force Multipliers
    for_mult: int = 100     # Constant Force multiplier (0 - 120%)
    spr_mult: int = 100     # Spring Effect multiplier (0 - 120%)
    dpr_mult: int = 100     # Damper Effect multiplier (0 - 120%)
    # Wheel and Pedals Feedback
    sho: int = 100          # Wheel vibration / shock (0 = Off, 10 - 100%)
    bli: int = 0            # Brake Level Indicator (0 = Off, 1 - 100%)
    brf: int = 50           # Brake Force for load-cell pedals (0 - 100%)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TuningProfile":
        valid_fields = cls.__dataclass_fields__
        coerced = {}
        for k, v in data.items():
            if k in valid_fields:
                f_type = valid_fields[k].type
                try:
                    if f_type is str or f_type == "str":
                        coerced[k] = str(v)
                    else:
                        coerced[k] = int(v)
                except (ValueError, TypeError):
                    coerced[k] = valid_fields[k].default
        return cls(**coerced)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, text: str) -> "TuningProfile":
        return cls.from_dict(json.loads(text))


# Attribute metadata for GUI generators
TUNING_METADATA = [
    {
        "id": "sen",
        "reg": "SEN",
        "name": "Sensitivity (SEN)",
        "desc": "Maximum wheel rotation angle in degrees. 0 sets Auto (game-matched).",
        "min": 0,
        "max": 2520,
        "step": 10,
        "unit": "°",
        "default": 900,
        "category": "Steering and Output"
    },
    {
        "id": "ff",
        "reg": "FF",
        "name": "Force Feedback Strength (FF)",
        "desc": "Master motor output strength of the wheelbase.",
        "min": 0,
        "max": 100,
        "step": 1,
        "unit": "%",
        "default": 100,
        "category": "Steering and Output"
    },
    {
        "id": "ffs",
        "reg": "FFS",
        "name": "Force Feedback Scaling (FFS)",
        "desc": "Linear mode prevents clipping; Peak mode delivers maximum instant torque.",
        "type": "toggle",
        "options": ["Linear", "Peak"],
        "default": 1,
        "category": "Steering and Output"
    },
    {
        "id": "ndp",
        "reg": "NDP",
        "name": "Natural Damper (NDP)",
        "desc": "Adds rotational resistance to reduce oscillations and steering flutter on straights.",
        "min": 0,
        "max": 100,
        "step": 1,
        "unit": "%",
        "default": 20,
        "category": "Damping and Inertia"
    },
    {
        "id": "nfr",
        "reg": "NFR",
        "name": "Natural Friction (NFR)",
        "desc": "Simulates mechanical steering rack and tire scrub resistance.",
        "min": 0,
        "max": 100,
        "step": 1,
        "unit": "%",
        "default": 5,
        "category": "Damping and Inertia"
    },
    {
        "id": "nin",
        "reg": "NIN",
        "name": "Natural Inertia (NIN)",
        "desc": "Simulates additional steering column mass/weight.",
        "min": 0,
        "max": 100,
        "step": 1,
        "unit": "%",
        "default": 0,
        "category": "Damping and Inertia"
    },
    {
        "id": "int_filter",
        "reg": "INT",
        "name": "FFB Interpolation Filter (INT)",
        "desc": "Smooths out low-frequency game FFB signals (e.g. 60Hz physics ticks).",
        "min": 0,
        "max": 20,
        "step": 1,
        "unit": "",
        "default": 3,
        "category": "Filters and Effects"
    },
    {
        "id": "fei",
        "reg": "FEI",
        "name": "Force Effect Intensity (FEI)",
        "desc": "Controls the sharpness of transient curb strikes and road surface vibrations.",
        "min": 0,
        "max": 100,
        "step": 5,
        "unit": "%",
        "default": 100,
        "category": "Filters and Effects"
    },
    {
        "id": "for_mult",
        "reg": "FOR",
        "name": "Game Force Effect (FOR)",
        "desc": "Multiplier for game constant force effects.",
        "min": 0,
        "max": 120,
        "step": 10,
        "unit": "%",
        "default": 100,
        "category": "Game Multipliers"
    },
    {
        "id": "spr_mult",
        "reg": "SPR",
        "name": "Game Spring Effect (SPR)",
        "desc": "Multiplier for game centering spring effects.",
        "min": 0,
        "max": 120,
        "step": 10,
        "unit": "%",
        "default": 100,
        "category": "Game Multipliers"
    },
    {
        "id": "dpr_mult",
        "reg": "DPR",
        "name": "Game Damper Effect (DPR)",
        "desc": "Multiplier for game velocity damping effects.",
        "min": 0,
        "max": 120,
        "step": 10,
        "unit": "%",
        "default": 100,
        "category": "Game Multipliers"
    },
    {
        "id": "sho",
        "reg": "SHO",
        "name": "Wheel Vibration / Shock (SHO)",
        "desc": "Controls the vibration intensity of motors inside the wheel handles.",
        "min": 0,
        "max": 100,
        "step": 10,
        "unit": "%",
        "default": 100,
        "category": "Hardware Feedback"
    },
    {
        "id": "bli",
        "reg": "BLI",
        "name": "Brake Level Indicator (BLI)",
        "desc": "Triggers pedal/wheel vibration when brake pedal reaches this threshold (0 = Off).",
        "min": 0,
        "max": 100,
        "step": 5,
        "unit": "%",
        "default": 0,
        "category": "Hardware Feedback"
    },
    {
        "id": "brf",
        "reg": "BRF",
        "name": "Brake Force (BRF)",
        "desc": "Calibrates the pedal pressure required to reach 100% braking on load-cell pedals.",
        "min": 0,
        "max": 100,
        "step": 5,
        "unit": "%",
        "default": 50,
        "category": "Hardware Feedback"
    },
]
