# FanaLinux (Fanatec Linux Suite)

[![Linux Compatible](https://img.shields.io/badge/Platform-Linux%20(Fedora%20%2F%20Arch%20%2F%20Ubuntu)-blue.svg)]()
[![License](https://img.shields.io/badge/License-GPLv3-green.svg)]()
[![Hardware](https://img.shields.io/badge/Hardware-Fanatec%20CSL%20DD%20%2F%20Formula%20V2.5-orange.svg)]()

**FanaLinux** is a native, modern Linux GUI control suite designed to provide 1:1 parity with the Windows **Fanatec Control Panel** and **FanaLab** applications for Fanatec wheelbases and steering wheels.

Built using **GTK4** and **Libadwaita** on top of a user-space **`hidraw` / `evdev`** driver engine, it eliminates the need for proprietary Windows software or Wine wrappers to configure and tune Fanatec sim racing hardware.

---

## Legal & Intellectual Property Notice

FanaLinux is an independent, open-source project developed to enable interoperability between Linux systems and compatible Fanatec hardware. It is not affiliated with, endorsed by, or sponsored by Endor AG, Fanatec, Corsair, or their respective affiliates.

The project's implementation is independently authored. No Fanatec proprietary source code, Windows application binaries, firmware images, or proprietary graphical assets are intentionally incorporated into or distributed with this project.

Hardware protocol behaviour is investigated through direct device testing and USB communication analysis for compatibility purposes. The Fanatec Windows application has not been decompiled or disassembled as part of this project's development.

The project is intended to enable interoperability with lawfully possessed hardware while respecting applicable intellectual-property laws. This notice describes the project's development approach and intended scope; it does not constitute a legal determination or guarantee of compliance in every jurisdiction.

Fanatec and related product names are used solely to identify compatible hardware. All trademarks remain the property of their respective owners. FanaLinux is an independent community project and is not an official Fanatec product.

---

## Architecture Overview

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                            FanaLinux UI (GTK4 + Libadwaita)                            │
│     [Overview]  [Tuning]  [Vibration]  [LED & Display]  [Profiles]  [Calibration]      │
└────────────────────────────────────────┬───────────────────────────────────────────────┘
                                         │ Python GObject / Evdev
                                         ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               Fanatec Device Controller                                │
├────────────────────────────────────────┬───────────────────────────────────────────────┤
│           Native Linux /dev/hidraw     │        evdev (/dev/input/event*)              │
│   • Multi-color RevLEDs (BGR565)       │   • Sub-ms 16-bit steering angle              │
│   • Flag LEDs (Left/Right)             │   • 16-bit throttle / brake axes              │
│   • OLED Display Segments              │   • Button matrix & shift paddles             │
│   • EEPROM Tuning Parameter Write      │                                               │
├────────────────────────────────────────┴───────────────────────────────────────────────┤
│                   Auto-Profile Sim Game Detector (FanaLab Equivalent)                  │
│   • Background /proc process scanner detecting Steam/Proton/Wine/native sims           │
│   • Auto-switches wheelbase tuning presets (AC, ACC, F1, iRacing, AMS2, Rally, etc.)   │
│   • Auto-launches in-game UDP telemetry engine (Assetto Corsa UDP 9996)                │
│   • Restores baseline fallback profile upon simulator exit                             │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                       In-Game Telemetry Engine (Live Telemetry)                        │
│   • Ingests Assetto Corsa UDP broadcasts on localhost port 9996                        │
│   • Computes live RPM percentage & drives Formula V2.5 RevLEDs                         │
│   • Renders active Gear (1, 2, 3, N, R) or Speed directly to OLED                      │
│   • Flashes Flag LEDs on ABS, Traction Control, or Pit Limiter                         │
└────────────────────────────────────────┬───────────────────────────────────────────────┘
                                         │ USB (VID: 0x0EB7, PID: 0x0020)
                                         ▼
                    Fanatec CSL DD Wheelbase + Formula V2.5 Rim
```

---

## Features (1:1 Parity Status)

### 1. Hardware Tuning Menu (1:1 with Wheelbase EEPROM)
* **SEN:** Wheel Sensitivity / Rotation degrees (90° to 2520°, 0 = Auto) with toggleable Auto mode and direct numeric input for exact degree precision.
* **FF:** Overall Force Feedback Master Strength (0% to 100%).
* **FFS:** Force Feedback Scaling (Linear mode vs Peak torque mode).
* **NDP / NFR / NIN:** Natural Damper, Natural Friction, and Natural Inertia.
* **INT / FEI:** Interpolation smoothing filter and Force Effect Intensity.
* **FOR / SPR / DPR:** In-game physics multipliers (Constant Force, Spring, Damper).
* **SHO:** Wheel rim handle vibration / shock motor intensity.
* **BRF:** Load-cell brake force sensitivity.
* **Hardware Profile Slots:** Save / switch directly across Base Memory Slots 1 through 5.
* **Car / Game Preset Manager:** Save and load custom tuning configurations to disk (`~/.config/fanalinux/presets/`).

### 2. Auto-Profile Game Detection & Preset Management (FanaLab Equivalent)
* **Background Process Scanner:** Non-intrusive Linux `/proc` scanner (<5ms overhead) actively monitoring for running racing simulators.
* **Proton / Wine / Native Interoperability:** Automatically detects games whether launched natively or via Steam Proton / Wine / Content Manager (e.g., `acs.exe`, `acc.exe`, `iRacingSim64DX11.exe`, `F1_24.exe`, `AMS2AVX.exe`, `BeamNG.drive.x64.exe`, `dirtrally2.exe`, `wrc.exe`, `eurotrucks2.exe`, `lemansultimate.exe`).
* **Instant Profile Switching:** Automatically applies associated tuning profile to wheelbase EEPROM memory on game start.
* **Auto Telemetry Launch:** Automatically starts background telemetry listeners (e.g. Assetto Corsa UDP port 9996) when a compatible sim starts.
* **Fallback & Recovery:** Seamlessly reverts to desktop fallback profile (e.g. `Default`) and stops telemetry when the simulator process exits.
* **Factory Preset Catalog:** Pre-seeded with optimized profiles (`Default`, `Assetto Corsa - GT3`, `Assetto Corsa - Formula`, `F1 24`, `Drift`, `Rally`) in `~/.config/fanalinux/presets/`.

### 3. Live In-Game Telemetry Engine (FanaLab Equivalent)
* **Assetto Corsa Native UDP Integration:** Listens to Assetto Corsa on `127.0.0.1:9996` with zero configuration needed.
* **Dynamic RevLEDs:** Real-time RPM climb across the 9 Formula V2.5 multi-color LEDs with shift point strobe.
* **In-Game OLED Display:** Automatically renders live Gear (`1`, `2`, `3`, `N`, `R`) or Vehicle Speed (KM/H).
* **Flag Alerts:** Flashes side Flag clusters on ABS activation or Traction Control intervention.

### 4. Vibration & Dynamic Haptics (FanaLab Parity)
* **Braking & Engine Dynamics:**
  * **ABS Vibration:** Programmable tactile pulse frequency (18 Hz) and duration upon brake lockups.
  * **Engine Vibration:** Continuous subtle motor and rim vibration dynamically scaled with engine RPM.
  * **Rev Limiter Vibration:** Sharp rhythmic shudder when bumping against maximum redline revs.
* **Suspension & Surface Displacement:**
  * **Curb Strikes:** Simulates rough rumble strips and kerb strikes through steering rim haptics.
* **Traction & Tire Slip:**
  * **Traction Control Intervention:** Haptic alerts when ECU traction control engages under acceleration.
  * **Wheel Lock & Spin:** Directional vibration warnings when driven wheels break traction or tires lock.
* **Chassis Balance:**
  * **Understeer & Oversteer Alerts:** Tactile warnings when front scrub or rear yaw exceed optimal slip angles.

### 5. Overview & Input Visualizer
* **16-bit Steering Angle Gauge:** Sub-millisecond evdev reading with live degrees readout.
* **Pedal Travel Bars:** Color-coded gauges for Throttle (Green), Brake (Red), Clutch (Blue).
* **24-Button Matrix:** Monospace pill chips highlighting live button clicks and shifter paddle pulls with generous padding.

### 6. Calibration, Diagnostics & Visual Dial
* **Interactive 360° Wheel Center Dial:** High-resolution ClubSport Formula V2.5 rim rendering rotating in real-time with cardinal degree markings, angle badge, and smooth 60 FPS cubic ease-out calibration ripple animation.
* **Force Feedback Motor Test Suite:** Interactive centering spring, dynamic mechanical friction, alternating torque pulse sequence, and 18 Hz tactile vibration test.
* **Safety Force Cutoff:** Dedicated emergency stop button instantly canceling all active motor torque, centering springs, and vibrations.
* **Pedal Deadzones:** Customizable lower threshold deadbands for Throttle, Brake, and Clutch (220 px standardized sliders).
* **Hardware Firmware Display:** Real-time reporting of Wheelbase Base, Motor Controller, and Steering Rim revisions.

---

## Technical Protocol Specification (For Maintainers & Developers)

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

### Prerequisites
* Fedora Linux, Arch Linux, Ubuntu, or Debian
* Python >= 3.10
* GTK4 & Libadwaita (`libadwaita`, `python3-gobject`)

### Quick Setup

```bash
# Clone repository
git clone https://github.com/DavideDonadio/fanalinux.git
cd fanalinux

# Create virtual environment with system packages (for PyGObject/GTK4)
python3 -m venv --system-site-packages .venv
source .venv/bin/activate

# Install dependencies and package
pip install -e .

# Launch FanaLinux
fanalinux
```

Or press the **Super (Windows) key** in your desktop environment and search for **"FanaLinux"**!
