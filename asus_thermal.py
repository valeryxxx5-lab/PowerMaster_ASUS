r"""
PowerMaster_ASUS - ASUS Thermal Policy Controller
Controls Embedded Controller Thermal Profile via ACPI WMI:
  Namespace : root\wmi
  Class     : AsusAtkWmi_WMNB
  DeviceID  : 0x00120075
  Mode 0    : Balanced
  Mode 1    : Turbo (High Performance)
  Mode 2    : Silent (Fan Stop below ~55°C + reduced SPL/sPPT)
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import subprocess
import threading
from typing import Optional, Tuple

try:
    import pythoncom
    import win32com.client
    HAS_WIN32COM = True
except ImportError:
    HAS_WIN32COM = False

from config import (
    ASUS_WMI_NAMESPACE,
    ASUS_WMI_CLASS,
    ASUS_WMI_METHOD_SET,
    ASUS_WMI_METHOD_GET,
    ASUS_DEVICE_ID_THERMAL_POLICY,
)

logger = logging.getLogger("PowerMaster.Thermal")


def is_admin() -> bool:
    """Returns True if the current process has Administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


class AsusThermalController:
    """
    Thread-safe controller for ASUS EC Thermal Policy via WMI.
    All public methods are serialized with a class-level RLock.
    Each WMI call is wrapped with CoInitialize/CoUninitialize (COM STA lifecycle).
    Falls back to PowerShell Invoke-CimMethod if direct WMI fails or no admin rights.
    """

    _lock = threading.RLock()
    _breaker_until: float = 0.0

    # ------------------------------------------------------------------
    # get_thermal_policy
    # ------------------------------------------------------------------
    @classmethod
    def get_thermal_policy(cls) -> Tuple[Optional[int], str]:
        """
        Reads the current ASUS Thermal Policy from EC.
        Returns: (mode, message) where mode is 0/1/2 or None on failure.
        """
        import time
        with cls._lock:
            if time.monotonic() < cls._breaker_until:
                return None, "Circuit breaker active (skipping heavy WMI/CIM calls)"
            
            if not is_admin():
                from config import config
                saved = int(getattr(config, "asus_thermal_policy", 0))
                return saved, f"Configured policy: {saved} (Read-only status: Non-Admin)"
            if not HAS_WIN32COM:
                logger.warning("pywin32 not installed — WMI get skipped.")
                return None, "pywin32 not installed"
            try:
                pythoncom.CoInitialize()
                try:
                    wmi_svc = win32com.client.GetObject(f"winmgmts:{ASUS_WMI_NAMESPACE}")
                    instances = wmi_svc.ExecQuery(f"SELECT * FROM {ASUS_WMI_CLASS}")
                    if instances.Count == 0:
                        logger.warning(f"WMI class {ASUS_WMI_CLASS} not found in {ASUS_WMI_NAMESPACE}")
                        return None, "WMI class not found"
                    for inst in instances:
                        in_p = inst.Methods_(ASUS_WMI_METHOD_GET).InParameters.SpawnInstance_()
                        in_p.Properties_.Item("Device_ID").Value = ASUS_DEVICE_ID_THERMAL_POLICY
                        result = inst.ExecMethod_(ASUS_WMI_METHOD_GET, in_p)
                        try:
                            val = result.Properties_.Item("status").Value
                        except Exception:
                            val = result.Properties_.Item("ReturnValue").Value
                        cls._breaker_until = 0.0
                        return int(val), "Success"
                    return None, "No instance found"
                except Exception as e:
                    logger.warning(f"WMI get_thermal_policy error: {e} — falling back to CIM")
                    return cls._cim_get()
            finally:
                pythoncom.CoUninitialize()

    @classmethod
    def _cim_get(cls) -> Tuple[Optional[int], str]:
        """PowerShell CIM fallback for get_thermal_policy."""
        import time
        try:
            cmd = [
                "powershell", "-NoProfile", "-NonInteractive", "-Command",
                (
                    f"$obj = Get-CimInstance -Namespace '{ASUS_WMI_NAMESPACE}' -ClassName '{ASUS_WMI_CLASS}'; "
                    f"$r = Invoke-CimMethod -InputObject $obj -MethodName '{ASUS_WMI_METHOD_GET}' "
                    f"-Arguments @{{Device_ID=[uint32]{ASUS_DEVICE_ID_THERMAL_POLICY}}}; "
                    f"$r.status"
                ),
            ]
            flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=flags,
                encoding="utf-8",
                errors="replace",
            )
            if proc.returncode == 0 and proc.stdout.strip():
                cls._breaker_until = 0.0
                return int(proc.stdout.strip()), "Success (CIM)"
            logger.warning(f"CIM get failed (rc={proc.returncode}): {proc.stderr.strip()}")
            cls._breaker_until = time.monotonic() + 60.0
            return None, f"CIM get failed: {proc.stderr.strip()}"
        except Exception as pe:
            logger.warning(f"CIM get exception: {pe}")
            cls._breaker_until = time.monotonic() + 60.0
            return None, f"CIM get exception: {pe}"

    # ------------------------------------------------------------------
    # set_thermal_policy
    # ------------------------------------------------------------------
    @classmethod
    def _ioctl_set(cls, mode: int) -> Tuple[bool, str]:
        r"""Sets ASUS EC Thermal Policy via direct kernel IOCTL (\\.\ATKACPI\ASLDSRV)."""
        import struct
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p
        ]
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.DeviceIoControl.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p
        ]
        kernel32.DeviceIoControl.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        try:
            h_device = kernel32.CreateFileW(
                r"\\.\ATKACPI\ASLDSRV",
                0xC0000000,
                0x00000003,
                None,
                3,
                0,
                None,
            )
            invalid_h = wintypes.HANDLE(-1).value
            if h_device == invalid_h or h_device == 0 or h_device is None:
                return False, "ASUS ACPI device not found"
            try:
                in_buf = struct.pack("<IIII", 0x53564544, 8, ASUS_DEVICE_ID_THERMAL_POLICY, int(mode))
                out_buf = ctypes.create_string_buffer(1024)
                bytes_returned = ctypes.c_ulong(0)
                success = ctypes.windll.kernel32.DeviceIoControl(
                    h_device,
                    0x0022240C,
                    in_buf,
                    len(in_buf),
                    out_buf,
                    len(out_buf),
                    ctypes.byref(bytes_returned),
                    None,
                )
                if success:
                    res_val = struct.unpack("<I", out_buf.raw[:4])[0]
                    if res_val == 1:
                        cls._breaker_until = 0.0
                        return True, f"EC Thermal Policy -> {mode} (ACPI IOCTL)"
                    return False, f"IOCTL returned {res_val}"
                return False, f"DeviceIoControl failed (WinError {ctypes.GetLastError()})"
            finally:
                ctypes.windll.kernel32.CloseHandle(h_device)
        except Exception as e:
            return False, f"IOCTL exception: {e}"

    @classmethod
    def set_thermal_policy(cls, mode: int) -> Tuple[bool, str]:
        """
        Sets ASUS EC Thermal Policy.
        mode: 0=Balanced, 1=Turbo, 2=Silent (Fan Stop + reduced TDP)
        Returns: (success, message)
        """
        import time
        with cls._lock:
            if time.monotonic() < cls._breaker_until:
                return False, "Circuit breaker active"

            # 1. Primary path: Direct ASUS ACPI IOCTL (lightning fast, no COM/CIM timeouts)
            ok_ioctl, msg_ioctl = cls._ioctl_set(mode)
            if ok_ioctl:
                cls._breaker_until = 0.0
                logger.info(f"EC Thermal Policy set to {mode} via ACPI IOCTL")
                return True, msg_ioctl

            # 2. Secondary path: WMI DEVS
            if not HAS_WIN32COM:
                logger.warning("pywin32 not installed — WMI set skipped.")
                return False, "pywin32 not installed"
            try:
                pythoncom.CoInitialize()
                try:
                    wmi_svc = win32com.client.GetObject(f"winmgmts:{ASUS_WMI_NAMESPACE}")
                    instances = wmi_svc.ExecQuery(f"SELECT * FROM {ASUS_WMI_CLASS}")
                    if instances.Count == 0:
                        logger.warning(f"WMI class {ASUS_WMI_CLASS} not found")
                        return False, "WMI class not found"
                    for inst in instances:
                        in_p = inst.Methods_(ASUS_WMI_METHOD_SET).InParameters.SpawnInstance_()
                        in_p.Properties_.Item("Device_ID").Value = ASUS_DEVICE_ID_THERMAL_POLICY
                        in_p.Properties_.Item("Control_status").Value = mode
                        inst.ExecMethod_(ASUS_WMI_METHOD_SET, in_p)
                        cls._breaker_until = 0.0
                        logger.info(f"EC Thermal Policy set to {mode} via WMI DEVS")
                        return True, f"EC Thermal Policy -> {mode}"
                    return False, "No WMI instance found"
                except Exception as e:
                    logger.warning(f"WMI set_thermal_policy error: {e} — falling back to CIM")
                    return cls._cim_set(mode)
            finally:
                pythoncom.CoUninitialize()

    @classmethod
    def _cim_set(cls, mode: int) -> Tuple[bool, str]:
        """PowerShell CIM fallback for set_thermal_policy."""
        import time
        try:
            cmd = [
                "powershell", "-NoProfile", "-NonInteractive", "-Command",
                (
                    f"$obj = Get-CimInstance -Namespace '{ASUS_WMI_NAMESPACE}' -ClassName '{ASUS_WMI_CLASS}'; "
                    f"$r = Invoke-CimMethod -InputObject $obj -MethodName '{ASUS_WMI_METHOD_SET}' "
                    f"-Arguments @{{Device_ID=[uint32]{ASUS_DEVICE_ID_THERMAL_POLICY}; Control_status=[uint32]{mode}}}; "
                    f"$r.result"
                ),
            ]
            flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=flags,
                encoding="utf-8",
                errors="replace",
            )
            if proc.returncode == 0:
                cls._breaker_until = 0.0
                logger.info(f"EC Thermal Policy set to {mode} via CIM")
                try:
                    from config import config
                    config.asus_thermal_policy = mode
                except Exception:
                    pass
                return True, f"EC Thermal Policy -> {mode} (CIM)"
            logger.warning(f"CIM set failed (rc={proc.returncode}): {proc.stderr.strip()}")
            cls._breaker_until = time.monotonic() + 60.0
            return False, f"CIM set failed: {proc.stderr.strip()}"
        except Exception as pe:
            logger.warning(f"CIM set exception: {pe}")
            cls._breaker_until = time.monotonic() + 60.0
            return False, f"CIM set exception: {pe}"
