#!/usr/bin/env bash
# ==============================================================================
# FanaLinux Installer
# Native Linux Control Panel & Telemetry Suite for Fanatec Hardware
# https://github.com/DavideDonadio/fanalinux
# ==============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${BOLD}${BLUE}====================================================${NC}"
echo -e "${BOLD}${GREEN}   FanaLinux Automated Installer (GTK4/Libadwaita)  ${NC}"
echo -e "${BOLD}${BLUE}====================================================${NC}\n"

# 1. Determine script directory (handles both git clone and curl execution)
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 2. Check Python Version (>= 3.10)
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}[ERROR] Python 3 is not installed. Please install Python 3.10 or newer.${NC}"
    exit 1
fi

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || [ "$PY_MAJOR" -eq 3 -a "$PY_MINOR" -lt 10 ]; then
    echo -e "${RED}[ERROR] Python 3.10 or newer is required (detected Python $PY_VER).${NC}"
    exit 1
fi
echo -e "${GREEN}[✓] Detected Python $PY_VER${NC}"

# 3. Check System Dependencies (PyGObject, GTK4, Libadwaita)
echo -e "${BLUE}[*] Checking GTK4 and Libadwaita bindings...${NC}"
MISSING_DEPS=0
python3 -c "import gi; gi.require_version('Gtk', '4.0'); gi.require_version('Adw', '1'); from gi.repository import Gtk, Adw" 2>/dev/null || MISSING_DEPS=1

