"""One-click install of the hid-fanatecff kernel FFB driver.

Only the privileged step runs as root (via pkexec, reusing the upstream
install.sh verbatim); cloning and checks run as the normal user.
"""

import logging
import os
import shlex
import shutil
import subprocess

logger = logging.getLogger("fanalinux.driver_setup")

REPO_URL = "https://github.com/gotzl/hid-fanatecff"
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "fanalinux", "hid-fanatecff")
LOG_PATH = os.path.join(os.path.expanduser("~"), ".cache", "fanalinux", "driver-install.log")

BUILD_DEPS = ("git", "make", "gcc", "dkms")


def missing_deps() -> list:
    """Build tools absent from PATH plus kernel headers (names for the hint)."""
    missing = [d for d in BUILD_DEPS if shutil.which(d) is None]
    headers = f"/lib/modules/{os.uname().release}/build"
    if not os.path.isdir(headers):
        missing.append("kernel-headers")
    return missing


def dep_install_hint() -> str:
    """Distro one-liner providing the build dependencies."""
    if shutil.which("dnf"):
        return "sudo dnf install kernel-devel gcc make joystick git dkms"
    if shutil.which("apt"):
        return "sudo apt install linux-headers-generic build-essential joystick dkms"
    if shutil.which("pacman"):
        return "sudo pacman -S linux-headers base-devel joyutils dkms"
    return "install: git, make, gcc, dkms and your kernel headers"


def driver_module_present() -> bool:
    """True when hid-fanatec is installed (works without the wheel connected)."""
    if os.path.isdir("/sys/module/hid_fanatec"):
        return True
    try:
        r = subprocess.run(["modinfo", "hid-fanatec"], capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def secure_boot_on() -> bool:
    try:
        out = subprocess.run(["mokutil", "--sb-state"], capture_output=True,
                             text=True, timeout=10).stdout.lower()
        return "enabled" in out
    except Exception:
        return False


def run_install() -> tuple:
    """Clone/update the driver repo and run its install.sh as root.

    Returns (ok, tail): ok True when DKMS reports success, tail the last
    log lines for display. Full output goes to LOG_PATH.
    """
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "w") as log:
        def emit(msg):
            log.write(msg + "\n")
            log.flush()

        if shutil.which("pkexec") is None:
            return False, "pkexec not found: no graphical privilege prompt available"
        if not shutil.which("git"):
            return False, "git not found"

        if os.path.isdir(os.path.join(CACHE_DIR, ".git")):
            emit(f"Updating {CACHE_DIR}")
            r = subprocess.run(["git", "-C", CACHE_DIR, "pull", "--ff-only"],
                               capture_output=True, text=True, timeout=300)
        else:
            emit(f"Cloning {REPO_URL}")
            r = subprocess.run(["git", "clone", "--depth", "1", REPO_URL, CACHE_DIR],
                               capture_output=True, text=True, timeout=300)
        emit(r.stdout + r.stderr)
        if r.returncode != 0:
            return False, f"git failed (see {LOG_PATH})"

        # Upstream install.sh must run as root; udev reload needs root too,
        # so both go through the single pkexec authentication.
        root_cmd = (f"cd {shlex.quote(CACHE_DIR)} && bash install.sh"
                    " && udevadm control --reload-rules"
                    " && udevadm trigger --subsystem-match=hidraw")
        emit("Running upstream install.sh as root")
        r = subprocess.run(["pkexec", "bash", "-c", root_cmd],
                           capture_output=True, text=True, timeout=900)
        emit(r.stdout + r.stderr)
        tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-12:])
        if r.returncode != 0:
            if "dismissed" in (r.stderr or "").lower() or r.returncode in (126, 127):
                return False, "Administrator authentication cancelled"
            return False, tail or f"install failed (see {LOG_PATH})"
        return True, tail
