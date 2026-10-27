# FanaLinux (Fanatec Linux Suite)

[![Linux Compatible](https://img.shields.io/badge/Platform-Linux%20(Fedora%20%2F%20Arch%20%2F%20Ubuntu)-blue.svg)]()
[![License](https://img.shields.io/badge/License-GPLv3-green.svg)]()
[![Hardware](https://img.shields.io/badge/Hardware-Fanatec%20CSL%20DD%20%2F%20Formula%20V2-orange.svg)]()

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
git clone https://github.com/DavideDonadio/FanaLinux.git
cd FanaLinux
./install.sh
fanalinux
```

Flow: **Tuning** → adjust → **Apply to Wheelbase**. \
**Remember to long-press the Tuning button for the full Advanced menu** (all 14 parameters). \
Game force feedback needs the hid-fanatecff kernel module — **Overview** installs it in one click.


## Features

| Tab | What it does |
|---|---|
| Overview | Hardware status, kernel FFB driver install/update + version, live inputs, about and version |
| Tuning | Full parameter set (SEN/FF/FFS/NDP/NFR/NIN/INT/FEI/FOR/SPR/DPR/SHO/BLI/BRF/FUL), slots 1–5, disk presets with exact numeric entry + SEN quick-chips |
| Profiles | Per-game auto-switching via `/proc` scan (Steam/Proton/Wine), auto telemetry start, fallback preset |
| Dyn FFB | Speed-sensitive + reverse-safety damping overlays |
| Vibration | ABS/engine/rev/suspension/TC/lock/spin/under-oversteer haptics with preview |
| Display | RevLEDs, flag LEDs, OLED gear/speed |
| Calibration | Center calibration, motor self-test, emergency cutoff |

**Telemetry in:** AC, BeamNG OutGauge, DiRT/WRC, F1, Forza (FM7 + FH/FM23), AMS2, SCS shm. \
**Out:** live RevLEDs, OLED gear/speed, ABS/TC flags, haptics, damping.

## Known limitations

- No read-back: The app can't display current on-wheel values — verification is eyes-on-OLED.
- Every Apply writes all known registers; DRI/ACP (unmodeled) reset to 0/OFF. If you use Drift mode, re-set it on the wheel afterwards.
- SHO displays On/Off only; granularity unverified beyond that. FFS Linear confirmed by symmetry (Peak verified).
- BRF can't be validated without load-cell pedals.

## Firmware updates

Flashing firmware needs official software. \
FanaLinux itself never flashes — by design.

## Legal

**FanaLinux is an independent community project and is not an official Fanatec product.** \
It is not affiliated with, endorsed by, or sponsored by Endor AG, Fanatec, Corsair, or their affiliates.

Protocol behavior is established through device testing and USB analysis for interoperability. \
No proprietary code, binaries, firmware, or assets are included. \
Fanatec product names identify compatible hardware only; all trademarks belong to their owners.

