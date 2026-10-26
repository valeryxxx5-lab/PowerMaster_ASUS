"""
PowerMaster_ASUS - ASUS Conflicting Background Services Controller.
Controls background ASUS services (ASUSOptimization, AsusAppService, ASUSSoftwareManager, ASUSSystemAnalysis),
which may override the battery charge limit in the EC (0x00120057) to 100%.
Uses native Win32 SCM API (win32service) without invoking PowerShell or cmd (0% CPU, 0 Defender triggers).
"""

from __future__ import annotations
import ctypes
import logging
import os
import sys
import time
from typing import Dict, List, Tuple, Any

try:
    import win32service
    HAS_WIN32SERVICE = True
except ImportError:
    win32service = None
    HAS_WIN32SERVICE = False

logger = logging.getLogger("PowerMaster.AsusServices")

# Conflicting ASUS services (aligned with G-Helper standards):
# NOTE: Driver 'asussaio' is intentionally EXCLUDED to protect AsusWinIO64.dll fan RPM telemetry.
CONFLICTING_ASUS_SERVICES: Tuple[str, ...] = (
    "ASUSOptimization",
    "AsusAppService",
    "ASUSSoftwareManager",
    "ASUSSystemAnalysis",
    "ASUSLinkNear",
    "ASUSLinkRemote",
    "ASUSSwitch",
)


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


