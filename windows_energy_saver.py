"""
PowerMaster_ASUS - Windows 11 Energy Saver Controller
Controls the native Windows 11 Energy Saver state.
"""
from __future__ import annotations
import logging
import threading
import subprocess
from typing import Optional, Tuple
import ctypes
from ctypes import wintypes, byref

try:
    import winreg
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False

logger = logging.getLogger("PowerMaster.EnergySaver")

REG_POWER_KEY = r"SYSTEM\CurrentControlSet\Control\Power"
REG_ENERGY_SAVER_STATE = "EnergySaverState"

GUID_SUB_ENERGYSAVER = "de830923-a562-41af-a086-e3a2c6bad2da"
GUID_ESBATTTHRESHOLD = "e69653ca-cf7f-4f05-aa73-cb833fa90ad4"
GUID_ESPOLICY = "5c5bb349-ad29-4ee2-9d0b-2b25270f7a81"


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", wintypes.BYTE),
        ("BatteryFlag", wintypes.BYTE),
        ("BatteryLifePercent", wintypes.BYTE),
        ("SystemStatusFlag", wintypes.BYTE),
        ("BatteryLifeTime", wintypes.DWORD),
        ("BatteryFullLifeTime", wintypes.DWORD),
    ]


try:
    powrprof = ctypes.windll.powrprof
    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32
    ntdll = ctypes.windll.ntdll
    if ntdll:
        try:
            ntdll.ZwQueryWnfStateData.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.POINTER(wintypes.ULONG),
                ctypes.c_void_p,
                ctypes.POINTER(wintypes.ULONG),
            ]
            ntdll.ZwQueryWnfStateData.restype = ctypes.c_long

            ntdll.ZwUpdateWnfStateData.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                wintypes.ULONG,
                ctypes.c_void_p,
                ctypes.c_void_p,
                wintypes.ULONG,
                wintypes.ULONG,
            ]
            ntdll.ZwUpdateWnfStateData.restype = ctypes.c_long
        except Exception:
            pass
except AttributeError:
    powrprof = None
    kernel32 = None
    user32 = None
    ntdll = None

WNF_PO_ENERGY_SAVER_OVERRIDE_V2 = 0x41C6013DA3BC3075
WNF_SEB_ENERGY_SAVER_STATE = 0x41840B3EA3BDF075


def _string_to_guid(guid_str: str) -> ctypes.Structure:
    import uuid
    b = uuid.UUID(guid_str).bytes_le
    
    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD),
                    ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD),
                    ("Data4", wintypes.BYTE * 8)]
    
    g = GUID()
    ctypes.memmove(ctypes.addressof(g), b, 16)
    return g


