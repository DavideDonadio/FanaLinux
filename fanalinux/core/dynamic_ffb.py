"""
Dynamic Force Feedback (Damper Overlay) Settings and Persistence.
Replicates FanaLab's 'FFB Dynamique' / 'Surcouche d'Amortissement':
- Speed-Sensitive Dynamic Damper
- Reverse Driving Safety Damper
"""

import os
import json
from dataclasses import dataclass, asdict

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


def load_dynamic_ffb_settings() -> DynamicFFBSettings:
    """Load dynamic FFB settings from ~/.config/fanalinux/dynamic_ffb.json."""
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r") as f:
                data = json.load(f)
                return DynamicFFBSettings(**data)
        except Exception:
            pass
    return DynamicFFBSettings()


def save_dynamic_ffb_settings(settings: DynamicFFBSettings):
    """Save dynamic FFB settings to ~/.config/fanalinux/dynamic_ffb.json."""
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w") as f:
        json.dump(asdict(settings), f, indent=4)
