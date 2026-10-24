"""FanaLinux - Native Linux Control Panel and Telemetry Suite for Fanatec Hardware."""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("fanalinux")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
