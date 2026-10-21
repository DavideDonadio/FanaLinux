#!/usr/bin/env bash
# ==============================================================================
# FanaLinux Uninstaller
# https://github.com/DavideDonadio/fanalinux
# ==============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

echo -e "${BOLD}${BLUE}====================================================${NC}"
echo -e "${BOLD}${RED}             FanaLinux Uninstaller                 ${NC}"
echo -e "${BOLD}${BLUE}====================================================${NC}\n"

read -rp "Are you sure you want to uninstall FanaLinux? (y/N): " CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "Uninstallation cancelled."
    exit 0
fi

echo -e "${BLUE}[*] Removing FanaLinux files...${NC}"

# Remove installation dir and binary
rm -rf "$HOME/.local/share/fanalinux"
rm -f "$HOME/.local/bin/fanalinux"

# Remove desktop entry
rm -f "$HOME/.local/share/applications/io.github.davidedonadio.fanalinux.desktop"

# Remove icons
for size in 48 64 128 256 512; do
    rm -f "$HOME/.local/share/icons/hicolor/${size}x${size}/apps/io.github.davidedonadio.fanalinux.png"
done
rm -f "$HOME/.local/share/icons/hicolor/scalable/apps/io.github.davidedonadio.fanalinux.svg"

# Update desktop and icon databases
command -v update-desktop-database &>/dev/null && update-desktop-database "$HOME/.local/share/applications" &>/dev/null || true
command -v gtk-update-icon-cache &>/dev/null && gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" &>/dev/null || true

# Udev rule removal prompt
UDEV_FILE="/etc/udev/rules.d/99-fanatec-fanalinux.rules"
if [ -f "$UDEV_FILE" ]; then
    read -rp "Remove Fanatec udev permissions rule ($UDEV_FILE)? (y/N): " REMOVE_UDEV
    if [[ "$REMOVE_UDEV" =~ ^[Yy]$ ]]; then
        sudo rm -f "$UDEV_FILE"
        sudo udevadm control --reload-rules
        sudo udevadm trigger
        echo -e "${GREEN}[✓] Udev rule removed.${NC}"
    fi
fi

echo -e "\n${BOLD}${GREEN}FanaLinux has been successfully uninstalled from your system.${NC}\n"
