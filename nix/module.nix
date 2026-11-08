self:
{ config, lib, pkgs, ... }:
let
  cfg = config.services.fanalinux;
in {
  options.services.fanalinux = {
    enable = lib.mkEnableOption "FanaLinux and its hardware permissions";
    package = lib.mkOption {
      type = lib.types.package;
      default = self.packages.${pkgs.stdenv.hostPlatform.system}.default;
      defaultText = lib.literalExpression "inputs.fanalinux.packages.\${pkgs.stdenv.hostPlatform.system}.default";
      description = "FanaLinux package to install.";
    };
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ cfg.package ];
    services.udev.packages = [ cfg.package ];
    boot.kernelModules = [ "uinput" ];
  };
}
