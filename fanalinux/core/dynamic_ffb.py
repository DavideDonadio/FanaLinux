"""
Dynamic Force Feedback (Damper Overlay) Settings and Persistence.
Replicates FanaLab's 'FFB Dynamique' / 'Surcouche d'Amortissement':
- Speed-Sensitive Dynamic Damper
- Reverse Driving Safety Damper
"""

import logging
import os
from dataclasses import asdict, dataclass, fields

from fanalinux.core.persistence import load_json_dict, save_json_dict

logger = logging.getLogger("fanalinux.dynamic_ffb_settings")

SETTINGS_PATH = os.path.expanduser("~/.config/fanalinux/dynamic_ffb.json")


@dataclass
class DynamicFFBSettings:
    # Speed Sensitive Damper (Sensible à la vitesse)
    speed_sensitive_enabled: bool = True
    speed_threshold_min: int = 175     # km/h: speed at which extra damping begins fading in
    speed_threshold_max: int = 340     # km/h: speed at which damping reaches maximum
    damper_effect_range: int = 90      # degrees: steering window around center (+/- 45 deg)
    damper_effect_strength: int = 75   # 0 to 100%

    # Reverse Driving Safety Damper (Conduite en marche arrière)
    reverse_damper_enabled: bool = False
    reverse_damper_strength: int = 20  # 0 to 100%
    reverse_fade_in: int = 5           # 1 to 10 ramp intensity

    @classmethod
    def from_dict(cls, data: dict) -> "DynamicFFBSettings":
        valid_fields = {f.name: f for f in fields(cls)}
        coerced = {}
        for k, v in data.items():
            if k in valid_fields:
                f_type = valid_fields[k].type
                try:
                    if f_type is bool or f_type == "bool":
                        coerced[k] = bool(v) and str(v).strip().lower() not in ("0", "false", "no", "off", "")
                    elif f_type is float or f_type == "float":
                        coerced[k] = float(v)
                    else:
                        coerced[k] = int(float(v))
                except (ValueError, TypeError):
                    coerced[k] = valid_fields[k].default
        return cls(**coerced)


def load_dynamic_ffb_settings() -> DynamicFFBSettings:
    """Load dynamic FFB settings from ~/.config/fanalinux/dynamic_ffb.json."""
    data = load_json_dict(SETTINGS_PATH)
    if data is not None:
        return DynamicFFBSettings.from_dict(data)
    return DynamicFFBSettings()


def save_dynamic_ffb_settings(settings: DynamicFFBSettings):
    """Save dynamic FFB settings to ~/.config/fanalinux/dynamic_ffb.json."""
    if not save_json_dict(SETTINGS_PATH, asdict(settings)):
        logger.error("Error saving dynamic FFB settings to disk")
