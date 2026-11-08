# USB pedal brake force

The **Pedals** page provides software brake-force adjustment for ClubSport V3 /
V3 Inverted pedals connected directly over USB (Fanatec `0eb7:183b`). It works
independently of a wheelbase connection. Pedals connected through a wheelbase
use the existing hardware BRF setting instead.

1. Quit any other mapper that owns the pedals.
2. In **Pedals**, enable mapping and set brake force. At 100%, the brake axis
   uses its full range; at 20%, one fifth of its range produces full braking.
   Throttle, clutch and buttons pass through.
3. Bind **FanaLinux Pedals** in your game and keep FanaLinux running.

Mapping is initially disabled. The enabled state and percentage are saved in
`~/.config/fanalinux/pedals.json`; enabled mapping resumes on the next launch.
The physical event device is grabbed while mapping runs to prevent duplicate
input. Disabling mapping, closing FanaLinux or unplugging the pedals releases
it and removes the virtual controller. Enabled mapping reconnects automatically
when the pedals are plugged back in. Minimize the window to keep mapping active.

The installer offers to install pedal permissions and load `uinput` at boot.
For a manual install:

```sh
sudo install -m 644 udev/70-fanalinux-pedals.rules /etc/udev/rules.d/
sudo install -m 644 udev/fanalinux-pedals.conf /etc/modules-load.d/
sudo modprobe uinput
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=input
sudo udevadm trigger --subsystem-match=misc
```

Replug the pedals after changing permissions. On NixOS, the optional
[FanaLinux module](NIX.md#nixos) installs the rules and enables `uinput`.
Run FanaLinux as your desktop user. The Pedals status row reports mapper errors.

