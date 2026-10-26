"""
PowerMaster_ASUS - Windows Power Plan Manager
Manages Windows power plans (High Performance, Balanced, Power Saver) via WinAPI powrprof.dll.
"""

from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes
import logging
import sys
import uuid
from typing import Optional, Tuple

from config import (
    GUID_HIGH_PERFORMANCE,
    GUID_BALANCED,
    GUID_POWER_SAVER,
    PLAN_NAMES,
)

logger = logging.getLogger("PowerMaster.PowerPlan")

# Load powrprof.dll
try:
    powrprof = ctypes.windll.powrprof
except AttributeError:
    powrprof = None


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]

    def to_uuid(self) -> uuid.UUID:
        return uuid.UUID(bytes_le=bytes(self))

    @classmethod
    def from_uuid(cls, u: uuid.UUID) -> "GUID":
        return cls.from_buffer_copy(u.bytes_le)

    @classmethod
    def from_string(cls, guid_str: str) -> "GUID":
        u = uuid.UUID(guid_str)
        return cls.from_uuid(u)


class PowerPlanManager:
    """Manages active Windows power scheme via powrprof.dll WinAPI."""

    GUID_HIGH = GUID_HIGH_PERFORMANCE
    GUID_BALANCED = GUID_BALANCED
    GUID_SAVER = GUID_POWER_SAVER

    GUID_PROCESSOR_SETTINGS_SUBGROUP = "54533251-82be-4824-96c1-47b60b740d00"
    GUID_PROCTHROTTLEMAX = "bc5038f7-23e0-4960-96da-33abaf5935ec"
    GUID_PROC_PERF_BOOST_MODE = "be337238-0d82-4146-a960-4f3749d470c7"

    BOOST_DISABLED = 0
    BOOST_ENABLED = 1
    BOOST_AGGRESSIVE = 2
    BOOST_EFFICIENT = 3
    BOOST_EFFICIENT_AGGRESSIVE = 4

    ALIASES = {
        "high": GUID_HIGH_PERFORMANCE,
        "perf": GUID_HIGH_PERFORMANCE,
        "performance": GUID_HIGH_PERFORMANCE,
        "balanced": GUID_BALANCED,
        "normal": GUID_BALANCED,
        "saver": GUID_POWER_SAVER,
        "eco": GUID_POWER_SAVER,
        "powersaver": GUID_POWER_SAVER,
    }

    @classmethod
    def resolve_guid(cls, key_or_guid: str) -> str:
        """Resolves an alias or GUID string to canonical lowercase GUID string."""
        clean = key_or_guid.strip().lower()
        if clean in cls.ALIASES:
            return cls.ALIASES[clean]
        try:
            return str(uuid.UUID(clean))
        except ValueError:
            return clean

    @classmethod
    def get_friendly_name(cls, guid_str: str) -> str:
        """Returns the friendly name of a power plan."""
        canonical = cls.resolve_guid(guid_str)
        if canonical in PLAN_NAMES:
            return PLAN_NAMES[canonical]

        # Try reading friendly name via WinAPI PowerReadFriendlyName
        try:
            g = GUID.from_string(canonical)
            buf = ctypes.create_unicode_buffer(512)
            buf_size = wintypes.DWORD(ctypes.sizeof(buf))
            ret = powrprof.PowerReadFriendlyName(
                None,
                ctypes.byref(g),
                None,
                None,
                buf,
                ctypes.byref(buf_size),
            )
            if ret == 0 and buf.value:
                return buf.value
        except Exception:
            pass

        return f"План ({canonical[:8]}...)"

    @classmethod
    def get_active_plan(cls) -> Tuple[Optional[str], str]:
        """
        Retrieves the currently active Windows power scheme.
        Returns: (guid_string, friendly_name)
        """
        pActiveGuid = ctypes.POINTER(GUID)()
        try:
            ret = powrprof.PowerGetActiveScheme(None, ctypes.byref(pActiveGuid))
            if ret == 0 and pActiveGuid:
                active_uuid = pActiveGuid.contents.to_uuid()
                active_str = str(active_uuid).lower()
                friendly = cls.get_friendly_name(active_str)
                return active_str, friendly
            else:
                return None, f"PowerGetActiveScheme failed with error code {ret}"
        except Exception as e:
            logger.error(f"Error querying active power plan: {e}")
            return None, f"Exception: {e}"
        finally:
            if pActiveGuid:
                ctypes.windll.kernel32.LocalFree(pActiveGuid)

    @classmethod
    def set_active_plan(cls, plan_key_or_guid: str, force: bool = False) -> Tuple[bool, str]:
        """
        Switches the active power scheme to the specified plan.
        Accepts: "high", "balanced", "saver", or GUID string.
        """
        canonical_guid = cls.resolve_guid(plan_key_or_guid)
        friendly_name = cls.get_friendly_name(canonical_guid)

        # Check if already active
        if not force:
            current_guid, _ = cls.get_active_plan()
            if current_guid and current_guid.lower() == canonical_guid.lower():
                logger.debug(f"Plan {friendly_name} ({canonical_guid}) is already active.")
                return True, f"План '{friendly_name}' уже активен."

        try:
            g = GUID.from_string(canonical_guid)
            ret = powrprof.PowerSetActiveScheme(None, ctypes.byref(g))
            if ret == 0:
                logger.info(f"Switched power plan to: {friendly_name} ({canonical_guid})")
                return True, f"План питания успешно переключен на: {friendly_name}"
            else:
                msg = f"PowerSetActiveScheme failed with Win32 code {ret}"
                logger.error(msg)
                return False, msg
        except Exception as e:
            msg = f"Exception setting power plan {canonical_guid}: {e}"
            logger.error(msg)
            return False, msg

    @classmethod
    def set_high_performance(cls, force: bool = False) -> Tuple[bool, str]:
        return cls.set_active_plan(cls.GUID_HIGH, force=force)

    @classmethod
    def set_balanced(cls, force: bool = False) -> Tuple[bool, str]:
        return cls.set_active_plan(cls.GUID_BALANCED, force=force)

    @classmethod
    def set_power_saver(cls, force: bool = False) -> Tuple[bool, str]:
        return cls.set_active_plan(cls.GUID_SAVER, force=force)

    @classmethod
    def set_processor_throttle_max(cls, percent: int, scheme_guid: Optional[str] = None, activate: bool = True) -> Tuple[bool, str]:
        """
        Sets the Maximum Processor State (0-100%) for AC and DC under the specified (or active) power scheme.
        """
        if powrprof is None:
            return False, "powrprof.dll is not available on this platform"

        clamped = max(0, min(100, int(percent)))

        if scheme_guid:
            canonical_guid = cls.resolve_guid(scheme_guid)
        else:
            canonical_guid, _ = cls.get_active_plan()
            if not canonical_guid:
                return False, "Could not determine active power scheme"

        try:
            scheme = GUID.from_string(canonical_guid)
            subgroup = GUID.from_string(cls.GUID_PROCESSOR_SETTINGS_SUBGROUP)
            throttle = GUID.from_string(cls.GUID_PROCTHROTTLEMAX)

            # Write AC value index
            ret_ac = powrprof.PowerWriteACValueIndex(
                None,
                ctypes.byref(scheme),
                ctypes.byref(subgroup),
                ctypes.byref(throttle),
                clamped,
            )

            # Write DC value index (battery)
            ret_dc = powrprof.PowerWriteDCValueIndex(
                None,
                ctypes.byref(scheme),
                ctypes.byref(subgroup),
                ctypes.byref(throttle),
                clamped,
            )

            if ret_ac != 0 or ret_dc != 0:
                msg = f"PowerWriteValueIndex failed (AC={ret_ac}, DC={ret_dc})"
                logger.error(msg)
                return False, msg

            # Apply changes by reactivating scheme
            if activate:
                ret_apply = powrprof.PowerSetActiveScheme(None, ctypes.byref(scheme))
                if ret_apply != 0:
                    msg = f"PowerSetActiveScheme failed to commit throttle with code {ret_apply}"
                    logger.warning(msg)
                    return False, msg

            logger.info(f"Set processor throttle max to {clamped}% for scheme {canonical_guid}")
            return True, f"Максимальное состояние процессора установлено в {clamped}%"

        except Exception as e:
            msg = f"Exception setting processor throttle max: {e}"
            logger.error(msg)
            return False, msg

    @classmethod
    def set_perf_boost_mode(cls, mode: Union[int, bool], scheme_guid: Optional[str] = None, activate: bool = True) -> Tuple[bool, str]:
        """
        Sets PERFBOOSTMODE (Processor Performance Boost Mode) for the given power scheme.
        Modes:
          0 - Disabled (Отключено: строго базовая частота ~2.9 ГГц, холодный и тихий)
          1 - Enabled (Включено)
          2 - Aggressive (Агрессивный буст для High Performance / Игр)
          3 - Efficient Enabled (Эффективный мягкий буст для Сбалансированного режима)
          4 - Efficient Aggressive
        If bool:
          False -> 0 (Disabled)
          True -> 2 if High Performance, 3 if Balanced, else 1
        Writes both AC and DC values, then conditionally reactivates the scheme.
        """
        if powrprof is None:
            return False, "powrprof.dll is not available"
        canonical_guid = cls.resolve_guid(scheme_guid) if scheme_guid else (cls.get_active_plan()[0] or cls.GUID_BALANCED)
        if isinstance(mode, bool):
            if not mode:
                value = cls.BOOST_DISABLED
            else:
                if canonical_guid.lower() == cls.GUID_HIGH.lower():
                    value = cls.BOOST_AGGRESSIVE
                elif canonical_guid.lower() == cls.GUID_BALANCED.lower():
                    value = cls.BOOST_EFFICIENT
                else:
                    value = cls.BOOST_ENABLED
        else:
            value = max(0, min(4, int(mode)))

        try:
            scheme = GUID.from_string(canonical_guid)
            subgroup = GUID.from_string(cls.GUID_PROCESSOR_SETTINGS_SUBGROUP)
            perf_boost = GUID.from_string(cls.GUID_PROC_PERF_BOOST_MODE)
            powrprof.PowerWriteACValueIndex(None, ctypes.byref(scheme), ctypes.byref(subgroup), ctypes.byref(perf_boost), value)
            powrprof.PowerWriteDCValueIndex(None, ctypes.byref(scheme), ctypes.byref(subgroup), ctypes.byref(perf_boost), value)
            if activate:
                powrprof.PowerSetActiveScheme(None, ctypes.byref(scheme))
            logger.info(f"PERFBOOSTMODE set to {value} for scheme {canonical_guid} (activate={activate})")
            return True, f"PERFBOOSTMODE установлен в {value}"
        except Exception as e:
            msg = f"Exception setting PERFBOOSTMODE: {e}"
            logger.error(msg)
            return False, msg

    @classmethod
    def get_perf_boost_mode(cls, scheme_guid: Optional[str] = None) -> Optional[int]:
        """
        Reads current PERFBOOSTMODE (AC) for specified or active power scheme.
        """
        if powrprof is None:
            return None

        if scheme_guid:
            canonical_guid = cls.resolve_guid(scheme_guid)
        else:
            canonical_guid, _ = cls.get_active_plan()
            if not canonical_guid:
                return None

        try:
            scheme = GUID.from_string(canonical_guid)
            subgroup = GUID.from_string(cls.GUID_PROCESSOR_SETTINGS_SUBGROUP)
            perf_boost = GUID.from_string(cls.GUID_PROC_PERF_BOOST_MODE)

            val_buf = wintypes.DWORD()
            ret = powrprof.PowerReadACValueIndex(
                None,
                ctypes.byref(scheme),
                ctypes.byref(subgroup),
                ctypes.byref(perf_boost),
                ctypes.byref(val_buf),
            )
            if ret == 0:
                return int(val_buf.value)
            return None
        except Exception as e:
            logger.debug(f"Exception reading PERFBOOSTMODE: {e}")
            return None

    @classmethod
    def get_processor_throttle_max(cls, scheme_guid: Optional[str] = None) -> Optional[int]:
        """
        Reads current Maximum Processor State (AC) for specified or active power scheme.
        """
        if powrprof is None:
            return None

        if scheme_guid:
            canonical_guid = cls.resolve_guid(scheme_guid)
        else:
            canonical_guid, _ = cls.get_active_plan()
            if not canonical_guid:
                return None

        try:
            scheme = GUID.from_string(canonical_guid)
            subgroup = GUID.from_string(cls.GUID_PROCESSOR_SETTINGS_SUBGROUP)
            throttle = GUID.from_string(cls.GUID_PROCTHROTTLEMAX)

            val_buf = wintypes.DWORD()
            ret = powrprof.PowerReadACValueIndex(
                None,
                ctypes.byref(scheme),
                ctypes.byref(subgroup),
                ctypes.byref(throttle),
                ctypes.byref(val_buf),
            )
            if ret == 0:
                return int(val_buf.value)
            return None
        except Exception as e:
            logger.debug(f"Error reading processor throttle max: {e}")
            return None


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Windows Power Plan Manager via WinAPI")
    parser.add_argument(
        "--set",
        choices=["high", "balanced", "saver", "perf", "eco"],
        help="Set power plan by alias",
    )
    parser.add_argument("--guid", help="Set power plan by explicit GUID")
    parser.add_argument("--status", action="store_true", help="Display current active power plan")

    args = parser.parse_args()

    if args.set:
        ok, msg = PowerPlanManager.set_active_plan(args.set)
        print(f"[{'OK' if ok else 'FAIL'}] {msg}")
        sys.exit(0 if ok else 1)

    if args.guid:
        ok, msg = PowerPlanManager.set_active_plan(args.guid)
        print(f"[{'OK' if ok else 'FAIL'}] {msg}")
        sys.exit(0 if ok else 1)

    # Default: status
    guid, name = PowerPlanManager.get_active_plan()
    print(f"Active Power Plan: {name}")
    print(f"GUID: {guid}")


if __name__ == "__main__":
    main()
