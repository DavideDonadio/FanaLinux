"""
Preset Management for FanaLinux.
Handles listing, loading, saving, and auto-seeding baseline tuning presets.
"""

import os
import json
import shutil
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

from fanalinux.core.tuning import TuningProfile

logger = logging.getLogger("fanalinux.presets")

PRESETS_DIR = Path.home() / ".config" / "fanalinux" / "presets"
OLD_PRESETS_DIR = Path.home() / ".config" / "open-fanactrl" / "presets"

# Factory baseline profiles tailored for common sim setups on CSL DD
DEFAULT_FACTORY_PRESETS: Dict[str, Dict[str, Any]] = {
    "Default": {
        "name": "Default",
        "slot": 1,
        "sen": 900,
        "ff": 100,
        "ffs": 1,
        "ndp": 20,
        "nfr": 5,
        "nin": 0,
        "int_filter": 3,
        "fei": 100,
        "for_mult": 100,
        "spr_mult": 100,
        "dpr_mult": 100,
        "sho": 100,
        "brf": 50,
        "bli": 85
    },
    "Assetto Corsa - GT3": {
        "name": "Assetto Corsa - GT3",
        "slot": 1,
        "sen": 900,
        "ff": 100,
        "ffs": 1,
        "ndp": 25,
        "nfr": 5,
        "nin": 0,
        "int_filter": 2,
        "fei": 90,
        "for_mult": 100,
        "spr_mult": 100,
        "dpr_mult": 100,
        "sho": 100,
        "brf": 55,
        "bli": 80
    },
    "Assetto Corsa - Formula": {
        "name": "Assetto Corsa - Formula",
        "slot": 1,
        "sen": 450,
        "ff": 90,
        "ffs": 1,
        "ndp": 20,
        "nfr": 0,
        "nin": 0,
        "int_filter": 1,
        "fei": 100,
        "for_mult": 100,
        "spr_mult": 100,
        "dpr_mult": 100,
        "sho": 100,
        "brf": 60,
        "bli": 75
    },
    "F1 24": {
        "name": "F1 24",
        "slot": 1,
        "sen": 360,
        "ff": 85,
        "ffs": 1,
        "ndp": 15,
        "nfr": 0,
        "nin": 0,
        "int_filter": 1,
        "fei": 100,
        "for_mult": 100,
        "spr_mult": 100,
        "dpr_mult": 100,
        "sho": 100,
        "brf": 50,
        "bli": 75
    },
    "Drift": {
        "name": "Drift",
        "slot": 1,
        "sen": 900,
        "ff": 100,
        "ffs": 1,
        "ndp": 5,
        "nfr": 0,
        "nin": 0,
        "int_filter": 1,
        "fei": 100,
        "for_mult": 100,
        "spr_mult": 100,
        "dpr_mult": 100,
        "sho": 100,
        "brf": 40,
        "bli": 0
    },
    "Rally": {
        "name": "Rally",
        "slot": 1,
        "sen": 540,
        "ff": 90,
        "ffs": 0,
        "ndp": 35,
        "nfr": 10,
        "nin": 0,
        "int_filter": 3,
        "fei": 80,
        "for_mult": 100,
        "spr_mult": 100,
        "dpr_mult": 100,
        "sho": 100,
        "brf": 50,
        "bli": 0
    }
}


def init_default_presets() -> None:
    """Ensure preset directory exists and seed factory presets if not present."""
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    # Migrate from old directory if present
    if OLD_PRESETS_DIR.exists() and not any(PRESETS_DIR.iterdir()):
        for f in OLD_PRESETS_DIR.glob("*.json"):
            try:
                shutil.copy2(f, PRESETS_DIR / f.name)
            except Exception:
                pass

    for name, data in DEFAULT_FACTORY_PRESETS.items():
        filepath = PRESETS_DIR / f"{name}.json"
        if not filepath.exists():
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                logger.info(f"Seeded factory preset: {filepath}")
            except Exception as e:
                logger.error(f"Failed to seed factory preset {name}: {e}")


def list_presets() -> List[str]:
    """Return sorted list of preset names without extension."""
    init_default_presets()
    presets = []
    if PRESETS_DIR.exists():
        for f in PRESETS_DIR.glob("*.json"):
            presets.append(f.stem)
    presets.sort()
    # Ensure 'Default' is first if present
    if "Default" in presets:
        presets.remove("Default")
        presets.insert(0, "Default")
    return presets


def load_preset(name: str) -> Optional[TuningProfile]:
    """Load a tuning profile by name."""
    filepath = PRESETS_DIR / f"{name}.json"
    if not filepath.exists():
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            return TuningProfile.from_dict(data)
    except Exception as e:
        logger.error(f"Error loading preset '{name}': {e}")
        return None


def save_preset(name: str, profile: TuningProfile) -> bool:
    """Save a tuning profile to disk."""
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '_', '-')).rstrip()
    if not safe_name:
        safe_name = "Custom"
    profile.name = safe_name
    filepath = PRESETS_DIR / f"{safe_name}.json"
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(profile.to_json())
        return True
    except Exception as e:
        logger.error(f"Error saving preset '{safe_name}': {e}")
        return False


def delete_preset(name: str) -> bool:
    """Delete a user preset (cannot delete 'Default')."""
    if name == "Default":
        return False
    filepath = PRESETS_DIR / f"{name}.json"
    if filepath.exists():
        try:
            filepath.unlink()
            return True
        except Exception as e:
            logger.error(f"Error deleting preset '{name}': {e}")
    return False
