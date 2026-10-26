"""
PowerMaster_ASUS - Main Dashboard GUI
Отображает текущий статус, телеметрию, активный план питания и позволяет быстро переключать режимы.
"""

from __future__ import annotations
import ctypes
from ctypes import wintypes
import logging
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable

from config import (
    APP_TITLE,
    APP_VERSION,
    config,
    GUID_HIGH_PERFORMANCE,
    GUID_BALANCED,
    GUID_POWER_SAVER,
)
from windows_energy_saver import WindowsEnergySaver

logger = logging.getLogger("PowerMaster.Dashboard")

ERROR_ALREADY_EXISTS = 183
DASHBOARD_MUTEX_NAME = "Local\\PowerMaster_ASUS_Dashboard_Mutex"


class AsusWinIOFanReader:
    """
    Reads genuine dynamic CPU and GPU fan RPM via AsusSAIO driver and AsusWinIO64.dll.
    Falls back gracefully if the service or DLL is missing, inaccessible, or returns <= 0.
    """

    _instance: Optional["AsusWinIOFanReader"] = None

    @classmethod
    def get_instance(cls) -> "AsusWinIOFanReader":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        if cls._instance is not None:
            try:
                cls._instance.close()
            except Exception:
                pass
            cls._instance = None

    def __init__(self):
        self._dll = None
        self._initialized = False
        self._service_attempted = False
        self._dll_path: Optional[str] = None
        self._init_winio()

    def _ensure_service_running(self) -> bool:
        """Attempts to start the asussaio service if it is stopped."""
        if self._service_attempted:
            return False
        self._service_attempted = True

        # 1. Try win32service SCM API
        try:
            import win32service
            scm = win32service.OpenSCManager(
                None, None, win32service.SC_MANAGER_CONNECT | win32service.SC_MANAGER_ENUMERATE_SERVICE
            )
            try:
                svc = win32service.OpenService(
                    scm, "asussaio", win32service.SERVICE_QUERY_STATUS | win32service.SERVICE_START
                )
                status = win32service.QueryServiceStatus(svc)
                if status[1] == win32service.SERVICE_RUNNING:
                    win32service.CloseServiceHandle(svc)
                    return True
                try:
                    win32service.StartService(svc, None)
                    win32service.CloseServiceHandle(svc)
                    return True
                except Exception as ex:
                    logger.debug(f"win32service.StartService asussaio failed: {ex}")
                win32service.CloseServiceHandle(svc)
            finally:
                win32service.CloseServiceHandle(scm)
        except Exception as e:
            logger.debug(f"win32service SCM access failed: {e}")

        # 2. Try sc.exe start asussaio
        try:
            import subprocess
            startupinfo = None
            creationflags = 0
            if sys.platform == "win32":
                creationflags = 0x08000000  # CREATE_NO_WINDOW
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            res = subprocess.run(
                ["sc.exe", "start", "asussaio"],
                capture_output=True,
                text=True,
                encoding="cp866",
                errors="replace",
                timeout=3,
                startupinfo=startupinfo,
                creationflags=creationflags,
            )
            return res.returncode == 0
        except Exception as ex2:
            logger.debug(f"sc.exe start asussaio failed: {ex2}")
            return False

    @staticmethod
    def find_dll_path() -> Optional[str]:
        """Locates AsusWinIO64.dll across driver store and ASUS utility paths."""
        import glob
        import os
        search_patterns = [
            r"C:\Windows\System32\DriverStore\FileRepository\asussci2.inf_amd64_*\ASUSSystemAnalysis\AsusWinIO64.dll",
            r"C:\Program Files\ASUS\ARMOURY CRATE Lite Service\AsusWinIO64.dll",
            r"C:\Program Files (x86)\ASUS\ASUS System Control Interface v3\*\AsusWinIO64.dll",
            r"C:\Program Files (x86)\ASUS\ArmouryDevice\dll\AsusWinIO64.dll",
            r"C:\Windows\System32\AsusWinIO64.dll",
        ]
        for pattern in search_patterns:
            try:
                matches = glob.glob(pattern)
                if matches:
                    valid_matches = [m for m in matches if os.path.isfile(m)]
                    if valid_matches:
                        valid_matches.sort(key=os.path.getmtime, reverse=True)
                        return valid_matches[0]
            except Exception as e:
                logger.debug(f"Error searching pattern {pattern}: {e}")

        import os
        local_cand = os.path.join(os.path.dirname(__file__), "AsusWinIO64.dll")
        if os.path.isfile(local_cand):
            return local_cand
        return None

    def _init_winio(self) -> None:
        """Loads AsusWinIO64.dll and calls InitializeWinIo()."""
        try:
            self._ensure_service_running()
            dll_path = self.find_dll_path()
            if not dll_path:
                logger.debug("AsusWinIO64.dll not found")
                return

            self._dll_path = dll_path
            import os
            dll_dir = os.path.dirname(dll_path)
            cookie = None
            try:
                if hasattr(os, "add_dll_directory") and os.path.isdir(dll_dir):
                    cookie = os.add_dll_directory(dll_dir)
                dll = ctypes.WinDLL(dll_path)
            finally:
                if cookie is not None:
                    try:
                        cookie.close()
                    except Exception:
                        pass

            if hasattr(dll, "InitializeWinIo") and hasattr(dll, "HealthyTable_FanRPM"):
                dll.InitializeWinIo.restype = ctypes.c_bool
                dll.HealthyTable_FanRPM.argtypes = [ctypes.c_int]
                dll.HealthyTable_FanRPM.restype = ctypes.c_int
                if hasattr(dll, "ShutdownWinIo"):
                    dll.ShutdownWinIo.restype = ctypes.c_bool

                if dll.InitializeWinIo():
                    self._dll = dll
                    self._initialized = True
                    logger.info(f"Initialized AsusWinIO from {dll_path}")
                else:
                    logger.debug("AsusWinIO InitializeWinIo returned False")
        except Exception as e:
            logger.debug(f"Failed to load or initialize AsusWinIO: {e}")
            self._dll = None
            self._initialized = False

    def get_fan_rpm(self, fan_index: int) -> Optional[int]:
        """
        Queries Fan RPM (0 for CPU, 1 for GPU).
        Returns positive RPM integer, or None if failed / <= 0.
        """
        if not self._initialized or not self._dll:
            return None
        try:
            rpm = self._dll.HealthyTable_FanRPM(fan_index)
            if isinstance(rpm, int) and rpm > 0:
                return rpm
        except Exception as e:
            logger.debug(f"HealthyTable_FanRPM({fan_index}) error: {e}")
        return None

    def get_cpu_fan_rpm(self) -> Optional[int]:
        return self.get_fan_rpm(0)

    def get_gpu_fan_rpm(self) -> Optional[int]:
        return self.get_fan_rpm(1)

    def close(self) -> None:
        """Shuts down WinIO and cleans up driver handle."""
        if self._initialized and self._dll is not None:
            try:
                if hasattr(self._dll, "ShutdownWinIo"):
                    self._dll.ShutdownWinIo()
            except Exception as e:
                logger.debug(f"Error in ShutdownWinIo: {e}")
            self._initialized = False
            self._dll = None
        if AsusWinIOFanReader._instance is self:
            AsusWinIOFanReader._instance = None


def _cleanup_winio() -> None:
    try:
        reader = AsusWinIOFanReader._instance
        if reader is not None:
            reader.close()
    except Exception:
        pass


import atexit
atexit.register(_cleanup_winio)


