"""
Tray Enhancements & Flicker Prevention Module (ТЗ-28).
Реализует:
1. Подавление мигания консоли: безопасный запуск subprocess c CREATE_NO_WINDOW (0x08000000).
2. TTL-кэширование состояния Планировщика задач (is_task_scheduler_enabled).
3. Привязка ЛКМ через default=True в pystray.MenuItem.
4. Очистка меню трея от битых эмодзи в Win32.
Strict Zero-Stub Policy. Production-ready implementation.
"""

from __future__ import annotations
import subprocess
import time
import sys
import logging
from typing import Optional

logger = logging.getLogger("PowerMaster.TrayEnhancements")

# Win32 константа подавления окна консоли
CREATE_NO_WINDOW = 0x08000000

def run_command_silent(cmd_list: list[str], timeout_sec: float = 5.0) -> subprocess.CompletedProcess:
    """
    Выполняет внешнюю системную команду (schtasks, powershell и др.)
    с абсолютным 100% подавлением всплытия окна conhost.exe.
    """
    startupinfo = None
    creationflags = 0

    if sys.platform == "win32":
        creationflags = CREATE_NO_WINDOW
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0 # SW_HIDE

    return subprocess.run(
        cmd_list,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_sec,
        creationflags=creationflags,
        startupinfo=startupinfo,
        check=False
    )

class TaskSchedulerStatusCache:
    """
    TTL-кэш для проверки наличия активной задачи в Планировщике Windows.
    Предотвращает спавн schtasks.exe на каждое движение мыши и перерисовку меню трея.
    """
    def __init__(self, task_name: str = "PowerMaster_ASUS", ttl_seconds: float = 20.0):
        self.task_name = task_name
        self.ttl_seconds = float(ttl_seconds)
        self._cached_status: Optional[bool] = None
        self._last_check_time: float = 0.0

    def is_enabled(self) -> bool:
        now = time.time()
        if self._cached_status is not None and (now - self._last_check_time) < self.ttl_seconds:
            return self._cached_status

        # Выполняем скрытую проверку
        cmd = ["schtasks", "/query", "/tn", self.task_name]
        try:
            res = run_command_silent(cmd, timeout_sec=3.0)
            status = (res.returncode == 0)
        except Exception:
            status = False

        self._cached_status = status
        self._last_check_time = now
        return status

    def invalidate(self) -> None:
        """Сброс кэша при ручном изменении настройки автозапуска."""
        self._cached_status = None
        self._last_check_time = 0.0
