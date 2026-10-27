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


def _dkms_versions() -> list:
    """Versions DKMS reports as installed (authoritative over /usr/src)."""
    try:
        r = subprocess.run(["dkms", "status", "hid-fanatec"],
                           capture_output=True, text=True, timeout=15)
    except Exception:
        return []
    versions = []
    for line in (r.stdout or "").splitlines():
        head, _, state = line.partition(":")
        if state.strip() != "installed":
            continue
        name, _, ver = head.partition("/")
        ver = ver.split(",")[0].strip()
        if name.strip() == "hid-fanatec" and ver and ver not in versions:
            versions.append(ver)
    return versions


def installed_version() -> str | None:
    """Installed driver version: DKMS status first, /usr/src glob as fallback.
    Result is cached (dkms spawns a slow subprocess): refresh at most every
    two minutes, or immediately after invalidate_installed_version()."""
    import glob
    import time
    now = time.monotonic()
    cached_at = getattr(installed_version, "_at", 0)
    if now - cached_at < 120 and hasattr(installed_version, "_val"):
        return installed_version._val
    versions = _dkms_versions()
    ver = versions[0] if versions else None
    if ver is None:
        dirs = glob.glob("/usr/src/hid-fanatec-*")
        if dirs:
            # Numeric version order, not lexicographic (0.2.10 beats 0.2.9).
            best = max(dirs, key=lambda d: _version_key(os.path.basename(d).removeprefix("hid-fanatec-")))
            ver = os.path.basename(best).removeprefix("hid-fanatec-") or None
    installed_version._val = ver
    installed_version._at = now
    return ver


def invalidate_installed_version():
    """Drop the installed_version() cache (call after driver install/update)."""
    if hasattr(installed_version, "_at"):
        installed_version._at = 0


def _version_key(version: str) -> tuple:
    key = []
    for part in version.split("-")[0].lstrip("v").split("."):
        digits = "".join(c for c in part if c.isdigit())
        key.append(int(digits) if digits else 0)
    return tuple(key)


def is_upstream_newer(installed: str | None, upstream: str | None) -> bool:
    """True when the upstream tag is newer (unparseable installed counts as older)."""
    if not upstream:
        return False
    if not installed:
        return True
    return _version_key(upstream) > _version_key(installed)