class DynamicCpuTelemetry:
    """Queries live dynamic CPU frequency using Windows Performance Counters with psutil fallback."""

    def __init__(self, fan_reader: Optional[AsusWinIOFanReader] = None):
        self._pdh_query = None
        self._counter_actual = None   # Actual Frequency (MHz) — точный как в Task Manager
        self._counter_perf = None     # % Processor Performance — fallback
        self._base_mhz = 3000.0
        self._fan_reader = fan_reader
        self._init_pdh()

    def _init_pdh(self) -> None:
        try:
            import win32pdh
            if hasattr(win32pdh, 'AddEnglishCounter'):
                self._pdh_query = win32pdh.OpenQuery()
                # Первичный счётчик: Actual Frequency — реальная мгновенная частота (МГц) с Turbo
                try:
                    self._counter_actual = win32pdh.AddEnglishCounter(
                        self._pdh_query, r"\Processor Information(_Total)\Actual Frequency"
                    )
                except Exception:
                    self._counter_actual = None
                # Резервный счётчик: % Processor Performance × base_clock
                try:
                    self._counter_perf = win32pdh.AddEnglishCounter(
                        self._pdh_query, r"\Processor Information(_Total)\% Processor Performance"
                    )
                    c_base = win32pdh.AddEnglishCounter(
                        self._pdh_query, r"\Processor Information(_Total)\Processor Frequency"
                    )
                    win32pdh.CollectQueryData(self._pdh_query)
                    import time
                    time.sleep(0.05)
                    win32pdh.CollectQueryData(self._pdh_query)
                    _, base_val = win32pdh.GetFormattedCounterValue(c_base, win32pdh.PDH_FMT_DOUBLE)
                    if base_val > 0:
                        self._base_mhz = float(base_val)
                    win32pdh.RemoveCounter(c_base)
                except Exception:
                    pass
                win32pdh.CollectQueryData(self._pdh_query)
        except Exception as e:
            logger.debug(f"PDH counter init exception: {e}")
            self.close()

    def get_frequency_ghz(self) -> Optional[float]:
        if self._pdh_query:
            try:
                import win32pdh
                win32pdh.CollectQueryData(self._pdh_query)
                # Первичный: Actual Frequency (МГц) — прямая реальная частота как в Task Manager
                if self._counter_actual:
                    _, actual_mhz = win32pdh.GetFormattedCounterValue(self._counter_actual, win32pdh.PDH_FMT_DOUBLE)
                    if actual_mhz > 0:
                        return actual_mhz / 1000.0
                # Резервный: % Processor Performance × base_clock
                if self._counter_perf:
                    _, perf_val = win32pdh.GetFormattedCounterValue(self._counter_perf, win32pdh.PDH_FMT_DOUBLE)
                    if perf_val > 0:
                        return self._base_mhz * (perf_val / 100.0) / 1000.0
            except Exception as e:
                logger.debug(f"Error reading PDH counter value: {e}")

        # Fallback to psutil
        try:
            import psutil
            cpu_freq = psutil.cpu_freq()
            if cpu_freq and cpu_freq.current:
                return cpu_freq.current / 1000.0
        except Exception:
            pass
        return None

    _temp_cache: Optional[float] = None
    _temp_cache_time: float = 0.0
    _temp_cb_failures: int = 0
    _temp_cb_open_until: float = 0.0

    def get_temperature_c(self) -> Optional[float]:
        now = time.monotonic()
        if now < self._temp_cb_open_until:
            return self._temp_cache
        if self._temp_cache is not None and (now - self._temp_cache_time) < 5.0:
            return self._temp_cache

        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            try:
                loc = win32com.client.Dispatch("WbemScripting.SWbemLocator")

                # Primary: root\cimv2 Win32_PerfFormattedData_Counters_ThermalZoneInformation (works without admin)
                try:
                    cim = loc.ConnectServer(".", r"root\cimv2")
                    tz_items = cim.ExecQuery(
                        "SELECT Temperature, HighPrecisionTemperature FROM Win32_PerfFormattedData_Counters_ThermalZoneInformation"
                    )
                    for item in tz_items:
                        hp = getattr(item, "HighPrecisionTemperature", None)
                        if hp is not None and hp > 2732:
                            c = (float(hp) - 2732.0) / 10.0
                            if 20.0 <= c <= 115.0:
                                self._temp_cache = c
                                self._temp_cache_time = now
                                self._temp_cb_failures = 0
                                return c
                        temp = getattr(item, "Temperature", None)
                        if temp is not None and temp > 273:
                            c = float(temp) - 273.15
                            if 20.0 <= c <= 115.0:
                                self._temp_cache = c
                                self._temp_cache_time = now
                                self._temp_cb_failures = 0
                                return c
                except Exception as e:
                    logger.debug(f"ThermalZoneInformation query exception: {e}")

                # Fallback: root\wmi MSAcpi_ThermalZoneTemperature (requires admin)
                try:
                    wmi_svc = loc.ConnectServer(".", r"root\wmi")
                    tz_items = wmi_svc.ExecQuery(
                        "SELECT CurrentTemperature FROM MSAcpi_ThermalZoneTemperature"
                    )
                    for item in tz_items:
                        ct = getattr(item, "CurrentTemperature", None)
                        if ct is not None and ct > 2732:
                            c = (float(ct) - 2732.0) / 10.0
                            if 20.0 <= c <= 115.0:
                                self._temp_cache = c
                                self._temp_cache_time = now
                                self._temp_cb_failures = 0
                                return c
                except Exception as e:
                    logger.debug(f"MSAcpi_ThermalZoneTemperature query exception: {e}")
            finally:
                pythoncom.CoUninitialize()
        except Exception as e:
            logger.debug(f"get_temperature_c exception: {e}")

        self._temp_cb_failures += 1
        if self._temp_cb_failures >= 3:
            self._temp_cb_open_until = now + 60.0
            logger.debug("CPU temperature WMI unsupported; Circuit Breaker opened for 60s")
        return None

    @staticmethod
    def _parse_fan_result(res) -> Optional[int]:
        if res is None or isinstance(res, bool):
            return None
        try:
            raw = None
            if isinstance(res, (int, float)):
                raw = res
            elif hasattr(res, "device_status"):
                raw = res.device_status
            elif hasattr(res, "ReturnValue"):
                raw = res.ReturnValue
            elif hasattr(res, "Properties_"):
                try:
                    raw = res.Properties_("device_status").Value
                except Exception:
                    try:
                        raw = res.Properties_("ReturnValue").Value
                    except Exception:
                        pass
            elif isinstance(res, (tuple, list)) and len(res) > 0:
                raw = res[0]
            else:
                raw = res

            if raw is None or isinstance(raw, bool):
                return None

            val = int(raw)
            if val == 0x00010019:
                return None
            if val < 0 or val == 65535:
                return None

            rpm = val & 0xFFFF
            if rpm == 65535:
                return None
            if 0 < rpm < 100:
                rpm = rpm * 100
            return rpm
        except Exception:
            return None

    def get_fan_rpm(self) -> Optional[int]:
        # 1. Try AsusWinIO driver/DLL
        try:
            reader = self._fan_reader if self._fan_reader is not None else AsusWinIOFanReader.get_instance()
            rpm = reader.get_cpu_fan_rpm()
            if rpm is not None and rpm >= 0:
                return rpm
        except Exception as e:
            logger.debug(f"AsusWinIO CPU RPM error: {e}")

        # 2. Fallback to ACPI WMI
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            try:
                loc = win32com.client.Dispatch("WbemScripting.SWbemLocator")
                wmi_svc = loc.ConnectServer(".", r"root\wmi")
                asus_items = wmi_svc.ExecQuery("SELECT * FROM AsusAtkWmi_WMNB")
                for item in asus_items:
                    # 0x00110013 is typically CPU Fan RPM on ASUS
                    res = None
                    try:
                        res = item.DSTS(0x00110013)
                    except Exception:
                        pass
                    if res is None:
                        try:
                            in_params = item.Methods_("DSTS").InParameters.SpawnInstance_()
                            in_params.Device_ID = 0x00110013
                            res = item.ExecMethod_("DSTS", in_params)
                        except Exception:
                            pass
                    rpm = self._parse_fan_result(res)
                    if rpm is not None:
                        return rpm
            finally:
                pythoncom.CoUninitialize()
        except Exception as e:
            logger.debug(f"ACPI WMI CPU fan RPM error: {e}")
        return None

    def close(self) -> None:
        if self._pdh_query:
            try:
                import win32pdh
                win32pdh.CloseQuery(self._pdh_query)
            except Exception:
                pass
            self._pdh_query = None
            self._counter_perf = None


