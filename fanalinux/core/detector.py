"""
Auto-Profile Sim Game Detector for Linux.
Monitors running processes for racing simulators and automatically switches
hardware tuning presets and telemetry engines.
"""

import os
import json
import time
import logging
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

from fanalinux.core.presets import list_presets, load_preset, init_default_presets

logger = logging.getLogger("fanalinux.detector")

CONFIG_PATH = Path.home() / ".config" / "fanalinux" / "game_profiles.json"
OLD_CONFIG_PATH = Path.home() / ".config" / "open-fanactrl" / "game_profiles.json"

BUILTIN_GAMES: List[Dict[str, Any]] = [
    {
        "id": "assetto_corsa",
        "name": "Assetto Corsa",
        "executables": ["acs.exe", "assettocorsa.exe"],
        "default_preset": "Assetto Corsa - GT3",
        "has_telemetry": True,
        "telemetry_type": "ac_udp",
        "description": "Kunos Simulazioni Assetto Corsa (Proton / Wine / Content Manager)"
    },
    {
        "id": "acc",
        "name": "Assetto Corsa Competizione",
        "executables": ["acc.exe", "ac2-win64-shipping.exe"],
        "default_preset": "Assetto Corsa - GT3",
        "has_telemetry": False,
        "telemetry_type": None,
        "description": "Official Fanatec GT World Challenge Simulator"
    },
    {
        "id": "f1_24",
        "name": "EA Sports F1 24",
        "executables": ["f1_24.exe"],
        "default_preset": "F1 24",
        "has_telemetry": False,
        "telemetry_type": "f1_udp",
        "description": "EA Sports Formula 1 2024"
    },
    {
        "id": "f1_23",
        "name": "EA Sports F1 23",
        "executables": ["f1_23.exe"],
        "default_preset": "F1 24",
        "has_telemetry": False,
        "telemetry_type": "f1_udp",
        "description": "EA Sports Formula 1 2023"
    },
    {
        "id": "iracing",
        "name": "iRacing",
        "executables": ["iracingsim64dx11.exe", "iracingsim64.exe"],
        "default_preset": "Default",
        "has_telemetry": False,
        "telemetry_type": None,
        "description": "iRacing Motorsport Simulations"
    },
    {
        "id": "ams2",
        "name": "Automobilista 2",
        "executables": ["ams2avx.exe", "ams2.exe"],
        "default_preset": "Default",
        "has_telemetry": False,
        "telemetry_type": None,
        "description": "Reiza Studios Automobilista 2"
    },
    {
        "id": "dirt_rally_2",
        "name": "DiRT Rally 2.0",
        "executables": ["dirtrally2.exe"],
        "default_preset": "Rally",
        "has_telemetry": False,
        "telemetry_type": None,
        "description": "Codemasters DiRT Rally 2.0"
    },
    {
        "id": "ea_wrc",
        "name": "EA Sports WRC",
        "executables": ["wrc.exe"],
        "default_preset": "Rally",
        "has_telemetry": False,
        "telemetry_type": None,
        "description": "EA Sports World Rally Championship"
    },
    {
        "id": "beamng",
        "name": "BeamNG.drive",
        "executables": ["beamng.drive.x64.exe", "beamng.drive.ui.x64.exe"],
        "default_preset": "Default",
        "has_telemetry": False,
        "telemetry_type": None,
        "description": "Soft-body physics vehicle simulator"
    },
    {
        "id": "rfactor2",
        "name": "rFactor 2",
        "executables": ["rfactor2.exe"],
        "default_preset": "Default",
        "has_telemetry": False,
        "telemetry_type": None,
        "description": "Studio 397 rFactor 2"
    },
    {
        "id": "lmu",
        "name": "Le Mans Ultimate",
        "executables": ["lemansultimate.exe"],
        "default_preset": "Default",
        "has_telemetry": False,
        "telemetry_type": None,
        "description": "Official FIA WEC / 24 Hours of Le Mans game"
    },
    {
        "id": "forza_motorsport",
        "name": "Forza Motorsport",
        "executables": ["forzamotorsport.exe"],
        "default_preset": "Default",
        "has_telemetry": False,
        "telemetry_type": None,
        "description": "Turn 10 Studios Forza Motorsport"
    },
    {
        "id": "ets2",
        "name": "Euro Truck Simulator 2",
        "executables": ["eurotrucks2.exe", "eurotrucks2"],
        "default_preset": "Default",
        "has_telemetry": False,
        "telemetry_type": None,
        "description": "SCS Software Euro Truck Simulator 2"
    },
    {
        "id": "ats",
        "name": "American Truck Simulator",
        "executables": ["amtrucks.exe", "amtrucks"],
        "default_preset": "Default",
        "has_telemetry": False,
        "telemetry_type": None,
        "description": "SCS Software American Truck Simulator"
    }
]


