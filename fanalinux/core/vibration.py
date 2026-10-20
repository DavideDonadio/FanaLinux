"""
Fanatec Telemetry-Driven Vibration & Haptics Configuration Model.
Matches Fanatec App / FanaLab vibration settings.
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any
import os
import json
import logging

logger = logging.getLogger("fanalinux.vibration")

CONFIG_DIR = os.path.expanduser("~/.config/fanalinux")
VIBRATION_CONFIG_PATH = os.path.join(CONFIG_DIR, "vibration.json")


@dataclass
class VibrationSettings:
    # 1. Braking & Engine
    abs_enabled: bool = True
    abs_strength: int = 5          # 1 - 10
    abs_duration: int = 80         # ms (20 - 300ms)

    engine_enabled: bool = False
    engine_strength: int = 4       # 1 - 10
    engine_initial: int = 0        # % (0 - 100%)

    rev_enabled: bool = True
    rev_strength: int = 5          # 1 - 10
    rev_threshold: float = 96.0    # % (80.0 - 100.0%)

    # 2. Suspension & Chassis Dynamics
    suspension_enabled: bool = False
    suspension_strength: int = 5   # 1 - 10
    suspension_threshold: float = 1.2  # % (0.1 - 50.0%)

    understeer_enabled: bool = False
    understeer_strength: int = 8   # 1 - 10
    understeer_friction_limit: float = 6.3  # degrees

    oversteer_enabled: bool = False
    oversteer_strength: int = 2    # 1 - 10
    oversteer_friction_limit: float = 0.0   # degrees

    # 3. Traction & Tire Grip
    tc_enabled: bool = True
    tc_strength: int = 4           # 1 - 10
    tc_duration: int = 90          # ms (20 - 300ms)

    wheel_lock_enabled: bool = False
    wheel_lock_strength: int = 6   # 1 - 10

    wheel_spin_enabled: bool = False
    wheel_spin_strength: int = 2   # 1 - 10

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VibrationSettings":
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


def load_vibration_settings() -> VibrationSettings:
    """Load user vibration preferences from disk or return factory defaults."""
    if os.path.exists(VIBRATION_CONFIG_PATH):
        try:
            with open(VIBRATION_CONFIG_PATH, "r") as f:
                data = json.load(f)
                return VibrationSettings.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load {VIBRATION_CONFIG_PATH}: {e}, using defaults")
    return VibrationSettings()


def save_vibration_settings(settings: VibrationSettings):
    """Save user vibration preferences to disk."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(VIBRATION_CONFIG_PATH, "w") as f:
            json.dump(settings.to_dict(), f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save vibration settings to {VIBRATION_CONFIG_PATH}: {e}")