class GpuTelemetry:
    """Queries NVIDIA GPU telemetry via NVML and WMI fallback."""

    NVML_TEMPERATURE_GPU = 0
    NVML_CLOCK_GRAPHICS = 0

    def __init__(self, fan_reader: Optional[AsusWinIOFanReader] = None):
        self._nvml = None
        self._handle = None
        self._initialized = False
        self._fan_reader = fan_reader
        self._init_nvml()

    def _init_nvml(self):
        try:
            self._nvml = ctypes.WinDLL("nvml.dll")
            res = self._nvml.nvmlInit_v2()
            if res == 0: # NVML_SUCCESS
                self._handle = ctypes.c_void_p()
                res_handle = self._nvml.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(self._handle))
                if res_handle == 0:
                    self._initialized = True
        except Exception as e:
            logger.debug(f"NVML init failed: {e}")

    def get_utilization_pct(self) -> Optional[int]:
        if not self._initialized:
            return None
        try:
            class nvmlUtilization_t(ctypes.Structure):
                _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]
            util = nvmlUtilization_t()
            res = self._nvml.nvmlDeviceGetUtilizationRates(self._handle, ctypes.byref(util))
            if res == 0:
                return int(util.gpu)
        except Exception:
            pass
        return None

    def get_clock_mhz(self) -> Optional[int]:
        if not self._initialized:
            return None
        try:
            clock = ctypes.c_uint()
            res = self._nvml.nvmlDeviceGetClockInfo(self._handle, self.NVML_CLOCK_GRAPHICS, ctypes.byref(clock))
            if res == 0:
                return int(clock.value)
        except Exception:
            pass
        return None

    def get_temperature_c(self) -> Optional[int]:
        if not self._initialized:
            return None
        try:
            temp = ctypes.c_uint()
            res = self._nvml.nvmlDeviceGetTemperature(self._handle, self.NVML_TEMPERATURE_GPU, ctypes.byref(temp))
            if res == 0:
                return int(temp.value)
        except Exception:
            pass
        return None

    def get_fan_rpm(self) -> Optional[int]:
        # 1. Try AsusWinIO driver/DLL
        try:
            reader = self._fan_reader if self._fan_reader is not None else AsusWinIOFanReader.get_instance()
            rpm = reader.get_gpu_fan_rpm()
            if rpm is not None and rpm >= 0:
                return rpm
        except Exception as e:
            logger.debug(f"AsusWinIO GPU RPM error: {e}")

        # 2. Try ASUS WMI for GPU Fan (0x00110014)
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            try:
                loc = win32com.client.Dispatch("WbemScripting.SWbemLocator")
                wmi_svc = loc.ConnectServer(".", r"root\wmi")
                asus_items = wmi_svc.ExecQuery("SELECT * FROM AsusAtkWmi_WMNB")
                for item in asus_items:
                    # 0x00110014 is typically GPU Fan RPM on ASUS
                    res = None
                    try:
                        res = item.DSTS(0x00110014)
                    except Exception:
                        pass
                    if res is None:
                        try:
                            in_params = item.Methods_("DSTS").InParameters.SpawnInstance_()
                            in_params.Device_ID = 0x00110014
                            res = item.ExecMethod_("DSTS", in_params)
                        except Exception:
                            pass
                    rpm = DynamicCpuTelemetry._parse_fan_result(res)
                    if rpm is not None:
                        return rpm
            finally:
                pythoncom.CoUninitialize()
        except Exception as e:
            logger.debug(f"ACPI WMI GPU fan RPM error: {e}")

        # Fallback to NVML
        if not self._initialized:
            return None
        try:
            fan_speed = ctypes.c_uint()
            res = self._nvml.nvmlDeviceGetFanSpeed(self._handle, ctypes.byref(fan_speed))
            if res == 0:
                return int(fan_speed.value)
        except Exception:
            pass
        return None

    def close(self) -> None:
        if self._initialized and self._nvml:
            try:
                self._nvml.nvmlShutdown()
            except Exception:
                pass
        self._initialized = False
        self._nvml = None
        self._handle = None


# UI Themes and Scales Configuration for Dashboard (Accessibility & Visual Enhancement)
THEMES = {
    "cyber_dark": {
        "name": "TUF Cyber Dark",
        "bg_main": "#1e1e2e",
        "bg_card": "#2b2b3b",
        "bg_card_inner": "#252535",
        "fg_main": "#cdd6f4",
        "fg_muted": "#a6adc8",
        "telemetry_val_fg": "#FDF6E2",
        "border": "#45475a",
        "accent": "#ff9f1c",
        "btn_bg": "#313244",
        "btn_active": "#45475a",
        "btn_fg": "#cdd6f4",
        "btn_accent_bg": "#89b4fa",
        "btn_accent_fg": "#1e1e2e",
        "turbo_fg": "#f38ba8",
        "balance_fg": "#89b4fa",
        "eco_fg": "#a6e3a1",
        "warn_fg": "#f9e2af",
        "admin_ok": "#a6e3a1",
        "admin_bad": "#f38ba8",
    },
    "clean_minimalist": {
        "name": "Clean Minimalist",
        "bg_main": "#1e2022",
        "bg_card": "#2a2c31",
        "bg_card_inner": "#32353c",
        "fg_main": "#f8fafc",
        "fg_muted": "#94a3b8",
        "telemetry_val_fg": "#F4EFEA",
        "border": "#3f444e",
        "accent": "#388bfd",
        "btn_bg": "#373a40",
        "btn_active": "#4a4e56",
        "btn_fg": "#f8fafc",
        "btn_accent_bg": "#388bfd",
        "btn_accent_fg": "#ffffff",
        "turbo_fg": "#f87171",
        "balance_fg": "#60a5fa",
        "eco_fg": "#34d399",
        "warn_fg": "#fbbf24",
        "admin_ok": "#34d399",
        "admin_bad": "#f87171",
    },
    "oled_contrast": {
        "name": "High-Contrast OLED",
        "bg_main": "#000000",
        "bg_card": "#0c0c0c",
        "bg_card_inner": "#161616",
        "fg_main": "#ffffff",
        "fg_muted": "#00ffff",
        "telemetry_val_fg": "#FFF8E7",
        "border": "#00ffff",
        "accent": "#00ffff",
        "btn_bg": "#1c1c1c",
        "btn_active": "#333333",
        "btn_fg": "#ffffff",
        "btn_accent_bg": "#00ffff",
        "btn_accent_fg": "#000000",
        "turbo_fg": "#ff3344",
        "balance_fg": "#00bfff",
        "eco_fg": "#00ff66",
        "warn_fg": "#ffff00",
        "admin_ok": "#00ff66",
        "admin_bad": "#ff3344",
    },
    "light": {
        "name": "Light Modern",
        "bg_main": "#f4f5f7",
        "bg_card": "#ffffff",
        "bg_card_inner": "#e9ebf0",
        "fg_main": "#1e293b",
        "fg_muted": "#64748b",
        "telemetry_val_fg": "#F4EFEA",
        "border": "#cbd5e1",
        "accent": "#0284c7",
        "btn_bg": "#e2e8f0",
        "btn_active": "#cbd5e1",
        "btn_fg": "#0f172a",
        "btn_accent_bg": "#0284c7",
        "btn_accent_fg": "#ffffff",
        "turbo_fg": "#dc2626",
        "balance_fg": "#2563eb",
        "eco_fg": "#16a34a",
        "warn_fg": "#d97706",
        "admin_ok": "#16a34a",
        "admin_bad": "#dc2626",
    },
}

SCALES = {
    1.0: {
        "name": "100%",
        "font_base": ("Segoe UI", 10),
        "font_base_bold": ("Segoe UI", 10, "bold"),
        "font_card_header": ("Segoe UI", 11, "bold"),
        "font_header": ("Segoe UI", 12, "bold"),
        "font_mode": ("Segoe UI", 14, "bold"),
        "font_telemetry_val": ("Segoe UI", 11, "bold"),
        "font_btn": ("Segoe UI", 10),
        "font_btn_bold": ("Segoe UI", 10, "bold"),
        "win_w": 620,
        "win_h": 700,
    },
    1.25: {
        "name": "125%",
        "font_base": ("Segoe UI", 12),
        "font_base_bold": ("Segoe UI", 12, "bold"),
        "font_card_header": ("Segoe UI", 13, "bold"),
        "font_header": ("Segoe UI", 14, "bold"),
        "font_mode": ("Segoe UI", 17, "bold"),
        "font_telemetry_val": ("Segoe UI", 13, "bold"),
        "font_btn": ("Segoe UI", 11),
        "font_btn_bold": ("Segoe UI", 11, "bold"),
        "win_w": 730,
        "win_h": 770,
    },
    1.5: {
        "name": "150%",
        "font_base": ("Segoe UI", 14),
        "font_base_bold": ("Segoe UI", 14, "bold"),
        "font_card_header": ("Segoe UI", 15, "bold"),
        "font_header": ("Segoe UI", 17, "bold"),
        "font_mode": ("Segoe UI", 21, "bold"),
        "font_telemetry_val": ("Segoe UI", 15, "bold"),
        "font_btn": ("Segoe UI", 12),
        "font_btn_bold": ("Segoe UI", 12, "bold"),
        "win_w": 840,
        "win_h": 850,
    },
}