class AsusServiceManager:
    """Controls and safely disables conflicting ASUS background services via Win32 SCM."""

    @classmethod
    def get_asus_services_status(cls) -> Dict[str, str]:
        """
        Fast (< 0.5 ms) query of ASUS services status without admin rights.
        Returns dict: {service_name: 'running' | 'stopped' | 'disabled' | 'not_found'}.
        """
        result: Dict[str, str] = {}
        if not HAS_WIN32SERVICE:
            return {s: "not_found" for s in CONFLICTING_ASUS_SERVICES}

        scm = None
        try:
            scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ENUMERATE_SERVICE)
            for svc_name in CONFLICTING_ASUS_SERVICES:
                h_svc = None
                try:
                    h_svc = win32service.OpenService(
                        scm,
                        svc_name,
                        win32service.SERVICE_QUERY_STATUS | win32service.SERVICE_QUERY_CONFIG,
                    )
                    status = win32service.QueryServiceStatus(h_svc)
                    cfg = win32service.QueryServiceConfig(h_svc)
                    current_state = status[1]
                    start_type = cfg[1]
                    if current_state == win32service.SERVICE_RUNNING:
                        result[svc_name] = "running"
                    elif start_type == win32service.SERVICE_DISABLED:
                        result[svc_name] = "disabled"
                    else:
                        result[svc_name] = "stopped"
                except Exception:
                    result[svc_name] = "not_found"
                finally:
                    if h_svc is not None:
                        try:
                            win32service.CloseServiceHandle(h_svc)
                        except Exception:
                            pass
        except Exception as e:
            logger.debug(f"SCM query error: {e}")
            for svc_name in CONFLICTING_ASUS_SERVICES:
                result.setdefault(svc_name, "not_found")
        finally:
            if scm is not None:
                try:
                    win32service.CloseServiceHandle(scm)
                except Exception:
                    pass
        return result

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """Convenience method returning detailed dictionary of ASUS service states (single SCM scan)."""
        statuses = cls.get_asus_services_status()
        installed = sum(1 for st in statuses.values() if st != "not_found")
        running = sum(1 for st in statuses.values() if st == "running")
        return {
            "services": statuses,
            "running_count": running,
            "installed_count": installed,
        }

    @classmethod
    def disable_all(cls) -> Tuple[bool, str]:
        """Convenience alias for disable_conflicting_services."""
        return cls.disable_conflicting_services()

    @classmethod
    def enable_all(cls) -> Tuple[bool, str]:
        """Convenience alias for enable_conflicting_services."""
        return cls.enable_conflicting_services()

    @classmethod
    def get_running_count(cls) -> Tuple[int, int]:
        """Returns: (running_count, installed_count) of ASUS services."""
        statuses = cls.get_asus_services_status()
        installed = [s for s, st in statuses.items() if st != "not_found"]
        running = [s for s, st in statuses.items() if st == "running"]
        return len(running), len(installed)

    @classmethod
    def disable_conflicting_services(cls) -> Tuple[bool, str]:
        """
        Stops and sets to SERVICE_DISABLED all conflicting ASUS services.
        If non-elevated, prompts via UAC (--disable-asus-services).
        """
        if not is_admin():
            return cls._run_elevated_cli("--disable-asus-services")

        if not HAS_WIN32SERVICE:
            return False, "Модуль win32service недоступен"

        stopped_list: List[str] = []
        scm = None
        try:
            scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ALL_ACCESS)
            for svc_name in CONFLICTING_ASUS_SERVICES:
                h_svc = None
                try:
                    h_svc = win32service.OpenService(
                        scm,
                        svc_name,
                        win32service.SERVICE_STOP
                        | win32service.SERVICE_CHANGE_CONFIG
                        | win32service.SERVICE_QUERY_STATUS,
                    )
                    # 1. Change startup type to SERVICE_DISABLED
                    win32service.ChangeServiceConfig(
                        h_svc,
                        win32service.SERVICE_NO_CHANGE,
                        win32service.SERVICE_DISABLED,
                        win32service.SERVICE_NO_CHANGE,
                        None, None, 0, None, None, None, None,
                    )
                    # 2. If running, stop service and wait for SERVICE_STOPPED
                    status = win32service.QueryServiceStatus(h_svc)
                    if status[1] != win32service.SERVICE_STOPPED:
                        try:
                            win32service.ControlService(h_svc, win32service.SERVICE_CONTROL_STOP)
                            for _ in range(15):
                                time.sleep(0.1)
                                cur_st = win32service.QueryServiceStatus(h_svc)
                                if cur_st[1] == win32service.SERVICE_STOPPED:
                                    break
                        except Exception as e:
                            winerr = getattr(e, "winerror", None) or (e.args[0] if e.args and isinstance(e.args[0], int) else None)
                            if winerr == 1060:
                                logger.debug(f"Service {svc_name} does not exist (WinError 1060)")
                            else:
                                logger.warning(f"Failed to control service {svc_name}: {e}")
                    stopped_list.append(svc_name)
                    logger.info(f"Disabled and stopped conflicting ASUS service: {svc_name}")
                except Exception as e:
                    winerr = getattr(e, "winerror", None) or (e.args[0] if e.args and isinstance(e.args[0], int) else None)
                    if winerr == 1060:
                        logger.debug(f"Service {svc_name} does not exist (WinError 1060)")
                    else:
                        logger.warning(f"Failed to disable/stop ASUS service {svc_name}: {e}")
                finally:
                    if h_svc is not None:
                        try:
                            win32service.CloseServiceHandle(h_svc)
                        except Exception:
                            pass
        except Exception as e:
            return False, f"Ошибка доступа к диспетчеру служб (SCM): {e}"
        finally:
            if scm is not None:
                try:
                    win32service.CloseServiceHandle(scm)
                except Exception:
                    pass

        # Sync ChargingRate in registry and apply direct ACPI IOCTL
        try:
            from config import config
            from asus_battery import AsusBatteryController
            AsusBatteryController._sync_registry(config.battery_charge_limit)
            AsusBatteryController.set_charge_limit_direct(config.battery_charge_limit)
        except Exception as e:
            logger.warning(f"Failed to sync registry or apply battery limit direct: {e}")

        if stopped_list:
            return True, f"Отключены службы ASUS: {', '.join(stopped_list)}"
        return True, "Конфликтующие службы ASUS уже отключены или отсутствуют."

    @classmethod
    def enable_conflicting_services(cls) -> Tuple[bool, str]:
        """Restores ASUS services to SERVICE_AUTO_START and starts them."""
        if not is_admin():
            return cls._run_elevated_cli("--enable-asus-services")

        if not HAS_WIN32SERVICE:
            return False, "Модуль win32service недоступен"

        started_list: List[str] = []
        scm = None
        try:
            scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ALL_ACCESS)
            for svc_name in CONFLICTING_ASUS_SERVICES:
                h_svc = None
                try:
                    h_svc = win32service.OpenService(
                        scm,
                        svc_name,
                        win32service.SERVICE_START
                        | win32service.SERVICE_CHANGE_CONFIG
                        | win32service.SERVICE_QUERY_STATUS,
                    )
                    win32service.ChangeServiceConfig(
                        h_svc,
                        win32service.SERVICE_NO_CHANGE,
                        win32service.SERVICE_AUTO_START,
                        win32service.SERVICE_NO_CHANGE,
                        None, None, 0, None, None, None, None,
                    )
                    status = win32service.QueryServiceStatus(h_svc)
                    if status[1] == win32service.SERVICE_STOPPED:
                        try:
                            win32service.StartService(h_svc, None)
                        except Exception as e:
                            winerr = getattr(e, "winerror", None) or (e.args[0] if e.args and isinstance(e.args[0], int) else None)
                            if winerr == 1060:
                                logger.debug(f"Service {svc_name} does not exist (WinError 1060)")
                            else:
                                logger.warning(f"Failed to start service {svc_name}: {e}")
                    started_list.append(svc_name)
                except Exception as e:
                    winerr = getattr(e, "winerror", None) or (e.args[0] if e.args and isinstance(e.args[0], int) else None)
                    if winerr == 1060:
                        logger.debug(f"Service {svc_name} does not exist (WinError 1060)")
                    else:
                        logger.warning(f"Failed to enable/start ASUS service {svc_name}: {e}")
                finally:
                    if h_svc is not None:
                        try:
                            win32service.CloseServiceHandle(h_svc)
                        except Exception:
                            pass
        except Exception as e:
            return False, f"Ошибка восстановления служб: {e}"
        finally:
            if scm is not None:
                try:
                    win32service.CloseServiceHandle(scm)
                except Exception:
                    pass

        if started_list:
            return True, f"Включены службы ASUS: {', '.join(started_list)}"
        return True, "Службы ASUS не найдены."

    @classmethod
    def _run_elevated_cli(cls, flag: str) -> Tuple[bool, str]:
        """Launches elevated process via UAC to configure SCM services."""
        try:
            if getattr(sys, "frozen", False):
                exe = sys.executable
                params = flag
            else:
                exe = sys.executable
                main_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
                params = f'"{main_py}" {flag}'
            ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 0)
            if int(ret) > 32:
                time.sleep(0.2)
                return True, "Запрос выполнен с правами администратора (UAC)."
            return False, "Запрос прав администратора (UAC) был отклонён."
        except Exception as e:
            return False, f"Ошибка вызова UAC: {e}"