if [ "$MISSING_DEPS" -eq 1 ]; then
    echo -e "${YELLOW}[!] Missing GTK4 or Libadwaita Python bindings.${NC}"
    echo -e "${BOLD}Please install the system packages for your distribution:${NC}\n"
    if [ -f /etc/fedora-release ]; then
        echo -e "  ${BOLD}Fedora:${NC} sudo dnf install -y python3-gobject libadwaita gtk4"
    elif [ -f /etc/arch-release ]; then
        echo -e "  ${BOLD}Arch Linux:${NC} sudo pacman -S --needed python-gobject libadwaita gtk4"
    elif [ -f /etc/debian_version ] || [ -f /etc/ubuntu-release ]; then
        echo -e "  ${BOLD}Ubuntu/Debian:${NC} sudo apt install -y python3-gi python3-gi-cairo gir1.2-adw-1 gir1.2-gtk-4.0"
    else
        echo -e "  Install python3-gobject, gtk4, and libadwaita from your package manager."
    fi
    echo ""
    read -rp "Would you like to continue anyway? (y/N): " CONT
    if [[ ! "$CONT" =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo -e "${GREEN}[✓] GTK4 and Libadwaita bindings verified!${NC}"
fi

# 4. Target Directories
INSTALL_DIR="$HOME/.local/share/fanalinux"
BIN_DIR="$HOME/.local/bin"
APP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor"

mkdir -p "$INSTALL_DIR" "$BIN_DIR" "$APP_DIR"

# 5. Create Isolated Virtual Environment (PEP 668 compliant across modern distros)
echo -e "${BLUE}[*] Setting up isolated application environment in $INSTALL_DIR...${NC}"
python3 -m venv --system-site-packages "$INSTALL_DIR/venv"

echo -e "${BLUE}[*] Installing FanaLinux and Python dependencies...${NC}"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip setuptools wheel --quiet
"$INSTALL_DIR/venv/bin/pip" install "$SRC_DIR" --quiet

# 6. Symlink Executable
ln -sf "$INSTALL_DIR/venv/bin/fanalinux" "$BIN_DIR/fanalinux"
echo -e "${GREEN}[✓] Installed CLI binary to $BIN_DIR/fanalinux${NC}"

# 7. Install Application Icons
echo -e "${BLUE}[*] Installing desktop icons...${NC}"
ICONS_SRC="$SRC_DIR/fanalinux/resources/icons"

if [ -d "$ICONS_SRC" ]; then
    for size in 48 64 128 256 512; do
        if [ -f "$ICONS_SRC/io.github.davidedonadio.fanalinux_${size}.png" ]; then
            DEST="$ICON_DIR/${size}x${size}/apps"
            mkdir -p "$DEST"
            cp "$ICONS_SRC/io.github.davidedonadio.fanalinux_${size}.png" "$DEST/io.github.davidedonadio.fanalinux.png"
        fi
    done
    if [ -f "$ICONS_SRC/io.github.davidedonadio.fanalinux.svg" ]; then
        DEST="$ICON_DIR/scalable/apps"
        mkdir -p "$DEST"
        cp "$ICONS_SRC/io.github.davidedonadio.fanalinux.svg" "$DEST/"
    fi
    echo -e "${GREEN}[✓] Desktop icons installed!${NC}"
fi

# 8. Install .desktop Entry
echo -e "${BLUE}[*] Installing desktop application entry...${NC}"
cat <<EOF > "$APP_DIR/io.github.davidedonadio.fanalinux.desktop"
[Desktop Entry]
Name=FanaLinux
GenericName=Fanatec Control Suite
Comment=Native Linux Control Panel, Telemetry Bridge & FFB Tuning for Fanatec Hardware
Exec=sh -c 'PATH="\$HOME/.local/bin:\$PATH" exec fanalinux'
Icon=io.github.davidedonadio.fanalinux
Terminal=false
Type=Application
Categories=HardwareSettings;Settings;Game;Simulation;
Keywords=fanatec;simracing;csl-dd;force-feedback;telemetry;
StartupNotify=true
EOF
chmod +x "$APP_DIR/io.github.davidedonadio.fanalinux.desktop"
echo -e "${GREEN}[✓] Desktop entry created at $APP_DIR/io.github.davidedonadio.fanalinux.desktop${NC}"

# Update desktop and icon databases
command -v update-desktop-database &>/dev/null && update-desktop-database "$APP_DIR" &>/dev/null || true
command -v gtk-update-icon-cache &>/dev/null && gtk-update-icon-cache -f -t "$ICON_DIR" &>/dev/null || true

# 9. Configure Fanatec USB Udev Permissions
echo ""
echo -e "${BOLD}${BLUE}--- Hardware Permissions (udev) ---${NC}"
echo "FanaLinux needs non-root permission to communicate with Fanatec hardware via /dev/hidraw."

UDEV_RULE_SRC="$SRC_DIR/udev/99-fanatec-fanalinux.rules"
UDEV_TARGET="/etc/udev/rules.d/99-fanatec-fanalinux.rules"

if [ -f "$UDEV_RULE_SRC" ]; then
    if [ -f "$UDEV_TARGET" ]; then
        echo -e "${GREEN}[✓] Udev rules already installed at $UDEV_TARGET${NC}"
    else
        echo -e "${YELLOW}Installing udev rule requires sudo access:${NC}"
        echo "  sudo cp $UDEV_RULE_SRC $UDEV_TARGET"
        echo "  sudo udevadm control --reload-rules && sudo udevadm trigger"
        echo ""
        read -rp "Install udev rule now with sudo? (Y/n): " INSTALL_UDEV
        if [[ ! "$INSTALL_UDEV" =~ ^[Nn]$ ]]; then
            sudo cp "$UDEV_RULE_SRC" "$UDEV_TARGET"
            sudo udevadm control --reload-rules
            sudo udevadm trigger
            echo -e "${GREEN}[✓] Udev rule installed and reloaded!${NC}"
        else
            echo -e "${YELLOW}[!] Skipped udev installation. You can install it manually later with:${NC}"
            echo "    sudo cp $UDEV_RULE_SRC /etc/udev/rules.d/ && sudo udevadm control --reload-rules && sudo udevadm trigger"
        fi
    fi
fi

# 10. Check PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo -e "\n${YELLOW}[NOTE] '$BIN_DIR' is not in your current PATH.${NC}"
    echo "To run 'fanalinux' directly from the terminal, add this to your ~/.bashrc or ~/.zshrc:"
    echo -e "  ${BOLD}export PATH=\"\$HOME/.local/bin:\$PATH\"${NC}"
fi

echo -e "\n${BOLD}${GREEN}====================================================${NC}"
echo -e "${BOLD}${GREEN}   FanaLinux has been successfully installed!       ${NC}"
echo -e "${BOLD}${GREEN}====================================================${NC}"
echo -e "Launch it anytime by searching ${BOLD}'FanaLinux'${NC} in your Application Menu"
echo -e "or by running ${BOLD}'fanalinux'${NC} in your terminal.\n"