_init_ready_event = threading.Event()
_prewarm_thread = None


class DashboardWindow:
    _instance: Optional["DashboardWindow"] = None

    def __init__(
        self,
        tray_app=None,
        config_obj=None,
        watcher=None,
        on_close: Optional[Callable[[], None]] = None,
        is_standalone: bool = False,
        cpu_telemetry: Optional[DynamicCpuTelemetry] = None,
        gpu_telemetry: Optional[GpuTelemetry] = None,
        initially_hidden: bool = False,
    ):
        self.tray_app = tray_app
        if config_obj is None:
            from config import config as default_config
            self.config = default_config
        else:
            self.config = config_obj
        self.watcher = watcher
        self.on_close_callback = on_close
        self.is_standalone = is_standalone
        self.initially_hidden = initially_hidden
        self.telemetry_timer = None
        self.cpu_telemetry = cpu_telemetry if cpu_telemetry is not None else DynamicCpuTelemetry()
        self.gpu_telemetry = gpu_telemetry if gpu_telemetry is not None else GpuTelemetry()

        self.current_theme = str(getattr(self.config, "ui_theme", "cyber_dark"))
        if self.current_theme not in THEMES:
            self.current_theme = "cyber_dark"

        try:
            self.current_scale = float(getattr(self.config, "ui_scale", 1.0))
        except (ValueError, TypeError):
            self.current_scale = 1.0
        if self.current_scale not in SCALES:
            self.current_scale = 1.0

        s = SCALES[self.current_scale]
        t = THEMES[self.current_theme]

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(f"{APP_TITLE} v{APP_VERSION} - Панель управления")
        self.root.geometry(f"{s['win_w']}x{s['win_h']}")
        self.root.resizable(False, False)
        self.root.configure(bg=t["bg_main"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_delete)

        # Style
        self.style = ttk.Style(self.root)
        self.style.theme_use("clam")

        self._build_ui()
        self._apply_theme_and_styles()
        self._center_window(s["win_w"], s["win_h"])

        if initially_hidden:
            try:
                self.root.withdraw()
            except Exception:
                pass
        else:
            try:
                self.root.deiconify()
            except Exception:
                pass
            self._start_telemetry_loop()

        # Mark thread id on root for safe cross-thread apartment dispatch
        try:
            self.root._gui_thread_id = threading.get_ident()
        except Exception:
            pass
        DashboardWindow._instance = self
        _init_ready_event.set()

    def _center_window(self, width: int, height: int):
        self.root.update_idletasks()
        try:
            req_w = self.root.winfo_reqwidth()
            req_h = self.root.winfo_reqheight()
        except Exception:
            req_w = 0
            req_h = 0
        actual_w = max(width, req_w)
        actual_h = max(height, req_h)
        try:
            scr_w = self.root.winfo_screenwidth()
            scr_h = self.root.winfo_screenheight()
        except tk.TclError:
            return
        x = max(0, (scr_w // 2) - (actual_w // 2))
        y = max(0, (scr_h // 2) - (actual_h // 2))
        self.root.geometry(f"{actual_w}x{actual_h}+{x}+{y}")

    def lift_to_front(self):
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(100, lambda: self.root.attributes("-topmost", False))
            self.root.focus_force()
        except Exception:
            pass
        self._update_ui_state()
        self._start_telemetry_loop()

    def hide_window(self):
        logger.info("Withdrawing dashboard window to tray (fast cache kept)")
        if getattr(self, "telemetry_timer", None):
            try:
                self.root.after_cancel(self.telemetry_timer)
            except Exception:
                pass
            self.telemetry_timer = None
        try:
            self.root.withdraw()
        except Exception:
            pass
        if self.on_close_callback:
            try:
                self.on_close_callback()
            except Exception as e:
                logger.debug(f"Error in dashboard on_close_callback: {e}")

    def _on_window_delete(self):
        if not self.is_standalone:
            self.hide_window()
        else:
            self._on_close()

    def _on_close(self):
        logger.info("Closing Dashboard window")
        if getattr(self, "telemetry_timer", None):
            try:
                self.root.after_cancel(self.telemetry_timer)
            except Exception:
                pass
            self.telemetry_timer = None
        if getattr(self, "cpu_telemetry", None):
            try:
                self.cpu_telemetry.close()
            except Exception:
                pass
        if getattr(self, "gpu_telemetry", None):
            try:
                self.gpu_telemetry.close()
            except Exception:
                pass
        _cleanup_winio()
        if self.on_close_callback:
            try:
                self.on_close_callback()
            except Exception as e:
                logger.error(f"Error in dashboard on_close_callback: {e}")
        try:
            self.root.destroy()
        except Exception:
            pass
        DashboardWindow._instance = None
        if self.is_standalone:
            sys.exit(0)

    def set_theme(self, theme_key: str):
        if theme_key not in THEMES:
            return
        self.current_theme = theme_key
        try:
            self.config.ui_theme = theme_key
        except Exception:
            pass
        self._apply_theme_and_styles()
        self._update_ui_state()

    def set_scale(self, scale_val: float):
        if scale_val not in SCALES:
            return
        self.current_scale = scale_val
        try:
            self.config.ui_scale = scale_val
        except Exception:
            pass
        self._apply_theme_and_styles()
        s = SCALES[self.current_scale]
        self._center_window(s["win_w"], s["win_h"])
        self._update_ui_state()

    def _apply_theme_and_styles(self):
        t = THEMES[self.current_theme]
        s = SCALES[self.current_scale]

        try:
            self.root.configure(bg=t["bg_main"])
        except Exception:
            pass

        self.style.configure("TFrame", background=t["bg_main"])
        self.style.configure("Card.TFrame", background=t["bg_card"], relief="flat")
        self.style.configure("SubCard.TFrame", background=t.get("bg_card_inner", t["bg_card"]), relief="flat")
        self.style.configure("TLabel", background=t["bg_main"], foreground=t["fg_main"], font=s["font_base"])
        self.style.configure("Card.TLabel", background=t["bg_card"], foreground=t["fg_main"], font=s["font_base"])
        self.style.configure("SubCard.TLabel", background=t.get("bg_card_inner", t["bg_card"]), foreground=t["fg_main"], font=s["font_base"])
        self.style.configure("SubCardHeader.TLabel", background=t.get("bg_card_inner", t["bg_card"]), foreground=t["fg_main"], font=s["font_card_header"])
        self.style.configure("CardHeader.TLabel", background=t["bg_card"], foreground=t["fg_main"], font=s["font_card_header"])
        self.style.configure("CardStatic.TLabel", background=t.get("bg_card_inner", t["bg_card"]), foreground=t.get("fg_muted", "#888888"), font=s["font_base"])
        val_fg = t.get("telemetry_val_fg", "#FFF8E7")
        self.style.configure("CardVal.TLabel", background=t.get("bg_card_inner", t["bg_card"]), foreground=val_fg, font=s["font_telemetry_val"])
        self.style.configure("TButton", background=t["btn_bg"], foreground=t["btn_fg"], font=s["font_btn"], borderwidth=0, padding=4)
        self.style.map("TButton", background=[("active", t["btn_active"])])
        self.style.configure("Accent.TButton", background=t["btn_accent_bg"], foreground=t["btn_accent_fg"], font=s["font_btn_bold"], borderwidth=0, padding=4)
        self.style.map("Accent.TButton", background=[("active", t["btn_active"])])
        self.style.configure("Danger.TButton", background=t["turbo_fg"], foreground="#1e1e2e", font=s["font_btn_bold"], borderwidth=0, padding=4)
        self.style.map("Danger.TButton", background=[("active", "#fca311")])

        if hasattr(self, 'theme_btns'):
            for k, btn in self.theme_btns.items():
                try:
                    btn.configure(style="Accent.TButton" if self.current_theme == k else "TButton")
                except Exception:
                    pass

        if hasattr(self, 'scale_btns'):
            for v, btn in self.scale_btns.items():
                try:
                    btn.configure(style="Accent.TButton" if self.current_scale == v else "TButton")
                except Exception:
                    pass

        if hasattr(self, 'admin_lbl'):
            try:
                import ctypes
                is_adm = ctypes.windll.shell32.IsUserAnAdmin() != 0
            except Exception:
                is_adm = False
            try:
                self.admin_lbl.config(bg=t["bg_main"], fg=(t["admin_ok"] if is_adm else t["admin_bad"]), font=s["font_base_bold"])
            except Exception:
                pass

        if hasattr(self, 'header_status_lbl'):
            try:
                self.header_status_lbl.config(bg=t["bg_main"], fg=t["fg_main"], font=s["font_base"])
            except Exception:
                pass

        if hasattr(self, 'active_mode_lbl'):
            try:
                self.active_mode_lbl.config(font=s["font_mode"])
            except Exception:
                pass

        for lbl_name in ('cpu_pct_lbl', 'cpu_freq_lbl', 'cpu_temp_lbl', 'cpu_fan_lbl', 'gpu_pct_lbl', 'gpu_freq_lbl', 'gpu_temp_lbl', 'gpu_fan_lbl', 'ram_lbl', 'battery_lbl', 'fan_lbl'):
            lbl = getattr(self, lbl_name, None)
            if lbl:
                try:
                    lbl.config(font=s["font_telemetry_val"])
                except Exception:
                    pass

        try:
            self._update_toggles_ui()
        except Exception:
            pass

    def _build_ui(self):
        s = SCALES[self.current_scale]
        t = THEMES[self.current_theme]

        main_frame = ttk.Frame(self.root, padding=12)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Footer Actions (Packed FIRST to guarantee permanent visibility at bottom across all DPI scales) ---
        footer_frame = ttk.Frame(main_frame)
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(8, 0))

        btn_settings = ttk.Button(footer_frame, text="⚙️ Настройки...", command=self._open_settings)
        btn_settings.pack(side=tk.LEFT)

        self.btn_resume_auto = ttk.Button(footer_frame, text="🔄 Возобновить авто-режим", command=self._resume_auto)
        self.btn_resume_auto.pack(side=tk.LEFT, padx=10)

        close_btn_text = "Закрыть" if self.is_standalone else "Свернуть в трей"
        btn_hide = ttk.Button(footer_frame, text=close_btn_text, command=self._on_window_delete)
        btn_hide.pack(side=tk.RIGHT)

        # --- Header ---
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))

        title_lbl = ttk.Label(header_frame, text=f"{APP_TITLE} v{APP_VERSION}", style="Header.TLabel")
        title_lbl.pack(side=tk.LEFT)

        try:
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            is_admin = False

        admin_text = "[Admin]" if is_admin else "[User]"
        admin_color = t["admin_ok"] if is_admin else t["admin_bad"]
        self.admin_lbl = tk.Label(header_frame, text=admin_text, bg=t["bg_main"], fg=admin_color, font=s["font_base_bold"])
        self.admin_lbl.pack(side=tk.LEFT, padx=10)

        self.header_status_lbl = tk.Label(header_frame, text="", bg=t["bg_main"], fg=t["fg_main"], font=s["font_base"])
        self.header_status_lbl.pack(side=tk.LEFT, padx=5)

        # --- Accessibility & Visual Customization Toolbar ---
        toolbar = ttk.Frame(main_frame, style="Card.TFrame", padding=6)
        toolbar.pack(fill=tk.X, pady=(0, 10))

        # Row 1: Themes
        theme_frame = ttk.Frame(toolbar, style="Card.TFrame")
        theme_frame.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(theme_frame, text="🎨 Тема: ", style="Card.TLabel").pack(side=tk.LEFT, padx=(2, 4))
        self.theme_btns = {}
        for t_key, t_name in [("cyber_dark", "TUF Cyber"), ("clean_minimalist", "Minimalist"), ("oled_contrast", "OLED Contrast")]:
            btn = ttk.Button(
                theme_frame,
                text=t_name,
                style="Accent.TButton" if self.current_theme == t_key else "TButton",
                command=lambda k=t_key: self.set_theme(k),
            )
            btn.pack(side=tk.LEFT, padx=2)
            self.theme_btns[t_key] = btn

        # Row 2: Scales
        scale_frame = ttk.Frame(toolbar, style="Card.TFrame")
        scale_frame.pack(fill=tk.X, pady=(2, 0))
        ttk.Label(scale_frame, text="🔍 Масштаб: ", style="Card.TLabel").pack(side=tk.LEFT, padx=(2, 4))
        self.scale_btns = {}
        for s_val, s_name in [(1.0, "100%"), (1.25, "125%"), (1.5, "150%")]:
            btn = ttk.Button(
                scale_frame,
                text=s_name,
                style="Accent.TButton" if self.current_scale == s_val else "TButton",
                command=lambda v=s_val: self.set_scale(v),
            )
            btn.pack(side=tk.LEFT, padx=2)
            self.scale_btns[s_val] = btn

        # --- Active Power Mode Card ---
        mode_card = ttk.Frame(main_frame, style="Card.TFrame", padding=10)
        mode_card.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(mode_card, text="Текущий режим", style="CardHeader.TLabel").pack(anchor=tk.W, pady=(0, 4))

        mode_content = ttk.Frame(mode_card, style="Card.TFrame")
        mode_content.pack(fill=tk.X)

        # Left column: Mode Label + Status Row (with inline resume button)
        mode_left = ttk.Frame(mode_content, style="Card.TFrame")
        mode_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.active_mode_lbl = ttk.Label(mode_left, text="Загрузка...", style="Card.TLabel", font=s["font_mode"])
        self.active_mode_lbl.pack(anchor=tk.W, pady=(0, 4))

        status_row = ttk.Frame(mode_left, style="Card.TFrame")
        status_row.pack(anchor=tk.W, fill=tk.X)

        self.auto_status_lbl = ttk.Label(status_row, text="Управляется автоматически (FSM)", style="Card.TLabel", foreground=t["eco_fg"])
        self.auto_status_lbl.pack(side=tk.LEFT)

        self.btn_resume_auto_inline = ttk.Button(
            status_row,
            text="⚡ Возобновить авторежим",
            style="Accent.TButton",
            command=self._resume_auto,
        )

        # Right column: Vertical toggle badges stack
        self.toggles_frame = ttk.Frame(mode_content, style="Card.TFrame")
        self.toggles_frame.pack(side=tk.RIGHT, anchor=tk.E, padx=(10, 0))

        # Windows Energy Saver Toggle
        self.btn_energy_saver_toggle = tk.Button(
            self.toggles_frame,
            text="🍃 Энергосбережение [ВЫКЛ]",
            command=self._on_windows_energy_saver_toggled,
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=10,
            pady=5,
        )
        self.btn_energy_saver_toggle.pack(side=tk.TOP, anchor=tk.E)

        # --- Quick Mode Switcher ---
        switcher_frame = ttk.Frame(main_frame)
        switcher_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(switcher_frame, text="Быстрое переключение:", style="TLabel").pack(anchor=tk.W, pady=(0, 4))

        btn_frame = ttk.Frame(switcher_frame)
        btn_frame.pack(fill=tk.X)

        self.btn_turbo = tk.Button(
            btn_frame,
            text="⚡ Turbo / Высокая",
            command=lambda: self._set_plan(GUID_HIGH_PERFORMANCE),
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=8,
            pady=5,
        )
        self.btn_turbo.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))

        self.btn_balance = tk.Button(
            btn_frame,
            text="⚖️ Баланс",
            command=lambda: self._set_plan(GUID_BALANCED),
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=8,
            pady=5,
        )
        self.btn_balance.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 5))

        self.btn_eco = tk.Button(
            btn_frame,
            text="🍃 Эко / Тихий",
            command=lambda: self._set_plan(GUID_POWER_SAVER),
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=8,
            pady=5,
        )
        self.btn_eco.pack(side=tk.LEFT, expand=True, fill=tk.X)

        # --- Live Telemetry Card ---
        telemetry_card = ttk.Frame(main_frame, style="Card.TFrame")
        telemetry_card.pack(fill=tk.X, anchor=tk.N, pady=(0, 10))

        ttk.Label(telemetry_card, text="Телеметрия системы", style="CardHeader.TLabel").pack(anchor=tk.W, padx=10, pady=(8, 4))

        tel_inner = ttk.Frame(telemetry_card, style="Card.TFrame")
        tel_inner.pack(fill=tk.X, padx=10, pady=(0, 8))
        tel_inner.columnconfigure(0, weight=1, uniform="subcards")
        tel_inner.columnconfigure(1, weight=1, uniform="subcards")

        # 2-column grid layout for Telemetry (Symmetric Hardware Sub-Cards)
        col_left = ttk.Frame(tel_inner, style="SubCard.TFrame", padding=8)
        col_left.grid(row=0, column=0, sticky="nsew", padx=(0, 5), pady=(0, 6))
        col_left.columnconfigure(0, weight=1)
        col_left.columnconfigure(1, weight=0)

        col_right = ttk.Frame(tel_inner, style="SubCard.TFrame", padding=8)
        col_right.grid(row=0, column=1, sticky="nsew", padx=(5, 0), pady=(0, 6))
        col_right.columnconfigure(0, weight=1)
        col_right.columnconfigure(1, weight=0)

        # Left Column: CPU
        ttk.Label(col_left, text="🔹 Процессор (ЦП)", style="SubCardHeader.TLabel").grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 4))

        ttk.Label(col_left, text="Утилизация:", style="CardStatic.TLabel").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.cpu_pct_lbl = ttk.Label(col_left, text="-- %", style="CardVal.TLabel")
        self.cpu_pct_lbl.grid(row=1, column=1, sticky=tk.E, pady=3, padx=4)

        ttk.Label(col_left, text="Частота:", style="CardStatic.TLabel").grid(row=2, column=0, sticky=tk.W, pady=3)
        self.cpu_freq_lbl = ttk.Label(col_left, text="-- GHz", style="CardVal.TLabel")
        self.cpu_freq_lbl.grid(row=2, column=1, sticky=tk.E, pady=3, padx=4)

        ttk.Label(col_left, text="Температура:", style="CardStatic.TLabel").grid(row=3, column=0, sticky=tk.W, pady=3)
        self.cpu_temp_lbl = ttk.Label(col_left, text="-- °C", style="CardVal.TLabel")
        self.cpu_temp_lbl.grid(row=3, column=1, sticky=tk.E, pady=3, padx=4)

        # Right Column: GPU
        ttk.Label(col_right, text="🔸 Видеокарта (ГП)", style="SubCardHeader.TLabel").grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 4))

        ttk.Label(col_right, text="Утилизация:", style="CardStatic.TLabel").grid(row=1, column=0, sticky=tk.W, pady=3)
        self.gpu_pct_lbl = ttk.Label(col_right, text="-- %", style="CardVal.TLabel")
        self.gpu_pct_lbl.grid(row=1, column=1, sticky=tk.E, pady=3, padx=4)

        ttk.Label(col_right, text="Частота:", style="CardStatic.TLabel").grid(row=2, column=0, sticky=tk.W, pady=3)
        self.gpu_freq_lbl = ttk.Label(col_right, text="-- MHz", style="CardVal.TLabel")
        self.gpu_freq_lbl.grid(row=2, column=1, sticky=tk.E, pady=3, padx=4)

        ttk.Label(col_right, text="Температура:", style="CardStatic.TLabel").grid(row=3, column=0, sticky=tk.W, pady=3)
        self.gpu_temp_lbl = ttk.Label(col_right, text="-- °C", style="CardVal.TLabel")
        self.gpu_temp_lbl.grid(row=3, column=1, sticky=tk.E, pady=3, padx=4)

        # Bottom Resource Row (RAM & Battery / Power status)
        bottom_row = ttk.Frame(tel_inner, style="SubCard.TFrame", padding=6)
        bottom_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        bottom_row.columnconfigure(0, weight=1)
        bottom_row.columnconfigure(1, weight=1)

        self.ram_lbl = ttk.Label(bottom_row, text="📊 ОЗУ: -- / -- GB (--%)", style="CardVal.TLabel")
        self.ram_lbl.grid(row=0, column=0, sticky=tk.W, padx=6, pady=2)

        self.battery_lbl = ttk.Label(bottom_row, text="🔋 Батарея: -- % (Лимит: --)", style="CardVal.TLabel", cursor="hand2")
        self.battery_lbl.grid(row=0, column=1, sticky=tk.E, padx=6, pady=2)
        if hasattr(self.battery_lbl, "bind"):
            try:
                self.battery_lbl.bind("<Button-1>", self._on_battery_lbl_click)
            except Exception:
                pass

        self.fan_lbl = ttk.Label(bottom_row, text="Профиль: --", style="CardStatic.TLabel")

    def _on_battery_lbl_click(self, event):
        prev_menu = getattr(self, "_battery_popup_menu", None)
        if prev_menu is not None:
            try:
                prev_menu.destroy()
            except Exception:
                pass
        t = THEMES.get(self.current_theme, THEMES["cyber_dark"])
        s = SCALES.get(self.current_scale, SCALES[1.0])
        menu = tk.Menu(
            self.root,
            tearoff=0,
            font=s.get("font_btn_bold", ("Segoe UI", 10, "bold")),
            bg=t.get("bg_card", "#1e1e2e"),
            fg=t.get("fg_main", "#ffffff"),
            disabledforeground=t.get("fg_muted", "#888888"),
            activebackground=t.get("btn_accent_bg", "#00BFA5"),
            activeforeground=t.get("btn_accent_fg", "#000000"),
            relief="flat",
            bd=1,
        )
        self._battery_popup_menu = menu
        curr_limit = getattr(self.config, 'battery_charge_limit', 60)
        for limit, desc in [
            (60, "60% (Максимальная защита от износа)"),
            (80, "80% (Рекомендуемый: баланс долговечности)"),
            (100, "100% (Полная емкость)")
        ]:
            prefix = "✓ " if curr_limit == limit else "   "
            menu.add_command(
                label=f"{prefix}{desc}",
                command=lambda l=limit: self._set_battery_limit(l)
            )
        menu.add_separator()
        menu.add_command(
            label="ℹ️ От сети заряд не снижается. Отключите ЗУ для разряда до лимита",
            state=tk.DISABLED,
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass

    def _set_battery_limit(self, limit: int):
        try:
            from asus_battery import AsusBatteryController, is_admin
            if is_admin():
                ok, msg = AsusBatteryController.set_charge_limit_direct(limit)
            else:
                ok, msg = AsusBatteryController.set_charge_limit_direct(limit)
                if not ok:
                    ok, msg = AsusBatteryController.set_charge_limit_elevated(limit)

            self.config.battery_charge_limit = limit
            self.config.save()
            if self.tray_app and hasattr(self.tray_app, 'update_icon'):
                try:
                    self.tray_app.update_icon()
                except Exception:
                    pass
            self._update_battery_label()
        except Exception as e:
            logger.error(f"Error setting battery charge limit: {e}")

    def _update_battery_label(self):
        try:
            import psutil
            battery = psutil.sensors_battery()
            limit = self.config.battery_charge_limit if hasattr(self.config, 'battery_charge_limit') and self.config.battery_charge_limit is not None else 60
            if battery:
                plugged = "🔌" if battery.power_plugged else "🔋"
                status = "Сеть (AC)" if battery.power_plugged else "Батарея"
                if battery.power_plugged and battery.percent >= limit:
                    self.battery_lbl.config(text=f"{plugged} {battery.percent}% (Лимит: {limit}% • не заряжается)")
                    if hasattr(self, 'header_status_lbl'):
                        self.header_status_lbl.config(text=f"|  {status}, {battery.percent}% (не заряжается)")
                else:
                    self.battery_lbl.config(text=f"{plugged} {battery.percent}% (Лимит: {limit}%)")
                    if hasattr(self, 'header_status_lbl'):
                        self.header_status_lbl.config(text=f"|  {status}, {battery.percent}%")
            else:
                self.battery_lbl.config(text=f"🔋 Батарея (Лимит: {limit}%)")
        except Exception as e:
            logger.debug(f"Error updating battery label: {e}")

    def _set_plan(self, guid: str):
        try:
            self.config.manual_override_guid = guid
            from power_plan import PowerPlanManager
            manager = PowerPlanManager()
            manager.set_active_plan(guid)
            watcher = self.watcher or (getattr(self.tray_app, '_watcher', None) if self.tray_app else None)
            if watcher:
                if hasattr(watcher, 'set_manual_override'):
                    try:
                        watcher.set_manual_override(guid)
                    except Exception:
                        pass
                try:
                    watcher.has_manual_override = True
                except Exception:
                    pass
            if self.tray_app and hasattr(self.tray_app, 'update_icon'):
                self.tray_app.update_icon()
        except Exception as e:
            logger.error(f"Error setting power plan: {e}")
        self._update_ui_state()

    def _open_settings(self):
        try:
            from settings_dialog import open_settings_window
            def _on_save(data):
                if self.tray_app and hasattr(self.tray_app, '_on_settings_saved'):
                    try:
                        self.tray_app._on_settings_saved(data)
                    except Exception:
                        pass
                if "ui_theme" in data:
                    self.set_theme(data["ui_theme"])
                if "ui_scale" in data:
                    self.set_scale(float(data["ui_scale"]))
                self._update_ui_state()
            open_settings_window(self.config, on_save_callback=_on_save)
        except Exception as e:
            logger.error(f"Error opening settings: {e}")

    def _resume_auto(self):
        watcher = self.watcher or (getattr(self.tray_app, '_watcher', None) if self.tray_app else None)
        if watcher:
            if hasattr(watcher, 'clear_manual_override'):
                try:
                    watcher.clear_manual_override()
                except Exception:
                    pass
            try:
                watcher.has_manual_override = False
            except Exception:
                pass
        self.config.manual_override_guid = None
        self.config.auto_switching_enabled = True

        # When running in standalone mode without an in-process watcher, immediately
        # determine and apply the desired automatic plan so OS switches right away.
        if not watcher:
            try:
                from power_watcher import PowerWatcher
                temp_watcher = PowerWatcher()
                snapshot = temp_watcher.take_snapshot()
                desired_plan, _ = temp_watcher.evaluate_desired_plan(snapshot)
                from power_plan import PowerPlanManager
                PowerPlanManager.set_active_plan(desired_plan)
            except Exception as e:
                logger.debug(f"Error setting automatic plan on resume: {e}")

        if self.tray_app and hasattr(self.tray_app, 'update_icon'):
            self.tray_app.update_icon()
        self._update_ui_state()

    def _update_ui_state(self):
        # Determine current active plan
        try:
            from power_plan import PowerPlanManager
            manager = PowerPlanManager()
            plan_res = manager.get_active_plan()
            if isinstance(plan_res, (tuple, list)) and len(plan_res) >= 2:
                active_guid, _ = plan_res[0], plan_res[1]
            elif isinstance(plan_res, (tuple, list)) and len(plan_res) == 1:
                active_guid, _ = plan_res[0], ""
            else:
                active_guid, _ = None, ""

            t = THEMES.get(self.current_theme, THEMES["cyber_dark"])
            s = SCALES.get(self.current_scale, SCALES[1.0])
            if active_guid == GUID_HIGH_PERFORMANCE:
                self.active_mode_lbl.config(text="⚡ Высокая производительность", foreground=t["turbo_fg"])
                self.fan_lbl.config(text="Турбо / Максимум")
            elif active_guid == GUID_BALANCED:
                self.active_mode_lbl.config(text="⚖️ Сбалансированная", foreground=t["balance_fg"])
                self.fan_lbl.config(text="Сбалансированный")
            elif active_guid == GUID_POWER_SAVER:
                self.active_mode_lbl.config(text="🍃 Экономия энергии", foreground=t["eco_fg"])
                self.fan_lbl.config(text="Тихий / Эко")
            else:
                self.active_mode_lbl.config(text="Неизвестный режим", foreground=t["fg_main"])
                self.fan_lbl.config(text="--")

            watcher = self.watcher or (getattr(self.tray_app, '_watcher', None) if self.tray_app else None)
            if watcher is not None:
                is_manual = bool(getattr(watcher, 'has_manual_override', False)) or bool(self.config.manual_override_guid) or (not self.config.auto_switching_enabled)
            else:
                is_manual = bool(self.config.manual_override_guid) or (not self.config.auto_switching_enabled)

            if not self.config.auto_switching_enabled:
                self.auto_status_lbl.config(text="Ручной выбор (авто-режим выключен)", foreground=t["warn_fg"])
                self.btn_resume_auto.pack(side=tk.LEFT, padx=10)
                if hasattr(self, 'btn_resume_auto_inline'):
                    self.btn_resume_auto_inline.pack(side=tk.LEFT, padx=(10, 0))
            elif is_manual:
                self.auto_status_lbl.config(text="Ручной выбор (переопределено)", foreground=t["warn_fg"])
                self.btn_resume_auto.pack(side=tk.LEFT, padx=10)
                if hasattr(self, 'btn_resume_auto_inline'):
                    self.btn_resume_auto_inline.pack(side=tk.LEFT, padx=(10, 0))
            else:
                self.auto_status_lbl.config(text="Управляется автоматически (FSM)", foreground=t["eco_fg"])
                self.btn_resume_auto.pack_forget()
                if hasattr(self, 'btn_resume_auto_inline'):
                    self.btn_resume_auto_inline.pack_forget()

            # --- Reactive Quick-Switch Highlighting ---
            if hasattr(self, 'btn_turbo') and hasattr(self, 'btn_balance') and hasattr(self, 'btn_eco'):
                neutral_bg = t.get("btn_bg", "#313244")
                neutral_fg = t.get("btn_fg", "#cdd6f4")
                neutral_font = s.get("font_btn", ("Segoe UI", 10))
                bold_font = s.get("font_btn_bold", ("Segoe UI", 10, "bold"))

                # Reset all to neutral dark
                for btn in (self.btn_turbo, self.btn_balance, self.btn_eco):
                    try:
                        btn.configure(
                            bg=neutral_bg,
                            fg=neutral_fg,
                            font=neutral_font,
                            activebackground=t.get("btn_active", "#45475a"),
                            activeforeground=t.get("fg_main", "#ffffff"),
                        )
                    except Exception:
                        pass

                # If manual override is active, highlight the selected plan
                if is_manual:
                    if active_guid == GUID_HIGH_PERFORMANCE:
                        self.btn_turbo.configure(
                            bg=t["turbo_fg"],
                            fg="#1e1e2e",
                            font=bold_font,
                            activebackground=t["turbo_fg"],
                            activeforeground="#1e1e2e",
                        )
                    elif active_guid == GUID_BALANCED:
                        self.btn_balance.configure(
                            bg=t.get("bal_fg", t.get("balance_fg", "#89b4fa")),
                            fg="#1e1e2e",
                            font=bold_font,
                            activebackground=t.get("bal_fg", t.get("balance_fg", "#89b4fa")),
                            activeforeground="#1e1e2e",
                        )
                    elif active_guid == GUID_POWER_SAVER:
                        self.btn_eco.configure(
                            bg=t.get("eco_fg", "#a6e3a1"),
                            fg="#1e1e2e",
                            font=bold_font,
                            activebackground=t.get("eco_fg", "#a6e3a1"),
                            activeforeground="#1e1e2e",
                        )

            self._update_toggles_ui()

        except Exception as e:
            logger.error(f"Error updating UI state: {e}")

    def _update_toggles_ui(self):
        try:
            t = THEMES[self.current_theme]
            s = SCALES[self.current_scale]

            # Update Windows Energy Saver button badge (strictly matches live Windows state)
            es_val = WindowsEnergySaver.get_state()
            es_is_on = (es_val == 1)
            if hasattr(self, 'btn_energy_saver_toggle'):
                self.btn_energy_saver_toggle.configure(
                    font=s.get("font_btn", ("Segoe UI", 10)),
                    text="🍃 Энергосбережение [ВКЛ]" if es_is_on else "🍃 Энергосбережение [ВЫКЛ]",
                    bg=t.get("bal_fg", "#00d2d3") if es_is_on else t.get("btn_bg", "#333333"),
                    fg="#000000" if es_is_on else t.get("fg_muted", "#aaaaaa"),
                    activebackground=t.get("btn_active", "#444444"),
                    activeforeground=t.get("fg_main", "#ffffff"),
                )
        except Exception as e:
            logger.debug(f"Error updating toggles UI: {e}")

    def _on_windows_energy_saver_toggled(self):
        try:
            curr = WindowsEnergySaver.get_state()
            new_val = (curr != 1)
            ok, msg = WindowsEnergySaver.set_state(new_val)
            if ok:
                self.config.windows_energy_saver_manual = new_val
                logger.info(f"Windows Energy Saver toggled via dashboard to: {new_val}")
                self._update_toggles_ui()
            else:
                logger.warning(f"Could not toggle Windows Energy Saver ({msg}), opening settings...")
                try:
                    os.startfile("ms-settings:batterysaver")
                except Exception as se:
                    logger.debug(f"Could not open ms-settings:batterysaver: {se}")
                self._update_toggles_ui()
        except Exception as e:
            logger.error(f"Error toggling Windows energy saver in dashboard: {e}")

    def _start_telemetry_loop(self):
        self._update_ui_state()
        self._poll_telemetry()

    def _poll_telemetry(self):
        self._update_ui_state()
        try:
            import psutil
            cpu_pct = psutil.cpu_percent(interval=None)
            self.cpu_pct_lbl.config(text=f"{cpu_pct:.1f} %")

            try:
                freq_ghz = self.cpu_telemetry.get_frequency_ghz()
                if freq_ghz is not None:
                    self.cpu_freq_lbl.config(text=f"{freq_ghz:.2f} GHz")
            except Exception:
                pass

            try:
                temp_c = self.cpu_telemetry.get_temperature_c()
                if temp_c is not None:
                    self.cpu_temp_lbl.config(text=f"{temp_c:.0f} °C")
            except Exception:
                pass

            # GPU metrics
            if hasattr(self, 'gpu_telemetry') and self.gpu_telemetry:
                try:
                    gpu_pct = self.gpu_telemetry.get_utilization_pct()
                    if gpu_pct is not None:
                        self.gpu_pct_lbl.config(text=f"{gpu_pct} %")
                except Exception:
                    pass

                try:
                    gpu_mhz = self.gpu_telemetry.get_clock_mhz()
                    if gpu_mhz is not None:
                        self.gpu_freq_lbl.config(text=f"{gpu_mhz} MHz")
                except Exception:
                    pass

                try:
                    gpu_temp = self.gpu_telemetry.get_temperature_c()
                    if gpu_temp is not None:
                        self.gpu_temp_lbl.config(text=f"{gpu_temp} °C")
                except Exception:
                    pass

            # RAM metrics
            if hasattr(self, 'ram_lbl') and self.ram_lbl:
                try:
                    vm = psutil.virtual_memory()
                    used_gb = vm.used / (1024 ** 3)
                    total_gb = vm.total / (1024 ** 3)
                    self.ram_lbl.config(text=f"📊 ОЗУ: {used_gb:.1f} / {total_gb:.1f} GB ({vm.percent:.0f}%)")
                except Exception:
                    self.ram_lbl.config(text="📊 ОЗУ: -- / -- GB (--%)")

            try:
                battery = psutil.sensors_battery()
                if battery:
                    limit = None
                    if hasattr(self.config, 'battery_charge_limit') and self.config.battery_charge_limit is not None:
                        limit = self.config.battery_charge_limit
                    elif hasattr(self.config, 'charge_limit') and self.config.charge_limit is not None:
                        limit = self.config.charge_limit
                    else:
                        try:
                            from asus_battery import AsusBatteryController
                            hw_limit, _ = AsusBatteryController.get_current_limit()
                            if hw_limit is not None:
                                limit = hw_limit
                        except Exception:
                            pass
                    if limit is None:
                        limit = "--"
                    plugged = "🔌" if battery.power_plugged else "🔋"
                    status = "Сеть (AC)" if battery.power_plugged else "Батарея"
                    if battery.power_plugged and isinstance(limit, int) and battery.percent >= limit:
                        self.battery_lbl.config(text=f"{plugged} {battery.percent}% (Лимит: {limit}% • не заряжается)")
                        self.header_status_lbl.config(text=f"|  {status}, {battery.percent}% (не заряжается)")
                    else:
                        self.battery_lbl.config(text=f"{plugged} {battery.percent}% (Лимит: {limit}%)")
                        self.header_status_lbl.config(text=f"|  {status}, {battery.percent}%")
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Error polling telemetry: {e}")

        # Protect against duplicate/accumulating timers (Hermes recommendation)
        if getattr(self, "telemetry_timer", None):
            try:
                self.root.after_cancel(self.telemetry_timer)
            except Exception:
                pass
            self.telemetry_timer = None
        self.telemetry_timer = self.root.after(1500, self._poll_telemetry)


def prewarm_dashboard(tray_app=None, config_obj=None, watcher=None):
    """Pre-initializes the Dashboard window hidden in background for instant <0.1s tray open."""
    global _prewarm_thread
    if DashboardWindow._instance is not None and getattr(DashboardWindow._instance, "root", None) is not None:
        return DashboardWindow._instance

    _init_ready_event.clear()

    def _tk_thread():
        try:
            win = DashboardWindow(tray_app, config_obj, watcher, is_standalone=False, initially_hidden=True)
            win.root.mainloop()
        except Exception as e:
            logger.error(f"Error in prewarmed Dashboard mainloop: {e}")
        finally:
            DashboardWindow._instance = None
            _init_ready_event.clear()

    import threading
    t = threading.Thread(target=_tk_thread, daemon=True, name="PowerMasterDashboardGUI")
    _prewarm_thread = t
    t.start()
    return t


def show_dashboard_window(tray_app=None, config_obj=None, watcher=None, on_close=None):
    """Brings prewarmed or existing dashboard to front instantly, or creates if absent."""
    global _prewarm_thread
    # If prewarm is running, wait up to 2 seconds for it to finish initialization
    if DashboardWindow._instance is None and _prewarm_thread is not None and _prewarm_thread.is_alive():
        _init_ready_event.wait(timeout=2.0)

    if DashboardWindow._instance is not None and getattr(DashboardWindow._instance, "root", None) is not None:
        try:
            DashboardWindow._instance.root.after(0, DashboardWindow._instance.lift_to_front)
            return DashboardWindow._instance
        except Exception as e:
            logger.error(f"Failed to lift existing dashboard: {e}")
            DashboardWindow._instance = None

    _init_ready_event.clear()

    def _tk_thread():
        try:
            win = DashboardWindow(tray_app, config_obj, watcher, on_close, is_standalone=False, initially_hidden=False)
            win.root.mainloop()
        except Exception as e:
            logger.error(f"Error in Dashboard mainloop: {e}")
        finally:
            DashboardWindow._instance = None
            _init_ready_event.clear()

    import threading
    t = threading.Thread(target=_tk_thread, daemon=True, name="PowerMasterDashboardGUI")
    _prewarm_thread = t
    t.start()
    return t


def close_dashboard_permanently():
    """Forces complete shutdown and destruction of any running Dashboard instance."""
    inst = DashboardWindow._instance
    if inst is not None:
        try:
            inst.root.after(0, inst._on_close)
        except Exception:
            pass


def _bring_existing_dashboard_to_front() -> bool:
    """Finds existing Dashboard window and brings it to the foreground."""
    try:
        user32 = ctypes.windll.user32
        target_title = f"{APP_TITLE} v{APP_VERSION} - Панель управления"
        hwnd = user32.FindWindowW(None, target_title)
        if not hwnd:
            found_hwnd = None

            def _enum_cb(hwnd_item, lparam):
                nonlocal found_hwnd
                length = user32.GetWindowTextLengthW(hwnd_item)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd_item, buff, length + 1)
                    if APP_TITLE in buff.value and "Панель управления" in buff.value:
                        found_hwnd = hwnd_item
                        return False
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)
            hwnd = found_hwnd

        if hwnd:
            user32.ShowWindow(hwnd, 9)  # 9 = SW_RESTORE
            try:
                user32.BringWindowToTop(hwnd)
            except Exception:
                pass
            user32.SetForegroundWindow(hwnd)
            return True
    except Exception as e:
        logger.debug(f"Error bringing existing dashboard to front: {e}")
    return False


def run_standalone_dashboard() -> None:
    """
    Runs the Dashboard GUI as an isolated standalone subprocess.
    Includes single-instance protection via Win32 mutex.
    If already open, brings existing window to front and exits.
    Exits cleanly with sys.exit(0) when closed.
    """
    kernel32 = ctypes.windll.kernel32
    try:
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
    except Exception:
        pass
    handle = kernel32.CreateMutexW(None, wintypes.BOOL(True), DASHBOARD_MUTEX_NAME)
    last_error = kernel32.GetLastError()

    if not handle or last_error == ERROR_ALREADY_EXISTS:
        if handle:
            kernel32.CloseHandle(handle)
        _bring_existing_dashboard_to_front()
        sys.exit(0)

    try:
        from config import config as app_config
        win = DashboardWindow(
            tray_app=None,
            config_obj=app_config,
            watcher=None,
            is_standalone=True,
        )
        win.root.mainloop()
    except Exception as e:
        logger.critical(f"Fatal error in standalone dashboard: {e}", exc_info=True)
    finally:
        _cleanup_winio()
        if handle:
            try:
                kernel32.CloseHandle(handle)
            except Exception:
                pass
    sys.exit(0)

