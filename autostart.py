r"""
PowerMaster_ASUS - Windows Autostart Manager
Configures Windows startup via HKCU\Software\Microsoft\Windows\CurrentVersion\Run
and Windows Task Scheduler with elevated privileges (HighestAvailable).
"""

from __future__ import annotations
import logging
import os
import subprocess
import sys
import tempfile
try:
    import winreg
except ImportError:
    winreg = None
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("PowerMaster.Autostart")

REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_APP_VALUE = "PowerMaster_ASUS"

CREATE_NO_WINDOW = 0x08000000


def is_admin() -> bool:
    """Returns True if the current process is elevated with administrator privileges."""
    import ctypes
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def run_command_silent(cmd_list: list[str], timeout: float = 5.0) -> subprocess.CompletedProcess:
    """Executes a command with complete suppression of conhost.exe console window."""
    startupinfo = None
    creationflags = 0
    if sys.platform == "win32":
        creationflags = CREATE_NO_WINDOW
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE

    return subprocess.run(
        cmd_list,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=creationflags,
        startupinfo=startupinfo,
    )


class AutostartManager:
    """Manages Windows startup via Registry (HKCU Run) and Task Scheduler (Elevated)."""

    TASK_NAME = "PowerMaster_ASUS_Autostart"
    _ts_cache: Optional[bool] = None
    _ts_cache_time: float = 0.0
    _ts_cache_ttl: float = 20.0

    @classmethod
    def invalidate_cache(cls) -> None:
        cls._ts_cache = None
        cls._ts_cache_time = 0.0

    @classmethod
    def get_launch_command(cls) -> str:
        """Returns the command line to launch PowerMaster in the background."""
        if getattr(sys, "frozen", False):
            exe_path = Path(sys.executable).resolve()
            if "_MEI" in str(exe_path).upper():
                logger.error(f"Refusing temporary _MEI path for autostart: {exe_path}")
                local_app = os.environ.get("LOCALAPPDATA", "")
                if local_app:
                    for cand in [
                        Path(local_app) / "PowerMaster_ASUS" / "PowerMaster_ASUS.exe",
                        Path(local_app) / "Programs" / "PowerMaster_ASUS" / "PowerMaster_ASUS.exe",
                    ]:
                        if cand.exists():
                            exe_path = cand
                            break
            return f'"{exe_path}" --tray'

        base_dir = Path(__file__).resolve().parent
        launcher_pyw = base_dir / "launcher.pyw"

        # Locate pythonw.exe to run without a console window
        python_exe = sys.executable
        py_dir = os.path.dirname(python_exe)
        pythonw_exe = os.path.join(py_dir, "pythonw.exe")
        if not os.path.exists(pythonw_exe):
            pythonw_exe = python_exe

        return f'"{pythonw_exe}" "{launcher_pyw}" --tray'

    @classmethod
    def is_enabled(cls) -> bool:
        """Checks whether the autostart registry key exists."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_READ) as key:
                val, _ = winreg.QueryValueEx(key, REG_APP_VALUE)
                return bool(val)
        except FileNotFoundError:
            return False
        except Exception as e:
            logger.debug(f"Error checking autostart registry key: {e}")
            return False

    @classmethod
    def set_enabled(cls, enable: bool) -> Tuple[bool, str]:
        """Enables or disables automatic startup with Windows."""
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                REG_RUN_KEY,
                0,
                winreg.KEY_SET_VALUE | winreg.KEY_READ,
            ) as key:
                if enable:
                    cmd = cls.get_launch_command()
                    winreg.SetValueEx(key, REG_APP_VALUE, 0, winreg.REG_SZ, cmd)
                    logger.info(f"Autostart enabled with command: {cmd}")
                    return True, "Автозапуск с Windows успешно включен."
                else:
                    try:
                        winreg.DeleteValue(key, REG_APP_VALUE)
                        logger.info("Autostart registry value deleted.")
                        return True, "Автозапуск с Windows отключен."
                    except FileNotFoundError:
                        return True, "Автозапуск уже был отключен."
        except Exception as e:
            msg = f"Ошибка изменения реестра автозапуска: {e}"
            logger.error(msg)
            return False, msg

    # Alias for explicit registry-level autostart control
    set_registry_enabled = set_enabled

    @classmethod
    def toggle(cls) -> Tuple[bool, str]:
        """Toggles current autostart state."""
        current = cls.is_enabled()
        return cls.set_enabled(not current)

    @classmethod
    def get_mode(cls) -> str:
        """
        Returns active autostart mode:
        'admin' -> Task Scheduler (elevated, no UAC)
        'user'  -> HKCU Registry Run (standard user)
        'none'  -> Disabled
        """
        if cls.is_task_scheduler_enabled():
            return "admin"
        if cls.is_enabled():
            return "user"
        return "none"

    @classmethod
    def set_mode(cls, mode: str) -> Tuple[bool, str]:
        """
        Atomically switches between autostart modes ensuring mutual exclusion:
        'admin': Enables Task Scheduler, deletes Registry Run
        'user':  Enables Registry Run, deletes Task Scheduler
        'none':  Deletes both
        """
        cls.invalidate_cache()
        if mode == "admin":
            ok, msg = cls.set_task_scheduler_enabled(True)
            if ok:
                cls.set_enabled(False)
                return True, "Автозапуск от имени Администратора (без UAC) успешно включен."
            return False, msg
        elif mode == "user":
            if cls.is_task_scheduler_enabled():
                cls.set_task_scheduler_enabled(False)
            ok, msg = cls.set_enabled(True)
            if ok:
                return True, "Обычный автозапуск (без прав Администратора) включен."
            return False, msg
        elif mode == "none":
            if cls.is_task_scheduler_enabled():
                cls.set_task_scheduler_enabled(False)
            cls.set_enabled(False)
            return True, "Автозапуск отключен."
        return False, f"Неизвестный режим: {mode}"

    @classmethod
    def generate_task_scheduler_xml(cls) -> str:
        """
        Generates Windows Task Scheduler XML manifest configured for:
        - HighestAvailable execution level (Run as Admin without UAC prompt at logon)
        - 5 second logon delay for desktop initialization
        - Don't stop when on battery
        """
        from xml.sax.saxutils import escape

        if getattr(sys, "frozen", False):
            exe_path = Path(sys.executable).resolve()
            if "_MEI" in str(exe_path).upper():
                logger.error(f"Refusing temporary _MEI path for Task Scheduler: {exe_path}")
                local_app = os.environ.get("LOCALAPPDATA", "")
                if local_app:
                    for cand in [
                        Path(local_app) / "PowerMaster_ASUS" / "PowerMaster_ASUS.exe",
                        Path(local_app) / "Programs" / "PowerMaster_ASUS" / "PowerMaster_ASUS.exe",
                    ]:
                        if cand.exists():
                            exe_path = cand
                            break
            cmd_escaped = escape(str(exe_path))
            args_escaped = "--tray"
            work_dir_escaped = escape(str(exe_path.parent))
        else:
            base_dir = Path(__file__).resolve().parent
            launcher_pyw = str(base_dir / "launcher.pyw")
            python_exe = sys.executable
            py_dir = os.path.dirname(python_exe)
            pythonw_exe = os.path.join(py_dir, "pythonw.exe")
            if not os.path.exists(pythonw_exe):
                pythonw_exe = python_exe

            cmd_escaped = escape(str(pythonw_exe))
            args_escaped = escape(f'"{launcher_pyw}" --tray')
            work_dir_escaped = escape(str(base_dir))

        xml_content = f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>PowerMaster ASUS - All-in-One Power &amp; Battery Manager with Highest Privileges</Description>
    <Author>Valery &amp; DeepSeek Swarm &amp; Spark</Author>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <Delay>PT5S</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>4</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{cmd_escaped}</Command>
      <Arguments>{args_escaped}</Arguments>
      <WorkingDirectory>{work_dir_escaped}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""
        return xml_content

    @classmethod
    def is_task_scheduler_enabled(cls) -> bool:
        """Checks if the PowerMaster elevated task exists in Task Scheduler (with TTL cache)."""
        import time
        now = time.monotonic()
        if cls._ts_cache is not None and (now - cls._ts_cache_time < cls._ts_cache_ttl):
            return cls._ts_cache

        try:
            res = run_command_silent(["schtasks", "/query", "/tn", cls.TASK_NAME], timeout=3.0)
            status = (res.returncode == 0)
        except Exception as e:
            logger.debug(f"Error querying schtasks: {e}")
            status = False

        cls._ts_cache = status
        cls._ts_cache_time = now
        return status

    @classmethod
    def set_task_scheduler_enabled(cls, enable: bool) -> Tuple[bool, str]:
        """
        Creates or removes the elevated task in Windows Task Scheduler.
        If current process is non-admin, requests one-time UAC elevation via ShellExecuteW 'runas'.
        """
        import ctypes

        cls.invalidate_cache()

        if not enable:
            if not is_admin():
                # Elevate deletion
                try:
                    ret = ctypes.windll.shell32.ShellExecuteW(
                        None,
                        "runas",
                        "schtasks.exe",
                        f'/delete /tn "{cls.TASK_NAME}" /f',
                        None,
                        0,  # SW_HIDE
                    )
                    if ret > 32:
                        cls.invalidate_cache()
                        return True, "Запрос на удаление задачи отправлен через UAC."
                    return False, f"UAC запрос отклонен (код {ret})."
                except Exception as e:
                    return False, f"Ошибка вызова UAC элевации: {e}"

            try:
                res = run_command_silent(
                    ["schtasks", "/delete", "/tn", cls.TASK_NAME, "/f"],
                    timeout=5.0,
                )
                cls.invalidate_cache()
                if res.returncode == 0:
                    logger.info("Removed PowerMaster from Task Scheduler.")
                    return True, "Автозапуск через Планировщик задач отключен."
                return False, f"Ошибка удаления задачи: {res.stderr}"
            except Exception as e:
                return False, f"Исключение при удалении задачи: {e}"

        # Enable elevated task
        xml_content = cls.generate_task_scheduler_xml()
        tmp_xml = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-16", suffix=".xml", delete=False) as f:
                tmp_xml = f.name
                f.write(xml_content)

            if not is_admin():
                # One-time UAC prompt to import XML into Task Scheduler
                ret = ctypes.windll.shell32.ShellExecuteW(
                    None,
                    "runas",
                    "schtasks.exe",
                    f'/create /tn "{cls.TASK_NAME}" /xml "{tmp_xml}" /f',
                    None,
                    0,  # SW_HIDE
                )
                if ret > 32:
                    cls.set_enabled(False)
                    cls.invalidate_cache()
                    logger.info("Task Scheduler registration requested via elevated ShellExecuteW.")
                    return True, "Автозапуск через Планировщик задач запрошен через UAC."
                else:
                    return False, f"Пользователь отклонил UAC запрос (код {ret})."

            res = run_command_silent(
                ["schtasks", "/create", "/tn", cls.TASK_NAME, "/xml", tmp_xml, "/f"],
                timeout=5.0,
            )
            cls.invalidate_cache()
            if res.returncode == 0:
                logger.info("Registered PowerMaster elevated task in Task Scheduler.")
                cls.set_enabled(False)
                return True, "Автозапуск с повышенными правами (без окон UAC) успешно настроен в Планировщике задач."
            else:
                return False, f"Ошибка создания задачи: {res.stderr or res.stdout}"
        except Exception as e:
            return False, f"Исключение при регистрации в Планировщике: {e}"
        finally:
            if tmp_xml and os.path.exists(tmp_xml):
                try:
                    import time
                    time.sleep(0.5)
                    os.unlink(tmp_xml)
                except Exception:
                    pass

    @classmethod
    def auto_heal_autostart_task(cls) -> Tuple[bool, str]:
        r"""
        Self-healing routine when running with Administrator privileges:
        1. Checks if the Task Scheduler task 'PowerMaster_ASUS_Autostart' exists.
        2. If it points to an obsolete path (e.g. C:\Program Files (x86)\... or different from current sys.executable),
           updates the task to point to the current executable.
        3. Cleans up legacy files in C:\Program Files (x86)\PowerMaster_ASUS if they exist.
        """
        if not is_admin():
            return False, "Требуются права Администратора."

        try:
            res = run_command_silent(["schtasks", "/query", "/tn", cls.TASK_NAME, "/xml"], timeout=4.0)
            if res.returncode == 0 and res.stdout:
                current_exe = sys.executable
                # Check if task points to an obsolete path, Program Files, or temporary _MEI path
                stdout_lower = res.stdout.lower()
                if "program files" in stdout_lower or "_mei" in stdout_lower or (
                    getattr(sys, "frozen", False) and (current_exe.lower() not in stdout_lower or "--tray" not in stdout_lower)
                ):
                    logger.info(f"Task Scheduler points to outdated/temporary executable or missing --tray. Auto-healing to: {current_exe} --tray")
                    cls.set_task_scheduler_enabled(True)
                # Deduplicate: if Task Scheduler is active, ensure duplicate registry entry is removed
                if cls.is_enabled():
                    cls.set_enabled(False)
                    logger.info("Cleaned up redundant registry autostart (Task Scheduler is active).")
        except Exception as e:
            logger.debug(f"Error checking/healing task scheduler: {e}")

        # Check and remove legacy Program Files (x86) folder
        try:
            legacy_dir = Path(r"C:\Program Files (x86)\PowerMaster_ASUS")
            if legacy_dir.exists():
                import shutil
                shutil.rmtree(legacy_dir, ignore_errors=True)
                logger.info(f"Cleaned up legacy installation directory: {legacy_dir}")
        except Exception as e:
            logger.debug(f"Error cleaning legacy directory: {e}")

        return True, "Автозапуск синхронизирован."

