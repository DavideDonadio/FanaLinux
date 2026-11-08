{
  description = "FanaLinux: Fanatec control suite with USB pedal brake force";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in {
      packages = forAllSystems (system:
        let package = nixpkgs.legacyPackages.${system}.callPackage ./nix/package.nix { };
        in { default = package; fanalinux = package; });

      apps = forAllSystems (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/fanalinux";
          meta.description = "Launch FanaLinux";
        };
      });

      checks = forAllSystems (system: {
        package = self.packages.${system}.default;
      });

      devShells = forAllSystems (system:
        let pkgs = nixpkgs.legacyPackages.${system};
        in {
          default = pkgs.mkShell {
            inputsFrom = [ self.packages.${system}.default ];
            packages = [ pkgs.python3 pkgs.ruff pkgs.xvfb-run ];
          };
        });

      nixosModules.default = import ./nix/module.nix self;
    };
}
