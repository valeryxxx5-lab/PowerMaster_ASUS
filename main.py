"""
PowerMaster_ASUS - Main Application Entry Point
All-in-One Power & Battery Manager for ASUS TUF Gaming A15 (FA506IU)
"""

from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes
import logging
import os
import sys

for _k in list(os.environ.keys()):
    if _k.upper().startswith("_PYI_") or _k.upper().startswith("_MEI"):
        del os.environ[_k]

from config import (
    APP_TITLE,
    APP_VERSION,
    LOG_PATH,
    config,
)
from asus_battery import AsusBatteryController, is_admin
from autostart import AutostartManager
from power_plan import PowerPlanManager
from power_watcher import PowerWatcher
from tray_app import PowerMasterTrayApp

ERROR_ALREADY_EXISTS = 183


def setup_logging(verbose: bool = False) -> None:
    """Configures multi-sink logging to file and console."""
    log_level = logging.DEBUG if verbose else logging.INFO
    log_format = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"

    handlers: list[logging.Handler] = []
    # File handler
    try:
        fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
        fh.setLevel(log_level)
        fh.setFormatter(logging.Formatter(log_format))
        handlers.append(fh)
    except Exception:
        pass

    # Stream handler
    if sys.stdout is not None:
        try:
            sh = logging.StreamHandler(sys.stdout)
            sh.setLevel(log_level)
            sh.setFormatter(logging.Formatter(log_format))
            handlers.append(sh)
        except Exception:
            pass

    logging.basicConfig(level=log_level, handlers=handlers)


def acquire_single_instance_mutex(
    mutex_name: str = "Local\\PowerMaster_ASUS_SingleInstance_Mutex",
    timeout_sec: float = 5.0,
):
    """
    Ensures that only one instance of PowerMaster runs simultaneously using a Windows Mutex.
    Retries up to timeout_sec to allow an exiting or restarting instance to cleanly close.
    Returns the mutex handle if this is the active instance, or None if already running.
    """
    import random
    import time
    kernel32 = ctypes.windll.kernel32
    start = time.time()
    while True:
        handle = kernel32.CreateMutexW(None, wintypes.BOOL(True), mutex_name)
        last_error = kernel32.GetLastError()
        if not handle:
            # Handle is NULL (e.g. ERROR_ACCESS_DENIED when created by elevated process)
            if timeout_sec > 0.0 and time.time() - start < timeout_sec:
                time.sleep(random.uniform(0.05, 0.25))
                continue
            return None
        if last_error == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            if timeout_sec > 0.0 and time.time() - start < timeout_sec:
                time.sleep(random.uniform(0.05, 0.25))
                continue
            return None
        return handle


def print_status() -> None:
    active_guid, friendly_name = PowerPlanManager.get_active_plan()
    admin = is_admin()
    limit, limit_details = AsusBatteryController.get_current_limit()
    is_ac, batt_pct = PowerWatcher.get_power_status()
    idle_sec = PowerWatcher.get_user_idle_seconds()
    autostart = AutostartManager.is_enabled()

    print("=" * 60)
    print(f" {APP_TITLE} v{APP_VERSION} - System Status")
    print("=" * 60)
    print(f" * Права Администратора:       {'Да (Elevated)' if admin else 'Нет (Обычный пользователь)'}")
    print(f" * Активный план питания:     {friendly_name} ({active_guid})")
    print(f" * Источник питания:          {'Сеть AC (220V)' if is_ac else 'Батарея'}")
    print(f" * Заряд аккумулятора:        {batt_pct}%")
    print(f" * Лимит заряда ASUS WMI:     {limit}% ({limit_details})")
    print(f" * Время простоя пользователя: {int(idle_sec)} сек")
    print(f" * Автозапуск Windows (Run):  {'Включен' if autostart else 'Отключен'}")
    print(f" * Авто-переключение планов:  {'Включено' if config.auto_switching_enabled else 'Отключено'}")
    print("=" * 60)


SHUTDOWN_EVENT_NAME = r"Local\PowerMaster_ASUS_Shutdown_Event"


def signal_shutdown_existing() -> bool:
    """Signals any running PowerMaster instance to cleanly remove its tray icon and exit."""
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.OpenEventW.restype = wintypes.HANDLE
        kernel32.SetEvent.argtypes = [wintypes.HANDLE]
        kernel32.SetEvent.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        EVENT_MODIFY_STATE = 0x0002
        h_event = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, SHUTDOWN_EVENT_NAME)
        if h_event:
            kernel32.SetEvent(h_event)
            kernel32.CloseHandle(h_event)
            return True
    except Exception as e:
        logging.getLogger("PowerMaster").debug(f"Could not signal shutdown event: {e}")
    return False


