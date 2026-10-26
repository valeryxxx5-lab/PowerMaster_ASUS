"""
PowerMaster_ASUS - PowerWatcher Trigger Coordinator
Monitors system state and coordinates automatic switching of power plans:
1. Battery mode (AC disconnected): Power Saver (Safety Priority 1)
2. Process Trigger: Game in F:\\Games -> High Performance
3. Manual Override: User-selected plan stays active on AC unless gaming/battery
4. Idle & Display Trigger: Display off or > 3 min inactivity -> Power Saver; activity -> Restore
5. Startup Boost (first 3 min after Windows boot): High Performance
6. Default AC: Balanced
"""

from __future__ import annotations
import ctypes
from ctypes import wintypes
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

import psutil

from config import (
    GUID_HIGH_PERFORMANCE,
    GUID_BALANCED,
    GUID_POWER_SAVER,
    PLAN_NAMES,
    config,
)
from power_plan import PowerPlanManager
from asus_thermal import AsusThermalController
from windows_energy_saver import WindowsEnergySaver

logger = logging.getLogger("PowerMaster.Watcher")


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("dwTime", wintypes.DWORD),
    ]


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", wintypes.BYTE),
        ("BatteryFlag", wintypes.BYTE),
        ("BatteryLifePercent", wintypes.BYTE),
        ("SystemStatusFlag", wintypes.BYTE),
        ("BatteryLifeTime", wintypes.DWORD),
        ("BatteryFullLifeTime", wintypes.DWORD),
    ]


class WinGUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]

    @classmethod
    def from_uuid_str(cls, u_str: str) -> "WinGUID":
        u = uuid.UUID(u_str)
        return cls.from_buffer_copy(u.bytes_le)


GUID_CONSOLE_DISPLAY_STATE_STR = "6FE69556-704A-47A0-8F24-C21ED9394451"
GUID_SESSION_DISPLAY_STATUS_STR = "2B84C10B-0856-4D24-AF04-ABEE3E1A6482"
GUID_MONITOR_POWER_ON_STR = "02731015-4510-4526-99E6-E5A17EBD1AEA"
GUID_ACDC_POWER_SOURCE_STR = "5D3E4A6D-E927-4B00-9363-22E0E1192408"
GUID_POWERSCHEME_PERSONALITY_STR = "245D8541-3943-4422-B025-13A784F679B7"


class POWERBROADCAST_SETTING(ctypes.Structure):
    _fields_ = [
        ("PowerSetting", WinGUID),
        ("DataLength", wintypes.DWORD),
        ("Data", wintypes.BYTE * 1),
    ]


@dataclass
class SystemSnapshot:
    is_on_ac: bool
    battery_percent: int
    idle_seconds: float
    is_idle: bool
    in_startup_boost: bool
    active_game_process: Optional[str]
    current_plan_guid: Optional[str]
    current_plan_name: str
    startup_remaining_seconds: float = 0.0
    is_display_off: bool = False


