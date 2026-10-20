# OpenFana Control (Fanatec Linux Suite)

[![Linux Compatible](https://img.shields.io/badge/Platform-Linux%20(Fedora%20%2F%20Arch%20%2F%20Ubuntu)-blue.svg)]()
[![License](https://img.shields.io/badge/License-GPLv3-green.svg)]()
[![Hardware](https://img.shields.io/badge/Hardware-Fanatec%20CSL%20DD%20%2F%20Formula%20V2.5-orange.svg)]()

**OpenFana Control** is a native, modern Linux GUI control suite designed to provide 1:1 parity with the Windows **Fanatec Control Panel** and **FanaLab** applications for Fanatec wheelbases and steering wheels.

Built using **GTK4** and **Libadwaita** on top of a user-space **`hidapi` / `evdev`** driver engine, it eliminates the need for proprietary Windows software or Wine wrappers to configure and tune Fanatec sim racing hardware.

---

## Legal & Intellectual Property Disclaimer

> **Notice:** This is an independent, clean-room open-source project created strictly for hardware interoperability. It is **not** endorsed by, affiliated with, or associated with **Endor AG**, **Fanatec**, or **Corsair**.
>
> All protocol research was conducted via black-box hardware analysis and USB packet monitoring under **Directive 2009/24/EC (Art. 5(3) & Art. 6)** of the European Parliament and Council on the legal protection of computer programs, and **17 U.S.C. § 1201(f)** (reverse engineering for interoperability). No proprietary source code, copyrighted firmware binaries, or trademarked graphical assets are distributed within this repository.

---

## Architecture Overview

```text
┌────────────────────────────────────────────────────────────────────────┐
│                   OpenFana Control UI (GTK4 + Libadwaita)              │
│  [Overview & Gauges]  [1:1 Tuning Menu]  [LEDs & Display]  [Calibrate] │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ Python GObject
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                       Fanatec Device Controller                        │
├───────────────────────────────────┬────────────────────────────────────┤
│           hidapi (/dev/hidraw*)   │        evdev (/dev/input/event*)   │
│   • Multi-color RevLEDs (BGR565)  │   • Sub-ms 16-bit steering angle   │
│   • Flag LEDs (Left/Right)        │   • 16-bit throttle / brake axes   │
│   • OLED Display Segments         │   • Button matrix & shift paddles  │
│   • EEPROM Tuning Parameter Write │                                    │
└───────────────────────────────────┴────────────────────────────────────┘
                                    │ USB (VID: 0x0EB7, PID: 0x0020)
                                    ▼
                 Fanatec CSL DD Wheelbase + Formula V2.5 Rim
```

---

## Technical Protocol Specification (For Maintainers & LLM Agents)

This section documents the reverse-engineered USB HID protocol so that future maintainers and autonomous LLM agents can inspect, extend, or port the driver to other languages (C/Rust/Go).

### 1. USB Identification
* **Vendor ID:** `0x0EB7` (Endor AG / Fanatec)
* **CSL DD Product ID (PID):** `0x0020` (Native PC Mode, Red LED)
* **ClubSport V2.5 PID:** `0x0004` (Compatibility Mode, Yellow LED)

### 2. HID Endpoints & Report IDs
* **Report ID `0x01` (Standard / Legacy):**
  * Output buffer: 8 bytes (`[0x01, CMD, ...]`).
  * Used for: Base initialization (`0xF5`), 7-segment / OLED telemetry display (`0xF8 0x09 0x01 0x02`), and Center Calibration (`0xF8 0x09 0x01 0x06 0x01`).
* **Report ID `0xFF` (DirectDrive Protocol Pipe):**
  * Output buffer: 64 bytes (`[0xFF, SubCommand, ...]`).
  * Used for: Multi-color LED states (RPM & Flags) and internal EEPROM Tuning parameters.

### 3. Multi-Color LEDs (Formula V2.5 / Podium Wheels)
Multicolor LEDs use **BGR565** encoding:
$$\text{BGR565} = ((\text{Blue} \gg 3) \ll 11) \mid ((\text{Green} \gg 2) \ll 5) \mid (\text{Red} \gg 3)$$

* **RevLEDs (9 LEDs):**
  * Header: `[0xFF, 0x01, 0x00]` followed by 9x 16-bit BGR565 words (High byte first), padded to 64 bytes.
* **Flag LEDs (6 LEDs: 3 Left, 3 Right):**
  * Header: `[0xFF, 0x01, 0x01]` followed by 6x 16-bit BGR565 words, padded to 64 bytes.

### 4. OLED / 7-Segment Display
* Payload: `[0x01, 0xF8, 0x09, 0x01, 0x02, seg1, seg2, seg3]`
* Display mapping converts ASCII characters into 7-segment bit patterns (see `fanactrl/core/protocol.py`).

### 5. Hardware Tuning Menu Register Map (Report `0xFF 0x03`)
Tuning writes use: `[0xFF, 0x03, 0x00, ...]` where `buf[addr + 1] = value`:

| Register | Address | Description | Range |
| :--- | :---: | :--- | :--- |
| **SLOT** | `0x02` | Active Hardware Profile Slot | 1 to 5 |
| **SEN** | `0x03` | Wheel Sensitivity / Degrees of Rotation | 90° to 2520° (Raw: `deg // 10`) |
| **FF** | `0x04` | Master Force Feedback Strength | 0% to 100% |
| **SHO** | `0x05` | Handle Shock / Vibration Intensity | 0% to 100% |
| **FFS** | `0x07` | Force Feedback Scaling | 0 = Linear, 1 = Peak |
| **FOR** | `0x0A` | Game Constant Force Multiplier | 0% to 120% |
| **SPR** | `0x0B` | Game Spring Multiplier | 0% to 120% |
| **DPR** | `0x0C` | Game Damper Multiplier | 0% to 120% |
| **NDP** | `0x0D` | Natural Damper Resistance | 0% to 100% |
| **NFR** | `0x0E` | Natural Friction Resistance | 0% to 100% |
| **BRF** | `0x10` | Load Cell Brake Force | 0% to 100% |
| **FEI** | `0x11` | Force Effect Intensity | 0% to 100% |
| **INT** | `0x14` | FFB Interpolation Filter | 0 to 20 |
| **NIN** | `0x15` | Natural Inertia | 0% to 100% |

---

## Installation & Setup on Linux

### 1. Permissions (`udev` Rule)
Ensure non-root access to Fanatec USB HID nodes:
```bash
sudo bash -c 'cat << "EOF" > /etc/udev/rules.d/99-fanatec.rules
# Fanatec Wheelbases and Peripherals
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="0eb7", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="usb", ATTRS{idVendor}=="0eb7", MODE="0666", TAG+="uaccess"
EOF'
sudo udevadm control --reload-rules && sudo udevadm trigger
```

### 2. Environment Setup
```bash
git clone https://github.com/your-username/open-fanactrl.git
cd open-fanactrl

# Create virtual environment with system GTK4 / Libadwaita
uv venv --system-site-packages
source .venv/bin/activate
uv pip install hidapi
```

### 3. Launching OpenFana Control
```bash
./fanactrl/main.py
```

---

## Implemented Features

* [x] **Live Hardware Monitor:** Real-time 16-bit steering angle gauge, Throttle, Brake, Clutch, and 24-button state matrix.
* [x] **1:1 Tuning Menu:** Complete controls for SEN, FF, FFS, NDP, NFR, NIN, INT, FEI, FOR, SPR, DPR, SHO, and BRF across Hardware Slots 1 to 5.
* [x] **Formula V2.5 Multi-Color LEDs:** Real-time BGR565 control over 9 RevLEDs and 6 Flag LEDs.
* [x] **OLED Display Control:** Direct custom text and telemetry rendering.
* [x] **Center Calibration:** One-click hardware motor index zero-point calibration.
* [x] **Libadwaita Modern UI:** Follows GNOME / Fedora design patterns with light/dark theme adaptation.

---

## Roadmap

- [ ] Telemetry Daemon (listening on UDP port `9996` for Assetto Corsa, ACC, and iRacing via Proton).
- [ ] Per-Car Auto Profile Switcher (FanaLab feature).
- [ ] Flatpak packaging for Flathub distribution.
