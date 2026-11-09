{
  lib,
  python3Packages,
  gobject-introspection,
  wrapGAppsHook4,
  gtk4,
  libadwaita,
  copyDesktopItems,
  makeDesktopItem,
  xvfb-run,
}:

python3Packages.buildPythonApplication {
  pname = "fanalinux";
  version = (builtins.fromTOML (builtins.readFile ../pyproject.toml)).project.version;
  pyproject = true;

  src = lib.cleanSource ../.;
  build-system = [ python3Packages.setuptools ];
  dependencies = with python3Packages; [ hidapi evdev pygobject3 pycairo ];
  nativeBuildInputs = [ gobject-introspection wrapGAppsHook4 copyDesktopItems ];
  buildInputs = [ gtk4 libadwaita ];
  nativeCheckInputs = [ xvfb-run ];

  # Use the Python wrapper for both Python dependencies and GTK's runtime paths.
  dontWrapGApps = true;
  preFixup = ''
    makeWrapperArgs+=( "''${gappsWrapperArgs[@]}" )
  '';

  checkPhase = ''
    runHook preCheck
    export HOME="$TMPDIR/fanalinux-test-home"
    mkdir -p "$HOME"
    export GSETTINGS_BACKEND=memory
    export GTK_A11Y=none
    xvfb-run -a python -m unittest discover -s tests
    runHook postCheck
  '';

  postInstall = ''
    install -Dm444 udev/99-fanatec-fanalinux.rules $out/lib/udev/rules.d/99-fanatec-fanalinux.rules
    install -Dm444 udev/70-fanalinux-pedals.rules $out/lib/udev/rules.d/70-fanalinux-pedals.rules
    install -Dm444 fanalinux/resources/icons/io.github.davidedonadio.fanalinux.svg \
      $out/share/icons/hicolor/scalable/apps/io.github.davidedonadio.fanalinux.svg
    for size in 48 64 128 256 512; do
      install -Dm444 fanalinux/resources/icons/io.github.davidedonadio.fanalinux_''${size}.png \
        $out/share/icons/hicolor/''${size}x''${size}/apps/io.github.davidedonadio.fanalinux.png
    done
  '';

  desktopItems = [ (makeDesktopItem {
    name = "io.github.davidedonadio.fanalinux";
    desktopName = "FanaLinux";
    genericName = "Fanatec Control Suite";
    comment = "Fanatec hardware tuning, telemetry and USB pedal brake force";
    exec = "fanalinux";
    icon = "io.github.davidedonadio.fanalinux";
    categories = [ "Settings" "HardwareSettings" "Game" "Simulation" ];
    keywords = [ "fanatec" "simracing" "pedals" "telemetry" ];
    startupNotify = true;
  }) ];

  meta = {
    description = "Native Linux control panel and telemetry suite for Fanatec hardware";
    homepage = "https://github.com/DavideDonadio/FanaLinux";
    license = lib.licenses.gpl3Plus;
    platforms = lib.platforms.linux;
    mainProgram = "fanalinux";
  };
}
