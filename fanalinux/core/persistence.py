"""Shared JSON settings persistence: forgiving reads, atomic writes.

All app settings live under ~/.config/fanalinux/. Readers return None when the
file is missing or corrupt (callers fall back to defaults); writers go through
a temp file + os.replace so a crash mid-save never leaves a truncated file.
"""

import json
import logging
import os
import tempfile

logger = logging.getLogger("fanalinux.persistence")

CONFIG_DIR = os.path.expanduser("~/.config/fanalinux")


def load_json_dict(path) -> dict | None:
    """Read a JSON object from path. None when missing, corrupt, or not an object."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.warning(f"Ignoring corrupt settings file {path}: {e}")
        return None
    if not isinstance(data, dict):
        logger.warning(f"Ignoring non-object settings file {path}")
        return None
    return data


def save_json_dict(path, data: dict) -> bool:
    """Atomically write a JSON object to path (makedirs + tmp + replace)."""
    try:
        directory = os.path.dirname(os.path.abspath(str(path)))
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return True
    except Exception as e:
        logger.error(f"Could not save settings to {path}: {e}")
        return False
