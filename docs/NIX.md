# Installing with Nix

## Run or install on Linux

With Nix and flakes enabled, run these commands from the FanaLinux checkout:

```sh
nix run .
# Or install the desktop application in your user profile:
nix profile install .
```

The package includes GTK4, Libadwaita, Python dependencies, desktop entry,
icons and udev rules. Supported flake systems are `x86_64-linux` and
`aarch64-linux`. Building and running the package does not install system
permissions or load kernel modules.

On Linux distributions other than NixOS, install the rules from this checkout
and enable uinput once:

```sh
sudo install -m 644 udev/99-fanatec-fanalinux.rules /etc/udev/rules.d/
sudo install -m 644 udev/70-fanalinux-pedals.rules /etc/udev/rules.d/
sudo install -m 644 udev/fanalinux-pedals.conf /etc/modules-load.d/
sudo modprobe uinput
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=input
sudo udevadm trigger --subsystem-match=hidraw
sudo udevadm trigger --subsystem-match=misc
```

Replug your Fanatec devices afterwards. Run FanaLinux as your desktop user.

## NixOS

Add the input and module to your system flake, replacing the example path with
the absolute path to your FanaLinux checkout:

```nix
{
  inputs.fanalinux.url = "path:/absolute/path/to/FanaLinux";
  inputs.fanalinux.inputs.nixpkgs.follows = "nixpkgs";

  outputs = { nixpkgs, fanalinux, ... }: {
    nixosConfigurations.myHost = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        ./configuration.nix
        fanalinux.nixosModules.default
        { services.fanalinux.enable = true; }
      ];
    };
  };
}
```

The module installs the app and udev rules and loads `uinput`. It does not
start the GUI automatically or install the separate `hid-fanatecff` wheelbase
FFB driver. Standalone USB pedal mapping does not need that driver.
Apply your configuration using your usual NixOS deployment workflow, then
replug your devices. In **Pedals**, enable mapping and select **FanaLinux Pedals**
in your game. Keep the app open while playing.

## Develop and verify

```sh
nix develop
python -m fanalinux.main
xvfb-run -a python -m unittest discover -s tests
ruff check fanalinux tests --select F
```

`nix build` builds the app and runs its test suite under a virtual display.
`nix flake check` checks the flake and builds the package for the current system.