class GameDetector:
    def __init__(
        self,
        on_game_started: Optional[Callable[[Dict[str, Any], str, bool], None]] = None,
        on_game_stopped: Optional[Callable[[Dict[str, Any], str], None]] = None,
        on_scan_tick: Optional[Callable[[Optional[Dict[str, Any]]], None]] = None
    ):
        self.on_game_started = on_game_started
        self.on_game_stopped = on_game_stopped
        self.on_scan_tick = on_scan_tick

        self.running = False
        self._thread: Optional[threading.Thread] = None

        self.active_game: Optional[Dict[str, Any]] = None
        self.active_pid: Optional[int] = None
        self.active_exe: Optional[str] = None

        # Load configuration
        self.enabled = True
        self.poll_interval = 1.5
        self.fallback_preset = "Default"
        self.game_mappings: Dict[str, Dict[str, Any]] = {}
        self.custom_games: List[Dict[str, Any]] = []

        self._load_config()

    def _load_config(self):
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not CONFIG_PATH.exists() and OLD_CONFIG_PATH.exists():
            try:
                import shutil
                shutil.copy2(OLD_CONFIG_PATH, CONFIG_PATH)
            except Exception:
                pass

        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.enabled = bool(data.get("enabled", True))
                    self.poll_interval = float(data.get("poll_interval", 1.5))
                    self.fallback_preset = str(data.get("fallback_preset", "Default"))
                    self.game_mappings = data.get("game_mappings", {})
                    self.custom_games = data.get("custom_games", [])
            except Exception as e:
                logger.error(f"Error loading game profiles config: {e}")

        # Fill default mappings for builtins if not present
        for game in BUILTIN_GAMES:
            gid = game["id"]
            if gid not in self.game_mappings:
                self.game_mappings[gid] = {
                    "enabled": True,
                    "preset": game.get("default_preset", "Default"),
                    "auto_telemetry": game.get("has_telemetry", False)
                }

    def save_config(self):
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "enabled": self.enabled,
            "poll_interval": self.poll_interval,
            "fallback_preset": self.fallback_preset,
            "game_mappings": self.game_mappings,
            "custom_games": self.custom_games
        }
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving game profiles config: {e}")

    def get_all_games(self) -> List[Dict[str, Any]]:
        """Return combined list of builtin and custom games."""
        games = list(BUILTIN_GAMES)
        games.extend(self.custom_games)
        return games

    def get_game_by_id(self, game_id: str) -> Optional[Dict[str, Any]]:
        for g in self.get_all_games():
            if g["id"] == game_id:
                return g
        return None

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._scan_loop, daemon=True, name="GameDetectorThread")
        self._thread.start()
        logger.info("GameDetector background scanner started.")

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        logger.info("GameDetector background scanner stopped.")

    def scan_once(self) -> Optional[Dict[str, Any]]:
        """
        Perform a single scan of /proc looking for active sim games.
        Returns match dict if found: {'game': game_dict, 'exe': str, 'pid': int}
        """
        all_games = self.get_all_games()
        # Build quick lookup: lower_exe -> list of game dicts
        exe_map: Dict[str, List[Dict[str, Any]]] = {}
        for g in all_games:
            gid = g["id"]
            mapping = self.game_mappings.get(gid, {})
            # Skip if user disabled detection for this game
            if not mapping.get("enabled", True):
                continue
            for exe in g.get("executables", []):
                exe_lower = exe.lower()
                exe_map.setdefault(exe_lower, []).append(g)

        if not exe_map:
            return None

        try:
            proc_entries = os.listdir('/proc')
        except Exception:
            return None

        self_pid = os.getpid()
        for entry in proc_entries:
            if not entry.isdigit():
                continue
            pid = int(entry)
            if pid == self_pid:
                continue
            cmdline_path = f"/proc/{entry}/cmdline"
            comm_path = f"/proc/{entry}/comm"

            cmd_bytes = b""
            comm_str = ""

            try:
                with open(cmdline_path, "rb") as f:
                    cmd_bytes = f.read(4096)
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                continue

            try:
                with open(comm_path, "r", encoding="utf-8", errors="ignore") as f:
                    comm_str = f.read().strip().lower()
            except Exception:
                pass

            cmd_str = cmd_bytes.decode("utf-8", errors="ignore")
            # Linux cmdline has null separated args
            parts = [p for p in cmd_str.split("\x00") if p]

            for target_exe, games in exe_map.items():
                target_short = target_exe[:15]  # comm is limited to 15 chars in Linux
                matched = False

                # 1. Match comm
                if comm_str and (comm_str == target_exe or comm_str == target_short):
                    matched = True

                # 2. Match cmdline args by token basename
                if not matched and parts:
                    for part in parts:
                        # Clean both Windows & POSIX slashes to get exact filename
                        fname = part.replace("\\", "/").split("/")[-1].lower()
                        if fname == target_exe or fname == target_short:
                            matched = True
                            break

                if matched:
                    # Return first matching enabled game
                    return {
                        "game": games[0],
                        "exe": target_exe,
                        "pid": pid
                    }

        return None

    def _scan_loop(self):
        while self.running:
            try:
                if self.enabled:
                    match = self.scan_once()
                    if match:
                        matched_game = match["game"]
                        matched_pid = match["pid"]
                        matched_exe = match["exe"]

                        # Check if game just started or changed
                        if self.active_game is None or self.active_game["id"] != matched_game["id"]:
                            self.active_game = matched_game
                            self.active_pid = matched_pid
                            self.active_exe = matched_exe

                            gid = matched_game["id"]
                            mapping = self.game_mappings.get(gid, {})
                            preset_name = mapping.get("preset") or matched_game.get("default_preset", "Default")
                            auto_telem = mapping.get("auto_telemetry", matched_game.get("has_telemetry", False))

                            logger.info(f"Game Started: {matched_game['name']} (PID: {matched_pid}, preset: {preset_name})")
                            if self.on_game_started:
                                self.on_game_started(matched_game, preset_name, auto_telem)

                    else:
                        # No game active
                        if self.active_game is not None:
                            prev_game = self.active_game
                            self.active_game = None
                            self.active_pid = None
                            self.active_exe = None

                            logger.info(f"Game Stopped: {prev_game['name']} (reverting to {self.fallback_preset})")
                            if self.on_game_stopped:
                                self.on_game_stopped(prev_game, self.fallback_preset)

                    if self.on_scan_tick:
                        self.on_scan_tick(self.active_game)

            except Exception as e:
                logger.error(f"Error in GameDetector loop: {e}")

            time.sleep(self.poll_interval)
