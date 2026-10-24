# FanaLinux (Fanatec Linux Suite)

[![Linux Compatible](https://img.shields.io/badge/Platform-Linux%20(Fedora%20%2F%20Arch%20%2F%20Ubuntu)-blue.svg)]()
[![License](https://img.shields.io/badge/License-GPLv3-green.svg)]()
[![Hardware](https://img.shields.io/badge/Hardware-Fanatec%20CSL%20DD%20%2F%20Formula%20V2.5-orange.svg)]()

**FanaLinux** is a native, modern Linux GUI control suite providing comprehensive hardware tuning, profile switching, and dynamic telemetry feedback for Fanatec wheelbases and steering wheels.

Built using **GTK4** and **Libadwaita** on top of a user-space **`hidraw` / `evdev`** driver engine, it eliminates the need for proprietary Windows software or Wine wrappers to configure and tune Fanatec sim racing hardware.

---

## Hardware support

| Base | Status |
|---|:---:|
| CSL DD / GT DD Pro | ![Validated](https://img.shields.io/badge/Validated-brightgreen) |
| Podium DD1/DD2, ClubSport DD/DD+ | ![Expected](https://img.shields.io/badge/Expected-yellow) |
| CSL Elite / ClubSport V2.5 (belt) | ![Unsupported](https://img.shields.io/badge/Unsupported-red) |

**Validated** — every tuning register confirmed on-wheel (CSL DD 5Nm + Formula V2, base 1.9.2.3 / motor 1.1.2.2). \
**Expected** — same protocol family and official parameter spec, encodings not yet verified on hardware. \
**Unsupported** — belt-driven bases are not supported; direct-drive bases only.

## Quick start

```bash
git clone https://github.com/DavideDonadio/fanalinux.git
cd fanalinux
./install.sh
fanalinux
```

Flow: **Tuning** → adjust → **Apply to Wheelbase**. \
**Remember to long-press the Tuning button for the full Advanced menu** (all 14 parameters).

## Features

| Tab | What it does |
|---|---|
| Overview | Hardware status + firmware, live 16-bit steering/pedals/buttons, about and version |
| Tuning | Full parameter set (SEN/FF/FFS/NDP/NFR/NIN/INT/FEI/FOR/SPR/DPR/SHO/BLI/BRF/FUL), slots 1–5, disk presets with exact numeric entry + SEN quick-chips |
| Profiles | Per-game auto-switching via `/proc` scan (Steam/Proton/Wine), auto telemetry start, fallback preset |
| Dynamic FFB | Speed-sensitive + reverse-safety damping overlays |
| Vibration | ABS/engine/rev/suspension/TC/lock/spin/under-oversteer haptics with preview |
| LED & Display | RevLEDs, flag LEDs, OLED gear/speed |
| Calibration | Center calibration, motor diagnostics, pedal deadzones |

**Telemetry in:** AC, BeamNG OutGauge, DiRT/WRC, F1, Forza (FM7 + FH/FM23), AMS2, SCS shm. \
**Out:** live RevLEDs, OLED gear/speed, ABS/TC flags, haptics, damping.

## Known limitations

- No read-back: The app can't display current on-wheel values — verification is eyes-on-OLED.
- Every Apply writes all known registers; DRI/ACP (unmodeled) reset to 0/OFF. If you use Drift mode, re-set it on the wheel afterwards.
- SHO displays On/Off only; granularity unverified beyond that. FFS Linear confirmed by symmetry (Peak verified).
- BRF can't be validated without load-cell pedals.

## Firmware updates & Windows companion

Flashing firmware needs official software. \
FanaLinux itself never flashes — by design.

## Legal & Intellectual Property Notice

FanaLinux is an independent, open-source project developed to enable interoperability between Linux systems and compatible Fanatec hardware. It is not affiliated with, endorsed by, or sponsored by Endor AG, Fanatec, Corsair, or their respective affiliates.

The project's implementation is independently authored. No Fanatec proprietary source code, Windows application binaries, firmware images, or proprietary graphical assets are intentionally incorporated into or distributed with this project.

Hardware protocol behaviour is investigated through direct device testing and USB communication analysis for compatibility purposes. The Fanatec Windows application has not been decompiled or disassembled as part of this project's development.

The project is intended to enable interoperability with lawfully possessed hardware while respecting applicable intellectual-property laws. This notice describes the project's development approach and intended scope; it does not constitute a legal determination or guarantee of compliance in every jurisdiction.

Fanatec and related product names are used solely to identify compatible hardware. All trademarks remain the property of their respective owners. **FanaLinux is an independent community project and is not an official Fanatec product.**

