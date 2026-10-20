# OpenFana Control (Fanatec Linux Suite)

[![Linux Compatible](https://img.shields.io/badge/Platform-Linux%20(Fedora%20%2F%20Arch%20%2F%20Ubuntu)-blue.svg)]()
[![License](https://img.shields.io/badge/License-GPLv3-green.svg)]()
[![Hardware](https://img.shields.io/badge/Hardware-Fanatec%20CSL%20DD%20%2F%20Formula%20V2.5-orange.svg)]()

**OpenFana Control** is a native, modern Linux GUI control suite designed to provide 1:1 parity with the Windows **Fanatec Control Panel** and **FanaLab** applications for Fanatec wheelbases and steering wheels.

Built using **GTK4** and **Libadwaita** on top of a user-space **`hidraw` / `evdev`** driver engine, it eliminates the need for proprietary Windows software or Wine wrappers to configure and tune Fanatec sim racing hardware.

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
                                    │ Python GObject / Evdev
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                       Fanatec Device Controller                        │
├───────────────────────────────────┬────────────────────────────────────┤
│           Native Linux /dev/hidraw│        evdev (/dev/input/event*)   │
│   • Multi-color RevLEDs (BGR565)  │   • Sub-ms 16-bit steering angle   │
│   • Flag LEDs (Left/Right)        │   • 16-bit throttle / brake axes   │
│   • OLED Display Segments         │   • Button matrix & shift paddles  │
│   • EEPROM Tuning Parameter Write │                                    │
├───────────────────────────────────┴────────────────────────────────────┤
│              In-Game Telemetry Engine (FanaLab Equivalent)             │
│   • Ingests Assetto Corsa UDP broadcasts on localhost port 9996        │
│   • Computes live RPM percentage & drives Formula V2.5 RevLEDs         │
│   • Renders active Gear (1, 2, 3, N, R) or Speed directly to OLED      │
│   • Flashes Flag LEDs on ABS, Traction Control, or Pit Limiter         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ USB (VID: 0x0EB7, PID: 0x0020)
                                    ▼
                 Fanatec CSL DD Wheelbase + Formula V2.5 Rim
```

---

## Features Implemented (1:1 Parity Status)

### 1. Hardware Tuning Menu (1:1 with Wheelbase EEPROM)
* **SEN:** Wheel Sensitivity / Rotation degrees (90° to 2520°, 0 = Auto).
* **FF:** Overall Force Feedback Master Strength (0% to 100%).
* **FFS:** Force Feedback Scaling (Linear mode vs Peak torque mode).
* **NDP / NFR / NIN:** Natural Damper, Natural Friction, and Natural Inertia.
* **INT / FEI:** Interpolation smoothing filter and Force Effect Intensity.
* **FOR / SPR / DPR:** In-game physics multipliers (Constant Force, Spring, Damper).
* **SHO:** Wheel rim handle vibration / shock motor intensity.
* **BRF:** Load-cell brake force sensitivity.
* **Hardware Profile Slots:** Save / switch directly across Base Memory Slots 1 through 5.
* **Car / Game Preset Manager:** Save and load custom tuning configurations to disk (`~/.config/open-fanactrl/presets/`).

### 2. Live In-Game Telemetry Engine (FanaLab Equivalent)
* **Assetto Corsa Native UDP Integration:** Listens to Assetto Corsa on `127.0.0.1:9996` with zero configuration needed.
* **Dynamic RevLEDs:** Real-time RPM climb across the 9 Formula V2.5 multi-color LEDs with shift point strobe.
* **In-Game OLED Display:** Automatically renders live Gear (`1`, `2`, `3`, `N`, `R`) or Vehicle Speed (KM/H).
* **Flag Alerts:** Flashes side Flag clusters on ABS activation or Traction Control intervention.

### 3. Overview & Input Visualizer
* **16-bit Steering Angle Gauge:** Sub-millisecond evdev reading with degrees readout.
* **Pedal Travel Bars:** Color-coded gauges for Throttle (Green), Brake (Red), Clutch (Blue).
* **24-Button Matrix:** Monospace pill chips highlighting live button clicks and shifter paddle pulls.

### 4. Calibration & Diagnostics
* **Center Calibration:** One-click optical/magnetic motor index zero-point calibration.
* **Pedal Deadzones:** Customizable lower deadbands for Throttle, Brake, and Clutch.
* **ClubSport Shifter Wizard:** Step-by-step guided wizard for 1st–7th gear and Reverse indexing.
* **Firmware Version Display:** Reports Base, Motor Controller, and Steering Rim revisions.

---

## Technical Protocol Specification (For Maintainers & LLM Agents)

### 1. USB Identification
* **Vendor ID:** `0x0EB7` (Endor AG / Fanatec)
* **CSL DD Product ID (PID):** `0x0020` (Native PC Mode, Red LED)

### 2. HID Endpoints & Report IDs
* **Report ID `0x01` (Standard / Legacy):** 8 bytes (`[0x01, CMD, ...]`).
  * Used for: Base initialization (`0xF5`), OLED display (`0xF8 0x09 0x01 0x02`), and Center Calibration (`0xF8 0x09 0x01 0x06 0x01`).
* **Report ID `0xFF` (DirectDrive Protocol Pipe):** 64 bytes (`[0xFF, SubCommand, ...]`).
  * Used for: Multi-color LED states (RPM & Flags) and internal EEPROM Tuning parameters.

### 3. Multi-Color LEDs (Formula V2.5 / Podium Wheels)
Multicolor LEDs use **BGR565** encoding:
$$\text{BGR565} = ((\text{Blue} \gg 3) \ll 11) \mid ((\text{Green} \gg 2) \ll 5) \mid (\text{Red} \gg 3)$$

* **RevLEDs (9 LEDs):**
  * Header: `[0xFF, 0x01, 0x00]` followed by 9x 16-bit BGR565 words (High byte first), padded to 64 bytes.
* **Flag LEDs (6 LEDs: 3 Left, 3 Right):**
  * Header: `[0xFF, 0x01, 0x01]` followed by 6x 16-bit BGR565 words, padded to 64 bytes.

---

## Installation & Launch

```bash
# Clone and enter repo
cd ~/Documents/Projects/open-fanactrl

# Launch application
.venv/bin/open-fanactrl
```

Or press the **Super (Windows) key** in GNOME and search for **"OpenFana Control"**!