class WindowsEnergySaver:
    """Thread-safe controller for Windows 11 Energy Saver."""
    _lock = threading.RLock()

    @classmethod
    def get_state(cls) -> Optional[int]:
        """Returns 1 if Energy Saver is On, 2 if Off, or None if unavailable."""
        with cls._lock:
            # 1. Primary: Windows 11 24H2 live kernel WNF state (0x41C6013DA3BC3075)
            # Live kernel state: always accurate for both AC and Battery, does not require elevation
            if ntdll and kernel32:
                try:
                    sn = ctypes.c_uint64(WNF_PO_ENERGY_SAVER_OVERRIDE_V2)
                    cs = wintypes.ULONG(0)
                    buf = wintypes.DWORD(0)
                    sz = wintypes.ULONG(4)
                    res = ntdll.ZwQueryWnfStateData(
                        byref(sn), ctypes.c_void_p(0), ctypes.c_void_p(0),
                        byref(cs), byref(buf), byref(sz)
                    )
                    if res == 0 and sz.value == 4:
                        if buf.value == 1:
                            return 1
                        elif buf.value in (0, 2):
                            return 2
                except Exception as e:
                    logger.debug(f"WNF query error: {e}")

            # 2. Check live kernel SystemStatusFlag (1 when active on battery)
            if kernel32:
                try:
                    status = SYSTEM_POWER_STATUS()
                    if kernel32.GetSystemPowerStatus(byref(status)):
                        if status.SystemStatusFlag == 1:
                            return 1
                except Exception as e:
                    logger.debug(f"GetSystemPowerStatus error: {e}")

            # 3. Fallback: HKLM Registry (EnergySaverState)
            if HAS_WINREG:
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REG_POWER_KEY, 0, winreg.KEY_READ) as key:
                        val, _ = winreg.QueryValueEx(key, REG_ENERGY_SAVER_STATE)
                        val = int(val)
                        if val == 1:
                            return 1
                        elif val in (0, 2):
                            return 2
                except Exception as e:
                    logger.debug(f"Could not read {REG_ENERGY_SAVER_STATE}: {e}")

            # 4. Fallback: SystemPowerStatus flag 0 -> 2
            if kernel32:
                try:
                    status = SYSTEM_POWER_STATUS()
                    if kernel32.GetSystemPowerStatus(byref(status)):
                        if status.SystemStatusFlag == 1:
                            return 1
                        elif status.SystemStatusFlag == 0:
                            return 2
                except Exception as e:
                    logger.debug(f"GetSystemPowerStatus error: {e}")

            return None

    @classmethod
    def set_state(cls, enabled: bool) -> Tuple[bool, str]:
        """Sets Windows 11 Energy Saver state."""
        with cls._lock:
            val = 1 if enabled else 2
            policy_val = 1 if enabled else 0
            
            success = False
            msg = ""

            # 1. Publish to Windows 11 24H2 WNF state (0x41C6013DA3BC3075)
            # umpo.dll listens to this WNF state and immediately updates HKLM EnergySaverState and Quick Settings UI!
            if ntdll and powrprof:
                try:
                    sn = ctypes.c_uint64(WNF_PO_ENERGY_SAVER_OVERRIDE_V2)
                    wnf_val = wintypes.DWORD(val)
                    st = ntdll.ZwUpdateWnfStateData(
                        byref(sn), byref(wnf_val), 4, ctypes.c_void_p(0), ctypes.c_void_p(0), 0, 0
                    )
                    if st == 0:
                        success = True
                        msg = "Set via WNF"
                except Exception as e:
                    logger.debug(f"WNF update failed: {e}")
            
            if not success and powrprof:
                try:
                    active_policy_guid_ptr = ctypes.POINTER(ctypes.c_ubyte)()
                    if powrprof.PowerGetActiveScheme(None, byref(active_policy_guid_ptr)) == 0:
                        active_scheme = ctypes.cast(active_policy_guid_ptr, ctypes.POINTER(_string_to_guid(GUID_SUB_ENERGYSAVER).__class__))
                        
                        sub_guid = _string_to_guid(GUID_SUB_ENERGYSAVER)
                        es_policy_guid = _string_to_guid(GUID_ESPOLICY)
                        
                        r1 = powrprof.PowerWriteACValueIndex(None, active_scheme, byref(sub_guid), byref(es_policy_guid), policy_val)
                        r2 = powrprof.PowerWriteDCValueIndex(None, active_scheme, byref(sub_guid), byref(es_policy_guid), policy_val)
                        r3 = powrprof.PowerSetActiveScheme(None, active_scheme)
                        
                        kernel32.LocalFree(active_policy_guid_ptr)
                        
                        if r1 == 0 and r2 == 0 and r3 == 0:
                            success = True
                            if not msg:
                                msg = "Set via powrprof"
                except Exception as e:
                    logger.debug(f"powrprof fail: {e}")
            
            if not success:
                try:
                    cflags = 0
                    if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                        cflags = subprocess.CREATE_NO_WINDOW
                    
                    threshold_val = 100 if enabled else 0
                    cmds = [
                        ["powercfg", "/setdcvalueindex", "SCHEME_CURRENT", GUID_SUB_ENERGYSAVER, GUID_ESBATTTHRESHOLD, str(threshold_val)],
                        ["powercfg", "/setacvalueindex", "SCHEME_CURRENT", GUID_SUB_ENERGYSAVER, GUID_ESBATTTHRESHOLD, str(threshold_val)],
                        ["powercfg", "/setdcvalueindex", "SCHEME_CURRENT", GUID_SUB_ENERGYSAVER, GUID_ESPOLICY, str(policy_val)],
                        ["powercfg", "/setacvalueindex", "SCHEME_CURRENT", GUID_SUB_ENERGYSAVER, GUID_ESPOLICY, str(policy_val)],
                        ["powercfg", "/setactive", "SCHEME_CURRENT"]
                    ]
                    
                    for cmd in cmds:
                        subprocess.run(cmd, check=True, creationflags=cflags)
                    
                    success = True
                    msg = "Set via powercfg fallback"
                except Exception as e:
                    err_msg = f"Fallback powercfg failed: {e}"
                    logger.warning(err_msg)
                    return False, err_msg
            
            if HAS_WINREG:
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REG_POWER_KEY, 0, winreg.KEY_SET_VALUE) as key:
                        winreg.SetValueEx(key, REG_ENERGY_SAVER_STATE, 0, winreg.REG_DWORD, val)
                except PermissionError:
                    logger.warning("No admin rights to write EnergySaverState to HKLM registry.")
                except Exception as e:
                    logger.debug(f"Registry write failed (non-fatal): {e}")
            
            if user32:
                def _broadcast_async():
                    try:
                        res = wintypes.DWORD()
                        user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "Environment", 2, 100, byref(res))
                        user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "SystemPowerStatus", 2, 100, byref(res))
                    except Exception:
                        pass
                threading.Thread(target=_broadcast_async, daemon=True, name="EnergySaverBroadcast").start()
                
            return True, msg
