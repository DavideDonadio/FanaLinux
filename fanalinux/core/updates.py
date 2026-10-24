"""Best-effort update check against GitHub releases.

Network failures degrade to (None, None); never raises.
"""

import json
import urllib.request

REPO = "DavideDonadio/fanalinux"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"


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
