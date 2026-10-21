"""
Wheel Calibration Settings and Persistence.
Maintains persistent steering center baseline offsets and calibration data.
"""

import os
import json
import logging
from dataclasses import dataclass, asdict

logger = logging.getLogger("fanalinux.calibration")

CALIBRATION_PATH = os.path.expanduser("~/.config/fanalinux/calibration.json")


@dataclass
class CalibrationSettings:
    center_raw: int = 32768  # 16-bit raw center position (factory default: 32768)

    @classmethod
    def from_dict(cls, data: dict) -> "CalibrationSettings":
        try:
            raw = int(float(data.get("center_raw", 32768)))
        except (ValueError, TypeError):
            raw = 32768
        return cls(center_raw=raw)


def load_calibration_settings() -> CalibrationSettings:
    """Load calibration settings from ~/.config/fanalinux/calibration.json."""
    if os.path.exists(CALIBRATION_PATH):
        try:
            with open(CALIBRATION_PATH, "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return CalibrationSettings.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load calibration settings: {e}")
    return CalibrationSettings()


def save_calibration_settings(settings: CalibrationSettings):
    """Save calibration settings to ~/.config/fanalinux/calibration.json."""
    try:
        os.makedirs(os.path.dirname(CALIBRATION_PATH), exist_ok=True)
        with open(CALIBRATION_PATH, "w") as f:
            json.dump(asdict(settings), f, indent=4)
        logger.info(f"Saved calibration settings: center_raw={settings.center_raw}")
    except Exception as e:
        logger.error(f"Failed to save calibration settings: {e}")