def terminate_duplicate_instances() -> int:
    """
    Обнаруживает и завершает все ранее запущенные экземпляры PowerMaster,
    обеспечивая чистый запуск новой версии (Single-Instance Takeover).
    1. Сначала отправляет сигнал мягкого выхода (Shutdown Event), чтобы старый процесс
       удалил иконку из трея и очистил %TEMP%\_MEIxxxxxx.
    2. Затем принудительно завершает любые оставшиеся процессы (сначала дочерние Worker,
       затем зависшие Bootloader), игнорируя текущий процесс и всех его предков.
    """
    import time
    import psutil

    log = logging.getLogger("PowerMaster")
    my_pid = os.getpid()
    protected_pids = {my_pid}
    try:
        curr_proc = psutil.Process(my_pid)
        for parent in curr_proc.parents():
            protected_pids.add(parent.pid)
    except Exception:
        try:
            ppid = os.getppid()
            if ppid:
                protected_pids.add(ppid)
        except Exception:
            pass

    target_names = {"powermaster_asus.exe", "powermaster_asus_portable.exe", "powermaster.exe"}

    def _find_foreign_procs() -> list:
        found = []
        for proc in psutil.process_iter(["pid", "ppid", "name"]):
            try:
                p_pid = proc.info["pid"]
                p_name = (proc.info["name"] or "").lower()
                if p_pid in protected_pids:
                    continue
                if p_name in target_names:
                    found.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return found

    foreign = _find_foreign_procs()
    if not foreign:
        return 0

    # Шаг 1: Кооперативный сигнал завершения (убирает фантомную иконку из трея и обходит AccessDenied)
    if signal_shutdown_existing():
        log.info("Отправлен сигнал мягкого завершения старому экземпляру PowerMaster...")
        for _ in range(8):
            time.sleep(0.1)
            foreign = _find_foreign_procs()
            if not foreign:
                log.info("Старый экземпляр корректно завершился самостоятельно.")
                return 1

    # Шаг 2: Принудительное завершение (сначала дочерние процессы Worker, чтобы Bootloader очистил _MEI)
    foreign_pids = {p.pid for p in foreign}
    workers = [p for p in foreign if p.info.get("ppid") in foreign_pids]
    bootloaders = [p for p in foreign if p.info.get("ppid") not in foreign_pids]

    terminated_count = 0
    for group in (workers, bootloaders):
        for proc in group:
            try:
                if not proc.is_running():
                    continue
                log.info(f"Обнаружен работающий дубликат PowerMaster (PID={proc.pid}). Завершение старого процесса...")
                proc.terminate()
                try:
                    proc.wait(timeout=1.0)
                except psutil.TimeoutExpired:
                    proc.kill()
                terminated_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                log.debug(f"Could not terminate PID={getattr(proc, 'pid', '?')}: {e}")
                continue
        if group is workers and workers:
            time.sleep(0.25)  # Даём родительскому Bootloader штатно удалить %TEMP%\_MEIxxxxxx

    if terminated_count > 0:
        time.sleep(0.2)
    return terminated_count


def signal_show_dashboard() -> bool:
    """Signals the running PowerMaster instance via Win32 event to open/lift Dashboard."""
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.OpenEventW.restype = wintypes.HANDLE
        kernel32.SetEvent.argtypes = [wintypes.HANDLE]
        kernel32.SetEvent.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        EVENT_MODIFY_STATE = 0x0002
        h_event = kernel32.OpenEventW(EVENT_MODIFY_STATE, False, "Local\\PowerMaster_ASUS_ShowDashboard_Event")
        if h_event:
            kernel32.SetEvent(h_event)
            kernel32.CloseHandle(h_event)
            return True
    except Exception as e:
        logging.getLogger("PowerMaster").debug(f"Could not signal show dashboard event: {e}")
    return False