def latest_upstream_version(timeout: int = 8) -> str | None:
    """Latest upstream tag via GitHub API (None on any failure)."""
    try:
        import json
        import urllib.request
        req = urllib.request.Request(
            "https://api.github.com/repos/gotzl/hid-fanatecff/releases/latest",
            headers={"User-Agent": "fanalinux"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            tag = json.load(resp).get("tag_name")
        return tag.strip() if tag else None
    except Exception:
        return None


def secure_boot_on() -> bool:
    try:
        out = subprocess.run(["mokutil", "--sb-state"], capture_output=True,
                             text=True, timeout=10).stdout.lower()
        return "enabled" in out
    except Exception:
        return False


def run_install(update: bool = False) -> tuple:
    """Clone/update the driver repo and run its install.sh as root.
    Any already-installed DKMS module is removed first (upstream refuses
    reinstalls); update=True additionally starts from a fresh full clone.

    Returns (ok, tail): ok True when DKMS reports success, tail the last
    log lines for display. Full output goes to LOG_PATH.
    """
    if update:
        shutil.rmtree(CACHE_DIR, ignore_errors=True)
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
            # Shallow clones cannot pull; fetch + reset works on any depth.
            r = subprocess.run(["git", "-C", CACHE_DIR, "fetch", "--depth", "1",
                                "origin", "master"],
                               capture_output=True, text=True, timeout=300)
            if r.returncode == 0:
                r = subprocess.run(["git", "-C", CACHE_DIR, "reset", "--hard",
                                    "FETCH_HEAD"],
                                   capture_output=True, text=True, timeout=120)
        else:
            # A non-repo cache dir is junk from an older release: replace it.
            shutil.rmtree(CACHE_DIR, ignore_errors=True)
            emit(f"Cloning {REPO_URL}")
            # Full clone: upstream version detection needs the tags.
            r = subprocess.run(["git", "clone", REPO_URL, CACHE_DIR],
                               capture_output=True, text=True, timeout=300)
        emit(r.stdout + r.stderr)
        if r.returncode != 0:
            return False, f"git failed (see {LOG_PATH})"
        # Never install an unversioned tree: without tags, upstream fingerprints
        # the build as "unknown" and version checks become meaningless.
        # Stale clones (e.g. from the first shallow-clone releases) carry no
        # tags even after fetch: start over with a full clone instead of aborting.
        r = subprocess.run(["git", "-C", CACHE_DIR, "describe", "--tags"],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            emit("No tags in cache, re-cloning full tree")
            shutil.rmtree(CACHE_DIR, ignore_errors=True)
            r = subprocess.run(["git", "clone", REPO_URL, CACHE_DIR],
                               capture_output=True, text=True, timeout=300)
            emit(r.stdout + r.stderr)
            if r.returncode != 0:
                return False, f"git failed (see {LOG_PATH})"
            r = subprocess.run(["git", "-C", CACHE_DIR, "describe", "--tags"],
                               capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                return False, "Cannot determine driver version from the clone; aborting"
        emit(f"Driver tree version: {r.stdout.strip()}")

        # The privileged step executes a script from a user-writable cache:
        # refuse when the checkout points anywhere but upstream.
        r = subprocess.run(["git", "-C", CACHE_DIR, "remote", "get-url", "origin"],
                           capture_output=True, text=True, timeout=30)
        origin = (r.stdout or "").strip().rstrip("/")
        if origin.endswith(".git"):
            origin = origin[:-4]
        if r.returncode != 0 or origin != REPO_URL:
            return False, f"Refusing: cache origin is {origin or 'unknown'}, not {REPO_URL}"

        # Upstream install.sh must run as root; udev reload needs root too,
        # so both go through the single pkexec authentication.
        # SUDO_USER lets their script fingerprint the real version instead of
        # "unknown"; the tree already carries tags from the full clone.
        import getpass
        try:
            invoking_user = os.environ.get("SUDO_USER") or os.environ.get("USER") or getpass.getuser()
        except Exception:
            invoking_user = ""
        # Upstream install.sh refuses when DKMS already lists the module, so any
        # existing entries are removed first (no-op on a clean system).
        # Upstream install.sh refuses when DKMS already lists the module, so any
        # existing entries are removed first (no-op on a clean system). If the
        # new build then fails, the same privileged script reinstalls the old
        # sources from /usr/src before reporting failure.
        dkms_dir = "/var/lib/dkms/hid-fanatec"
        try:
            old_versions = sorted(os.listdir(dkms_dir)) if os.path.isdir(dkms_dir) else []
        except OSError:
            old_versions = []
        removals = " && ".join(
            f"dkms remove -m hid-fanatec -v {shlex.quote(v)} --all" for v in old_versions)
        # Trust boundary: the cache is user-writable, so root never executes
        # from it. Pin the verified HEAD before auth; the privileged script
        # copies the tree to a root-owned stage and aborts unless origin, HEAD
        # and clean status all match. Any post-check tampering changes the hash
        # or dirties the tree, so it cannot slip through the auth delay.
        head = subprocess.run(["git", "-C", CACHE_DIR, "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=30)
        expected_head = (head.stdout or "").strip()
        if head.returncode != 0 or not expected_head:
            return False, "Cannot fingerprint the driver tree; aborting"
        stage_check = (f"[ \"$(git -C \"$STAGE\" rev-parse HEAD)\" = {shlex.quote(expected_head)} ]"
                       f" && [ -z \"$(git -C \"$STAGE\" status --porcelain)\" ]"
                       f" && [ \"$(git -C \"$STAGE\" remote get-url origin)\" = {shlex.quote(REPO_URL)}"
                       f" -o \"$(git -C \"$STAGE\" remote get-url origin)\" = {shlex.quote(REPO_URL + '.git')} ]")
        install_cmd = ("STAGE=$(mktemp -d /root/.fanalinux-driver-XXXXXX)"
                       " && trap 'rm -rf \"$STAGE\"' EXIT"
                       f" && cp -a {shlex.quote(CACHE_DIR)}/. \"$STAGE\"/"
                       " && cd \"$STAGE\""
                       f" && {stage_check}"
                       " && bash install.sh")
        post = "udevadm control --reload-rules && udevadm trigger --subsystem-match=hidraw"
        if removals and old_versions:
            rollback = " && ".join(
                f"dkms install -m hid-fanatec -v {shlex.quote(v)} --all" for v in old_versions)
            root_cmd = (f"{removals} && (({install_cmd} && {post}) || "
                        f"{{ echo FANALINUX_ROLLBACK; {rollback}; exit 1; }})")
        elif removals:
            root_cmd = f"{removals} && {install_cmd} && {post}"
        else:
            root_cmd = f"{install_cmd} && {post}"
        pkexec_cmd = ["pkexec"]
        if invoking_user:
            pkexec_cmd += ["env", f"SUDO_USER={invoking_user}"]
        pkexec_cmd += ["bash", "-c", root_cmd]
        emit("Running upstream install.sh as root")
        r = subprocess.run(pkexec_cmd,
                           capture_output=True, text=True, timeout=900)
        emit(r.stdout + r.stderr)
        tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-12:])
        if r.returncode != 0:
            if "dismissed" in (r.stderr or "").lower() or r.returncode in (126, 127):
                return False, "Administrator authentication cancelled"
            msg = tail or f"install failed (see {LOG_PATH})"
            if old_versions and "FANALINUX_ROLLBACK" in (r.stdout or ""):
                # Same-script rollback ran: verify the old module is back.
                restored = sorted(set(_dkms_versions()) & set(old_versions))
                if restored:
                    msg += f"\nPrevious driver {restored[0]} was restored."
                else:
                    msg += ("\nPrevious driver could NOT be restored: "
                            "reinstall it manually before rebooting.")
            return False, msg
        return True, tail
