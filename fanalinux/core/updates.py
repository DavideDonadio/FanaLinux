"""Best-effort update check against GitHub releases.

Network failures degrade to (None, None); never raises.
"""

import json
import os
import urllib.request

REPO = "DavideDonadio/fanalinux"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
STATE_PATH = os.path.expanduser("~/.config/fanalinux/update_state.json")


def get_local_version() -> str:
    from fanalinux import __version__
    return __version__


def _parse(tag: str) -> tuple:
    cleaned = tag.strip().lstrip("vV")
    parts = []
    for piece in cleaned.split("."):
        digits = "".join(c for c in piece if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer(local: str, remote: str) -> bool:
    """True if remote version tag is newer than local (pure, offline-testable)."""
    a, b = _parse(local), _parse(remote)
    width = max(len(a), len(b))
    return b + (0,) * (width - len(b)) > a + (0,) * (width - len(a))


def check_latest(timeout: int = 8):
    """Return (tag, url) of the latest GitHub release, or (None, None)."""
    try:
        req = urllib.request.Request(API_URL, headers={"User-Agent": "fanalinux"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = data.get("tag_name")
        url = data.get("html_url")
        if tag:
            return tag, url
    except Exception:
        pass
    return None, None


def load_update_state() -> dict:
    """Last known release from a previous check ({} when never checked)."""
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and data.get("tag"):
                return data
    except Exception:
        pass
    return {}


def save_update_state(tag: str, url: str) -> None:
    """Persist latest release so the update button survives restarts."""
    try:
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump({"tag": tag, "url": url}, f, indent=2)
    except Exception:
        pass