def main():
    # 1. DPI Awareness initialization (Per-Monitor V2) strictly before GUI subsystems
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass

    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description=f"{APP_TITLE} v{APP_VERSION} - Power & Battery Manager for ASUS TUF",
    )
    parser.add_argument("--status", action="store_true", help="Print current power and battery status and exit")
    parser.add_argument(
        "--set-limit",
        type=int,
        choices=[60, 80, 100],
        help="Set ASUS battery charge limit percentage (60, 80, 100)",
    )
    parser.add_argument(
        "--set-plan",
        choices=["high", "balanced", "saver"],
        help="Switch active power plan (high, balanced, saver)",
    )
    parser.add_argument(
        "--autostart",
        choices=["enable", "disable", "toggle"],
        help="Configure Windows startup registration",
    )
    parser.add_argument(
        "--notifications",
        choices=["enable", "disable", "toggle"],
        help="Configure popup notifications (enable, disable, toggle)",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose debug logging")
    parser.add_argument("--tray", action="store_true", help="Explicitly launch in system tray mode (default)")
    parser.add_argument("--dashboard", action="store_true", help="Launch standalone Dashboard GUI and exit when closed")
    parser.add_argument("--disable-asus-services", action="store_true", help="Disable and stop conflicting ASUS background services")
    parser.add_argument("--enable-asus-services", action="store_true", help="Re-enable and start ASUS background services")
    parser.add_argument("--status-asus-services", action="store_true", help="Print ASUS background services status and exit")

    args = parser.parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger("PowerMaster")

    # Handle standalone dashboard mode
    if args.dashboard:
        try:
            hwnd_console = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd_console:
                ctypes.windll.user32.ShowWindow(hwnd_console, 0)  # 0 = SW_HIDE
        except Exception:
            pass
        from dashboard import run_standalone_dashboard
        run_standalone_dashboard()
        sys.exit(0)

    # Handle single-shot CLI commands first
    if args.status:
        print_status()
        sys.exit(0)

    if args.set_limit is not None:
        if is_admin():
            ok, msg = AsusBatteryController.set_charge_limit_direct(args.set_limit)
        else:
            ok, msg = AsusBatteryController.set_charge_limit_elevated(args.set_limit)
        print(f"[{'OK' if ok else 'FAIL'}] {msg}")
        sys.exit(0 if ok else 1)

    if args.set_plan:
        ok, msg = PowerPlanManager.set_active_plan(args.set_plan)
        print(f"[{'OK' if ok else 'FAIL'}] {msg}")
        sys.exit(0 if ok else 1)

    if args.autostart:
        if args.autostart == "enable":
            ok, msg = AutostartManager.set_enabled(True)
        elif args.autostart == "disable":
            ok, msg = AutostartManager.set_enabled(False)
        else:
            ok, msg = AutostartManager.toggle()
        print(f"[{'OK' if ok else 'FAIL'}] {msg}")
        sys.exit(0 if ok else 1)

    if args.notifications:
        if args.notifications == "enable":
            config.notify_on_plan_change = True
            msg = "Всплывающие уведомления включены."
        elif args.notifications == "disable":
            config.notify_on_plan_change = False
            msg = "Всплывающие уведомления отключены."
        else:
            config.notify_on_plan_change = not config.notify_on_plan_change
            status = "включены" if config.notify_on_plan_change else "отключены"
            msg = f"Всплывающие уведомления {status}."
        print(f"[OK] {msg}")
        sys.exit(0)

    if args.disable_asus_services:
        from asus_services import AsusServiceManager
        ok, msg = AsusServiceManager.disable_conflicting_services()
        print(f"[{'OK' if ok else 'FAIL'}] {msg}")
        sys.exit(0 if ok else 1)

    if args.enable_asus_services:
        from asus_services import AsusServiceManager
        ok, msg = AsusServiceManager.enable_conflicting_services()
        print(f"[{'OK' if ok else 'FAIL'}] {msg}")
        sys.exit(0 if ok else 1)

    if args.status_asus_services:
        from asus_services import AsusServiceManager
        statuses = AsusServiceManager.get_asus_services_status()
        print("ASUS Conflicting Services:")
        for name, st in statuses.items():
            print(f"  {name}: {st}")
        sys.exit(0)

    # Launch GUI System Tray application
    # Automatically hide the console window if started via python.exe or cmd
    try:
        hwnd_console = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd_console:
            ctypes.windll.user32.ShowWindow(hwnd_console, 0)  # 0 = SW_HIDE
    except Exception:
        pass

    # 1. Terminate any foreign duplicate instances (Single-Instance Takeover)
    terminate_duplicate_instances()

    # 2. Check single instance mutex
    # Retries up to 5s to allow an exiting old instance to cleanly release the mutex
    mutex = acquire_single_instance_mutex(timeout_sec=5.0)
    if not mutex:
        if args.tray:
            logger.info("PowerMaster is already running in background. Exiting duplicate --tray instance.")
            sys.exit(0)
        logger.info("PowerMaster is already running. Signaling existing instance to open Dashboard.")
        if signal_show_dashboard():
            sys.exit(0)
        try:
            from dashboard import run_standalone_dashboard
            run_standalone_dashboard()
        except Exception as e:
            logger.error(f"Failed to open dashboard: {e}")
        sys.exit(0)

    logger.info(f"Initializing {APP_TITLE} v{APP_VERSION}...")
    if is_admin():
        try:
            AutostartManager.auto_heal_autostart_task()
        except Exception as e:
            logger.debug(f"Autostart auto-heal exception: {e}")
    mutex_holder = [mutex]

    def release_mutex():
        if mutex_holder[0]:
            try:
                ctypes.windll.kernel32.CloseHandle(mutex_holder[0])
            except Exception:
                pass
            mutex_holder[0] = None

    try:
        # When autostarted with --tray, stay in tray. When launched manually by user without --tray or with --dashboard, open dashboard.
        auto_open = bool(args.dashboard or (not args.tray) or getattr(config, "open_dashboard_on_startup", False))
        app = PowerMasterTrayApp(on_restart_release_mutex=release_mutex, auto_open_dashboard=auto_open)
        app.run()
    except Exception as e:
        logger.critical(f"Fatal unhandled exception in tray application: {e}", exc_info=True)
    finally:
        release_mutex()


if __name__ == "__main__":
    main()