class FastForegroundDetector:
    """
    Fast-Path O(1) Foreground Game Detection.
    Uses WinAPI to directly query the active foreground window process,
    eliminating the need to iterate through all processes in the system.
    """

    def __init__(self):
        self.user32 = ctypes.windll.user32
        self.kernel32 = ctypes.windll.kernel32

        # Explicit ctypes 64-bit typing to prevent 64-bit handle truncation in Windows 11
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.user32.GetForegroundWindow.argtypes = []

        self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]

        self.user32.FindWindowExW.restype = wintypes.HWND
        self.user32.FindWindowExW.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
        ]

        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]

        self.kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        self.kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]

        self.kernel32.CloseHandle.restype = wintypes.BOOL
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        self.PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    def _get_process_name_and_path(self, pid: int) -> Optional[Tuple[str, str]]:
        if pid <= 0:
            return None
        h_process = self.kernel32.OpenProcess(self.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h_process:
            return None
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if self.kernel32.QueryFullProcessImageNameW(h_process, 0, buf, ctypes.byref(size)):
                full_path = buf.value
                return (os.path.basename(full_path), full_path)
        finally:
            self.kernel32.CloseHandle(h_process)
        return None

    def get_foreground_process_info(self) -> Optional[Tuple[int, str, str]]:
        """
        Queries the current foreground window and returns (pid, exe_name, full_path) or None.
        Includes O(1) dereferencing for UWP / Xbox Game Pass games hosted inside ApplicationFrameHost.exe.
        Complexity: O(1) system calls.
        """
        try:
            hwnd = self.user32.GetForegroundWindow()
            if not hwnd:
                return None

            pid = wintypes.DWORD()
            self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == 0:
                return None

            info = self._get_process_name_and_path(pid.value)
            if not info:
                return None

            exe_name, full_path = info

            # UWP / Xbox Game Pass check (ApplicationFrameHost.exe)
            if exe_name.lower() == "applicationframehost.exe":
                child_hwnd = self.user32.FindWindowExW(hwnd, None, "Windows.UI.Core.CoreWindow", None)
                if child_hwnd:
                    child_pid = wintypes.DWORD()
                    self.user32.GetWindowThreadProcessId(child_hwnd, ctypes.byref(child_pid))
                    if child_pid.value > 0 and child_pid.value != pid.value:
                        child_info = self._get_process_name_and_path(child_pid.value)
                        if child_info:
                            exe_name, full_path = child_info
                            pid = child_pid

            return (pid.value, exe_name, full_path)
        except Exception as e:
            logger.debug(f"Error querying foreground window process: {e}")

        return None


class PowerBroadcastListener:
    """
    Listens for Win32 WM_POWERBROADCAST notifications via a hidden window
    and notifies PowerWatcher instantaneously upon power or display state changes.
    """

    def __init__(self, callback: Callable[[str, Any], None]):
        self.callback = callback
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._stop_event = threading.Event()
        self._hwnd: Optional[int] = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="PowerBroadcastListenerThread",
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        if self._hwnd:
            try:
                import win32gui
                import win32con
                win32gui.PostMessage(self._hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
            self._thread = None

    def _run(self) -> None:
        try:
            import win32gui
            import win32con
            import pythoncom
        except ImportError:
            logger.debug("win32gui/pythoncom unavailable; PowerBroadcastListener disabled.")
            return

        user32 = ctypes.windll.user32
        user32.RegisterPowerSettingNotification.restype = wintypes.HANDLE
        user32.RegisterPowerSettingNotification.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        user32.UnregisterPowerSettingNotification.argtypes = [wintypes.HANDLE]
        user32.UnregisterPowerSettingNotification.restype = wintypes.BOOL

        g_disp_console = WinGUID.from_uuid_str(GUID_CONSOLE_DISPLAY_STATE_STR)
        g_disp_session = WinGUID.from_uuid_str(GUID_SESSION_DISPLAY_STATUS_STR)
        g_disp_monitor = WinGUID.from_uuid_str(GUID_MONITOR_POWER_ON_STR)
        g_power = WinGUID.from_uuid_str(GUID_ACDC_POWER_SOURCE_STR)
        g_scheme = WinGUID.from_uuid_str(GUID_POWERSCHEME_PERSONALITY_STR)

        display_guids_bytes = {
            bytes(g_disp_console),
            bytes(g_disp_session),
            bytes(g_disp_monitor),
        }

        WM_POWERBROADCAST = 0x0218
        PBT_APMPOWERSTATUSCHANGE = 0x000A
        PBT_POWERSETTINGCHANGE = 0x8013
        PBT_APMRESUMESUSPEND = 0x0007
        PBT_APMRESUMEAUTOMATIC = 0x0012

        def wndproc(hwnd, msg, wparam, lparam):
            if msg == WM_POWERBROADCAST:
                if wparam == PBT_POWERSETTINGCHANGE and lparam:
                    try:
                        pbs = POWERBROADCAST_SETTING.from_address(lparam)
                        setting_bytes = bytes(pbs.PowerSetting)
                        if setting_bytes in display_guids_bytes:
                            state = pbs.Data[0] if pbs.DataLength >= 1 else 0  # 0 = Off, 1 = On, 2 = Dimmed
                            self.callback("display", state)
                        elif setting_bytes == bytes(g_power):
                            state = pbs.Data[0] if pbs.DataLength >= 1 else None
                            self.callback("power", state)
                        elif setting_bytes == bytes(g_scheme):
                            self.callback("scheme", None)
                        else:
                            self.callback("power_setting", None)
                    except Exception as ex:
                        logger.debug(f"Error reading POWERBROADCAST_SETTING: {ex}")
                elif wparam == PBT_APMPOWERSTATUSCHANGE:
                    self.callback("power", None)
                elif wparam in (PBT_APMRESUMESUSPEND, PBT_APMRESUMEAUTOMATIC):
                    self.callback("resume", wparam)
                return 1
            elif msg == win32con.WM_CLOSE:
                win32gui.DestroyWindow(hwnd)
                return 0
            elif msg == win32con.WM_DESTROY:
                win32gui.PostQuitMessage(0)
                return 0
            return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = wndproc
        class_name = f"PowerMasterListener_{threading.get_ident()}_{int(time.time())}"
        wc.lpszClassName = class_name

        try:
            hclass = win32gui.RegisterClass(wc)
        except Exception as e:
            logger.debug(f"Failed to register window class for power events: {e}")
            self._running = False
            return

        hwnd = win32gui.CreateWindow(
            class_name,
            "PowerMasterPowerEventWindow",
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            None,
        )
        if not hwnd:
            logger.debug("Failed to create window for power events.")
            self._running = False
            return

        h_notif_disp_console = user32.RegisterPowerSettingNotification(hwnd, ctypes.byref(g_disp_console), 0)
        h_notif_disp_session = user32.RegisterPowerSettingNotification(hwnd, ctypes.byref(g_disp_session), 0)
        h_notif_disp_monitor = user32.RegisterPowerSettingNotification(hwnd, ctypes.byref(g_disp_monitor), 0)
        h_notif_power = user32.RegisterPowerSettingNotification(hwnd, ctypes.byref(g_power), 0)
        h_notif_scheme = user32.RegisterPowerSettingNotification(hwnd, ctypes.byref(g_scheme), 0)

        self._hwnd = hwnd
        logger.info("PowerBroadcastListener active for instant display/AC/scheme notifications.")

        while self._running:
            try:
                pythoncom.PumpMessages()
            except Exception:
                pass
            if self._stop_event.is_set():
                break

        try:
            for h in (h_notif_disp_console, h_notif_disp_session, h_notif_disp_monitor, h_notif_power, h_notif_scheme):
                if h:
                    user32.UnregisterPowerSettingNotification(h)
            if hwnd:
                try:
                    win32gui.DestroyWindow(hwnd)
                except Exception:
                    pass
            win32gui.UnregisterClass(hclass, 0)
        except Exception as e:
            logger.debug(f"Error during listener cleanup: {e}")
        finally:
            self._hwnd = None


class PowerWatcher:
    """Coordinates power plan switching based on system triggers and rules."""

    def __init__(self, on_plan_changed: Optional[Callable[[str, str, str], None]] = None):
        """
        on_plan_changed callback signature: (new_guid, friendly_name, reason)
        """
        self._lock = threading.RLock()
        self.on_plan_changed = on_plan_changed
        self._start_time = time.time()
        self._running = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._tracked_game_pid: Optional[int] = None
        self._tracked_game_name: Optional[str] = None
        self._manual_override_guid: Optional[str] = None
        self._last_applied_guid: Optional[str] = None
        self._last_override_guid: Optional[str] = None
        self._last_reason: str = "Инициализация"
        self._is_display_off: bool = False
        self._broadcast_listener: Optional[PowerBroadcastListener] = None
        self._fast_detector = FastForegroundDetector()
        self._last_full_scan_time: float = 0.0
        self._last_thermal_change: float = 0.0
        self._last_thermal_plan: Optional[str] = None

        # Caches for game detection optimization
        self._game_dirs_cache: set[str] = set()
        self._game_dirs_prefixes: Tuple[str, ...] = ()
        self._game_names_cache: set[str] = set()
        self._last_cache_update_time: float = 0.0
        self._update_game_caches()

        # Fix C4: Check for stuck 60% throttle and safely reset
        for p_guid in [GUID_POWER_SAVER, GUID_BALANCED]:
            val = PowerPlanManager.get_processor_throttle_max(p_guid)
            if val is not None and val < 100:
                PowerPlanManager.set_processor_throttle_max(100, p_guid, activate=False)

    def _update_game_caches(self) -> None:
        """Updates the normalized caches for game directories and names."""
        with self._lock:
            now = time.monotonic()
            if self._last_cache_update_time > 0 and (now - self._last_cache_update_time < 2.0):
                return

            self._game_dirs_cache = {os.path.normpath(d).lower() for d in config.game_directories}
            self._game_dirs_prefixes = tuple(d if d.endswith(os.sep) else d + os.sep for d in self._game_dirs_cache)
            self._game_names_cache = {n.lower() for n in config.get("game_process_names", [])}
            self._last_cache_update_time = now

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._running

    @staticmethod
    def get_windows_uptime_seconds() -> float:
        """Returns the number of seconds elapsed since Windows booted."""
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.GetTickCount64.restype = ctypes.c_uint64
            ticks = kernel32.GetTickCount64()
            return float(ticks) / 1000.0
        except Exception:
            try:
                return max(0.0, time.time() - psutil.boot_time())
            except Exception:
                return 999999.0

    @property
    def startup_elapsed_seconds(self) -> float:
        """Seconds elapsed toward the startup boost threshold."""
        if config.get("boost_on_app_start", False):
            return time.time() - self._start_time
        return self.get_windows_uptime_seconds()

    @property
    def in_startup_boost(self) -> bool:
        """True if system is within the initial startup boost window."""
        return self.startup_elapsed_seconds < config.startup_boost_seconds

    @property
    def startup_remaining_seconds(self) -> float:
        """Seconds remaining in the startup boost window."""
        return max(0.0, float(config.startup_boost_seconds - self.startup_elapsed_seconds))

    @property
    def is_display_off(self) -> bool:
        with self._lock:
            return self._is_display_off


    def set_display_off(self, off: bool) -> None:
        with self._lock:
            self._is_display_off = off

    @property
    def manual_override_guid(self) -> Optional[str]:
        cfg_override = config.manual_override_guid
        if cfg_override:
            return cfg_override
        return self._manual_override_guid

    @property
    def has_manual_override(self) -> bool:
        return self.manual_override_guid is not None

    @has_manual_override.setter
    def has_manual_override(self, value: bool) -> None:
        with self._lock:
            if not value:
                self.clear_manual_override()
            elif self.manual_override_guid is None:
                curr_guid, _ = PowerPlanManager.get_active_plan()
                self.set_manual_override(curr_guid or GUID_BALANCED)

    def get_target_boost_mode_for_plan(self, plan_guid: Optional[str]) -> int:
        """
        Returns target PERFBOOSTMODE:
          - High Performance -> 2 (Aggressive Turbo Boost)
          - Balanced -> config.balanced_perf_boost_mode (3: Efficient Enabled)
          - Power Saver / Eco -> 0 (Disabled)
        """
        if not plan_guid:
            return PowerPlanManager.BOOST_DISABLED
        guid = plan_guid.lower()
        if guid == GUID_HIGH_PERFORMANCE.lower():
            return PowerPlanManager.BOOST_AGGRESSIVE
        elif guid == GUID_BALANCED.lower():
            return getattr(config, "balanced_perf_boost_mode", PowerPlanManager.BOOST_EFFICIENT)
        else:
            return PowerPlanManager.BOOST_DISABLED

    def set_manual_override(self, plan_guid: str) -> bool:
        """Sets a manual plan and holds it until cleared or overridden by battery/game."""
        with self._lock:
            self._is_display_off = False
            self._manual_override_guid = plan_guid
            saved_ok = config.set("manual_override_guid", plan_guid)
            if not saved_ok:
                logger.warning("Failed to persist manual_override_guid to disk, holding override in memory.")
            self._last_override_guid = plan_guid
            PowerPlanManager.set_active_plan(plan_guid)
            self._last_applied_guid = plan_guid
            if config.perfboostmode_disabled_in_saver:
                target_boost = self.get_target_boost_mode_for_plan(plan_guid)
                PowerPlanManager.set_perf_boost_mode(target_boost, plan_guid)
            friendly = PLAN_NAMES.get(plan_guid.lower(), plan_guid)
            self._last_reason = f"Ручной выбор: {friendly}"
            logger.info(f"Manual power plan override set to: {friendly} ({plan_guid})")
            return saved_ok

    def clear_manual_override(self) -> None:
        """Clears manual plan override and restores automatic trigger rules."""
        with self._lock:
            self._manual_override_guid = None
            self._last_override_guid = None
            if config.manual_override_guid is not None:
                config.set("manual_override_guid", None)
            logger.info("Manual power plan override cleared; resuming automatic rules.")

    @staticmethod
    def get_user_idle_seconds() -> float:
        """Returns the number of seconds since the last keyboard or mouse input."""
        try:
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
                ticks = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
                diff = (ticks - lii.dwTime) & 0xFFFFFFFF
                return diff / 1000.0
        except Exception as e:
            logger.debug(f"Failed to get user idle info: {e}")
        return 0.0

    @staticmethod
    def get_power_status() -> Tuple[bool, int]:
        """
        Returns: (is_on_ac, battery_percentage)
        ACLineStatus: 0 = Battery, 1 = AC Online, 255 = Unknown
        """
        try:
            sps = SYSTEM_POWER_STATUS()
            if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(sps)):
                is_ac = sps.ACLineStatus != 0  # 1 = AC, 255 treat as AC
                battery_pct = int(sps.BatteryLifePercent)
                if battery_pct > 100:
                    battery_pct = 100
                return is_ac, battery_pct
        except Exception as e:
            logger.debug(f"Failed to get power status via WinAPI: {e}")

        # Fallback to psutil
        try:
            b = psutil.sensors_battery()
            if b:
                return (b.power_plugged is not False), int(b.percent)
        except Exception:
            pass

        return True, 100

    @staticmethod
    def get_power_status_full() -> Tuple[bool, int, bool]:
        """
        Returns: (is_on_ac, battery_percentage, is_actively_charging)
        BatteryFlag bit 0x08 (8) = Charging actively in hardware (EC current > 0).
        """
        try:
            sps = SYSTEM_POWER_STATUS()
            if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(sps)):
                is_ac = sps.ACLineStatus != 0
                battery_pct = int(sps.BatteryLifePercent)
                if battery_pct > 100:
                    battery_pct = 100
                is_charging = bool(sps.BatteryFlag & 0x08) and (sps.BatteryFlag != 255)
                return is_ac, battery_pct, is_charging
        except Exception as e:
            logger.debug(f"Failed to get full power status via WinAPI: {e}")
        is_ac, pct = PowerWatcher.get_power_status()
        return is_ac, pct, False

    def find_active_game_process(self) -> Optional[Tuple[int, str]]:
        """
        Checks if any process from configured game directories is running.
        Optimized with O(1) Fast-Path:
        1. Query foreground active window directly via WinAPI (O(1)) - zero CPU overhead.
        2. Fast check if previously tracked game PID is still alive.
        3. Slow-path psutil.process_iter() executed only periodically (every 15s) or on initial detection.
        """
        with self._lock:
            self._update_game_caches()

            # 1. Fast-Path O(1): Foreground Window Check (Catches active game immediately)
            try:
                fg_info = self._fast_detector.get_foreground_process_info()
                if fg_info:
                    fg_pid, fg_name, fg_path = fg_info
                    norm_fg_path = os.path.normpath(fg_path).lower()
                    norm_fg_name = fg_name.lower()

                    is_game = norm_fg_name in self._game_names_cache
                    if not is_game:
                        if norm_fg_path.startswith(self._game_dirs_prefixes) or norm_fg_path in self._game_dirs_cache:
                            is_game = True

                    if is_game:
                        self._tracked_game_pid = fg_pid
                        self._tracked_game_name = fg_name
                        return (fg_pid, fg_name)
            except Exception as e:
                logger.debug(f"Fast foreground check exception: {e}")

            # 2. Fast check if currently tracked game PID is still alive
            if self._tracked_game_pid is not None:
                try:
                    p = psutil.Process(self._tracked_game_pid)
                    if p.is_running():
                        exe = p.exe()
                        if self._is_game_path(exe):
                            return (self._tracked_game_pid, self._tracked_game_name or p.name())
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                # Game closed
                self._tracked_game_pid = None
                self._tracked_game_name = None

            # 3. Slow-Path: Scan all processes only every 15 seconds to avoid CPU/C-state spikes
            now = time.time()
            if now - self._last_full_scan_time < 15.0:
                return None
            self._last_full_scan_time = now

            for p in psutil.process_iter(["pid", "name", "exe"]):
                try:
                    exe = p.info["exe"]
                    name = p.info["name"]
                    if not exe and not name:
                        continue

                    if exe:
                        norm_exe = os.path.normpath(exe).lower()
                        if norm_exe.startswith(self._game_dirs_prefixes) or norm_exe in self._game_dirs_cache:
                            self._tracked_game_pid = p.info["pid"]
                            self._tracked_game_name = name or os.path.basename(exe)
                            return (self._tracked_game_pid, self._tracked_game_name)

                    if name and name.lower() in self._game_names_cache:
                        self._tracked_game_pid = p.info["pid"]
                        self._tracked_game_name = name
                        return (self._tracked_game_pid, self._tracked_game_name)

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            return None

    def _is_game_path(self, exe: Optional[str]) -> bool:
        if not exe:
            return False
        norm_exe = os.path.normpath(exe).lower()
        if norm_exe.startswith(self._game_dirs_prefixes) or norm_exe in self._game_dirs_cache:
            return True
        return False

    def take_snapshot(self) -> SystemSnapshot:
        """Captures complete current system state."""
        is_ac, batt_pct = self.get_power_status()
        idle_sec = self.get_user_idle_seconds()
        
        # Fallback: if user is not idle (active recently or before idle timeout), display must be ON
        if self._is_display_off and idle_sec < min(60.0, float(config.idle_timeout_seconds)):
            self._is_display_off = False

        is_idle = idle_sec >= config.idle_timeout_seconds
        in_boost = self.in_startup_boost
        rem_boost = self.startup_remaining_seconds
        game_info = self.find_active_game_process()
        game_name = game_info[1] if game_info else None
        curr_guid, curr_name = PowerPlanManager.get_active_plan()

        return SystemSnapshot(
            is_on_ac=is_ac,
            battery_percent=batt_pct,
            idle_seconds=idle_sec,
            is_idle=is_idle,
            in_startup_boost=in_boost,
            active_game_process=game_name,
            current_plan_guid=curr_guid,
            current_plan_name=curr_name,
            startup_remaining_seconds=rem_boost,
            is_display_off=self._is_display_off,
        )

    def evaluate_desired_plan(self, snapshot: SystemSnapshot) -> Tuple[str, str]:
        """
        Determines target power plan based on hierarchical rule priorities:
        Priority 1: Battery mode (AC disconnected) -> Power Saver (safety override)
        Priority 2: Display off (AC connected) -> Power Saver (overrides minimized/background games)
        Priority 3: Game detected in foreground/active (on AC) -> High Performance
        Priority 3.5: User Manual Override (holds selected plan on AC when not gaming)
        Priority 4: User idle >= 3 min (on AC, no game) -> Power Saver
        Priority 5: Startup Boost (< 3 min since Windows boot, on AC, no game) -> High Performance
        Priority 6: Default AC -> Balanced
        """
        # Priority 1: Battery mode (AC disconnected) -> Power Saver (safety override)
        # Note: If user explicitly selected Balanced mode manually, honor the user's manual choice!
        if not snapshot.is_on_ac:
            override = self.manual_override_guid
            if override and override.lower() == GUID_BALANCED.lower():
                return (
                    GUID_BALANCED,
                    "Ручной выбор: Сбалансированная (Батарея)",
                )
            return (
                GUID_POWER_SAVER,
                f"Работа от батареи ({snapshot.battery_percent}%)",
            )

        # Priority 2: Game / heavy compute process detected on AC -> High Performance
        # When a game or rendering process is running on AC, High Performance MUST be preserved
        # even if the display turns off (e.g. overnight rendering / compute) until the process exits!
        if snapshot.active_game_process:
            return (
                GUID_HIGH_PERFORMANCE,
                f"Запущена игра / процесс: {snapshot.active_game_process}",
            )

        # Priority 3: User Manual Override (holds manually selected plan on AC when not gaming)
        override = self.manual_override_guid
        if override:
            name = PLAN_NAMES.get(override.lower(), override)
            return (
                override,
                f"Ручной выбор: {name}",
            )

        # Priority 4: Display turned off (on AC, no manual override, no active game/process) -> Power Saver
        if snapshot.is_display_off:
            return (
                GUID_POWER_SAVER,
                "Дисплей выключен (энергосбережение)",
            )

        # Priority 4: User idle on AC only triggers if display is actually turned off
        # While screen is active and powered on (e.g. watching movies, videos in 60 FPS, reading),
        # we preserve Balanced mode to prevent video stuttering and frame drops!
        if snapshot.is_idle and (snapshot.is_display_off or config.get("idle_switch_while_screen_on", False)):
            mins = int(snapshot.idle_seconds // 60)
            return (
                GUID_POWER_SAVER,
                f"Простой пользователя ({mins} мин)",
            )

        # Priority 4: Startup Boost
        if snapshot.in_startup_boost:
            rem_sec = int(snapshot.startup_remaining_seconds)
            return (
                GUID_HIGH_PERFORMANCE,
                f"Буст при старте (осталось {rem_sec} сек)",
            )

        # Priority 5: Default AC
        return (
            GUID_BALANCED,
            "Стандартный режим от сети",
        )

    def check_and_apply(self) -> None:
        """Single check and apply step of the monitoring loop."""
        with self._lock:
            config._maybe_reload()
            if not config.auto_switching_enabled:
                return

            snapshot = self.take_snapshot()
            desired_guid, reason = self.evaluate_desired_plan(snapshot)

            # Apply plan if different from current
            curr_guid = snapshot.current_plan_guid
            curr_override = self.manual_override_guid
            if curr_guid and curr_guid.lower() != desired_guid.lower():
                logger.info(f"Trigger activated: {reason} -> switching to {desired_guid}")
                ok, msg = PowerPlanManager.set_active_plan(desired_guid)
                if ok:
                    self._last_applied_guid = desired_guid
                    self._last_override_guid = curr_override
                    self._last_reason = reason
                    friendly = PLAN_NAMES.get(desired_guid.lower(), "Новый план")
                    if self.on_plan_changed:
                        try:
                            self.on_plan_changed(desired_guid, friendly, reason)
                        except Exception as e:
                            logger.error(f"Error in on_plan_changed callback: {e}")
            else:
                self._last_reason = reason
                plan_changed = bool(curr_guid and curr_guid.lower() != (self._last_applied_guid or "").lower())
                override_changed = (curr_override != self._last_override_guid)
                if plan_changed or override_changed:
                    self._last_applied_guid = curr_guid
                    self._last_override_guid = curr_override
                    friendly = PLAN_NAMES.get((curr_guid or "").lower(), "План")
                    if self.on_plan_changed and curr_guid:
                        try:
                            self.on_plan_changed(curr_guid, friendly, reason)
                        except Exception as e:
                            logger.error(f"Error in on_plan_changed callback: {e}")

            # --- EC Thermal Policy Sync (ASUS 0x00120075) with 5s debounce ---
            now_thermal = time.monotonic()
            ec_plan = self._last_applied_guid or curr_guid or ""
            plan_changed_thermal = (ec_plan.lower() != (self._last_thermal_plan or "").lower())

            if ec_plan.lower() == GUID_HIGH_PERFORMANCE.lower():
                target_thermal = 1  # Turbo
                target_boost = PowerPlanManager.BOOST_AGGRESSIVE  # 2: Агрессивный буст для High Performance / Игр
            elif ec_plan.lower() == GUID_BALANCED.lower():
                target_thermal = 0  # Balanced
                target_boost = getattr(config, "balanced_perf_boost_mode", PowerPlanManager.BOOST_EFFICIENT)  # 3: Эффективный буст
            else:
                target_thermal = 2  # Silent (Power Saver / Super Eco)
                target_boost = PowerPlanManager.BOOST_DISABLED    # 0: Отключен для Эко

            target_changed = (target_thermal != getattr(self, "_last_target_thermal", None)) or plan_changed_thermal
            if target_changed:
                ok_ec, _ = AsusThermalController.set_thermal_policy(target_thermal)
                if ok_ec:
                    self._last_thermal_change = now_thermal
                    self._last_thermal_plan = ec_plan
                    self._last_target_thermal = target_thermal
                if config.perfboostmode_disabled_in_saver and ec_plan:
                    PowerPlanManager.set_perf_boost_mode(target_boost, ec_plan)

            # --- Smart Battery Charge Limit Guard (0% CPU Event + Passive Drift Check) ---
            now_guard = time.monotonic()
            target_limit = int(config.battery_charge_limit)

            # 1. Отложенное подтверждение через 3 с после подключения БП / выхода из сна (перекрывает AsusOptimization)
            # Примечание: выполняется безусловно, исключая сброс при временной задержке определения AC в CmBatt.sys после S4
            if getattr(self, "_reassert_battery_limit_at", None) and now_guard >= self._reassert_battery_limit_at:
                self._reassert_battery_limit_at = None
                from asus_battery import AsusBatteryController
                AsusBatteryController.set_charge_limit_direct(target_limit)
                logger.info(f"Delayed AC guard: re-verified battery charge limit ({target_limit}%)")

            # 2. Пассивный Drift Guard: срабатывает только если батарея реально заряжается выше лимита
            if snapshot.is_on_ac and target_limit < 100 and snapshot.battery_percent > target_limit:
                _, _, is_charging_hw = self.get_power_status_full()
                pct_growing = (
                    getattr(self, "_last_ac_battery_pct", None) is not None
                    and snapshot.battery_percent > self._last_ac_battery_pct
                )
                if is_charging_hw or pct_growing:
                    if now_guard - getattr(self, "_last_battery_guard_time", 0.0) >= 60.0:
                        self._last_battery_guard_time = now_guard
                        from asus_battery import AsusBatteryController
                        AsusBatteryController.set_charge_limit_direct(target_limit)
                        logger.warning(
                            f"Drift Guard triggered: battery at {snapshot.battery_percent}% > {target_limit}% "
                            f"(hw_charging={is_charging_hw}, growing={pct_growing}) -> limit re-enforced."
                        )
            self._last_ac_battery_pct = snapshot.battery_percent if snapshot.is_on_ac else None

    def _on_broadcast_event(self, event_type: str, data: Any) -> None:
        """Instant event handler from PowerBroadcastListener."""
        with self._lock:
            if event_type == "display":
                is_off = (data == 0)
                idle_sec = self.get_user_idle_seconds()
                if is_off and idle_sec < min(30.0, float(config.idle_timeout_seconds)):
                    is_off = False
                self._is_display_off = is_off
                logger.info(f"Instant display state notification: {'OFF' if is_off else 'ON'}")
                self.check_and_apply()
            elif event_type == "power":
                logger.info("Instant power status change notification received.")
                try:
                    is_ac, _ = self.get_power_status()
                    if is_ac:
                        from asus_battery import AsusBatteryController
                        AsusBatteryController.set_charge_limit_direct(config.battery_charge_limit)
                        self._reassert_battery_limit_at = time.monotonic() + 3.0
                except Exception as ex:
                    logger.debug(f"Power change battery limit assertion failed: {ex}")
                self.check_and_apply()
            elif event_type in ("scheme", "power_setting"):
                logger.info(f"Instant power scheme/setting notification received ({event_type}).")
                config._maybe_reload(force=True)
                curr_guid, curr_name = PowerPlanManager.get_active_plan()
                curr_override = self.manual_override_guid
                plan_changed = bool(curr_guid and curr_guid.lower() != (self._last_applied_guid or "").lower())
                override_changed = (curr_override != self._last_override_guid)
                if plan_changed:
                    logger.info(f"External power scheme change detected in Windows: {curr_guid} ({curr_name})")
                    self._manual_override_guid = curr_guid
                    config.set("manual_override_guid", curr_guid)
                    self._last_applied_guid = curr_guid
                    self._last_override_guid = curr_guid
                    if self.on_plan_changed and curr_guid:
                        try:
                            self.on_plan_changed(curr_guid, curr_name, "Смена схемы питания")
                        except Exception as e:
                            logger.error(f"Error in on_plan_changed callback: {e}")
                elif override_changed:
                    self._last_override_guid = curr_override
                    if self.on_plan_changed and curr_guid:
                        try:
                            self.on_plan_changed(curr_guid, curr_name, "Смена схемы питания")
                        except Exception as e:
                            logger.error(f"Error in on_plan_changed callback: {e}")
                self.check_and_apply()
            elif event_type == "resume":
                logger.info(f"Instant system resume notification received (0x{data:04X} / Resume Event).")
                self._is_display_off = False
                # M-2: Hardware battery limit re-application on resume
                try:
                    from asus_battery import AsusBatteryController
                    AsusBatteryController.set_charge_limit_direct(config.battery_charge_limit)
                    self._reassert_battery_limit_at = time.monotonic() + 3.0
                    logger.info(f"Resume: ASUS battery charge limit reapplied ({config.battery_charge_limit}%)")
                except Exception as ex:
                    logger.debug(f"Failed to reapply battery limit on resume: {ex}")
                self.check_and_apply()

    def _monitor_loop(self) -> None:
        logger.info("PowerWatcher background monitor thread started.")
        while self._running:
            try:
                self.check_and_apply()
            except Exception as e:
                logger.error(f"Unexpected error in monitor loop: {e}", exc_info=True)
            if self._stop_event.wait(config.poll_interval_seconds):
                break
        logger.info("PowerWatcher background monitor thread stopped.")

    def start(self) -> None:
        """Starts the background monitor thread and event listener."""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()

        # Start instant event listener
        self._broadcast_listener = PowerBroadcastListener(self._on_broadcast_event)
        self._broadcast_listener.start()

        # Start polling loop
        self._thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="PowerWatcherThread",
        )
        self._thread.start()

    def stop(self) -> None:
        """Stops background monitor thread and event listener."""
        self._running = False
        self._stop_event.set()
        if self._broadcast_listener:
            self._broadcast_listener.stop()
            self._broadcast_listener = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
            self._thread = None
