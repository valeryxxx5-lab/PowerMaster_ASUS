"""
PowerMaster_ASUS - Configuration Management
Defines default settings, system GUIDs, hardware thresholds, and handles JSON persistence.
"""

from __future__ import annotations
import json
import os

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

APP_NAME = "PowerMaster_ASUS"
APP_TITLE = "PowerMaster ASUS TUF"
APP_VERSION = "0.2.61-beta"

import sys
import threading

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent


def _is_dir_writable(path: Path) -> bool:
    try:
        if not path.exists():
            return False
        test_file = path / f".write_test_{os.getpid()}"
        with open(test_file, "w") as f:
            f.write("1")
        test_file.unlink()
        return True
    except Exception:
        return False


def get_app_data_dir() -> Path:
    r"""
    Returns a writable directory for application settings and logs.
    If BASE_DIR is writable (e.g. portable mode or development workspace), uses BASE_DIR.
    Otherwise (e.g. installed in C:\Program Files (x86)\PowerMaster_ASUS), uses %APPDATA%\PowerMaster_ASUS.
    """
    if _is_dir_writable(BASE_DIR):
        return BASE_DIR

    appdata = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME
    try:
        appdata.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    # Migrate defaults from BASE_DIR / config.json if present
    base_cfg = BASE_DIR / "config.json"
    user_cfg = appdata / "config.json"
    if base_cfg.exists() and not user_cfg.exists():
        try:
            import shutil
            shutil.copy2(base_cfg, user_cfg)
        except Exception:
            pass

    return appdata


APP_DATA_DIR = get_app_data_dir()
CONFIG_PATH = APP_DATA_DIR / "config.json"
LOG_PATH = APP_DATA_DIR / "powermaster.log"

# Windows Power Plan GUIDs (Standard ASUS / Windows Schemes)
GUID_HIGH_PERFORMANCE = "07fa2daf-30e4-41ad-8daf-5bf18a330c48"
GUID_BALANCED = "381b4222-f694-41f0-9685-ff5bb260df2e"
GUID_POWER_SAVER = "d6c42cfd-bf64-4edf-85e4-9b82cd8789d8"

PLAN_NAMES = {
    GUID_HIGH_PERFORMANCE: "Высокая производительность",
    GUID_BALANCED: "Сбалансированная",
    GUID_POWER_SAVER: "Экономия энергии",
}

# ASUS ACPI WMI Constants
ASUS_WMI_NAMESPACE = "root\\wmi"
ASUS_WMI_CLASS = "AsusAtkWmi_WMNB"
ASUS_WMI_METHOD_SET = "DEVS"
ASUS_WMI_METHOD_GET = "DSTS"
ASUS_DEVICE_ID_BATTERY_LIMIT = 0x00120057
ASUS_DEVICE_ID_THERMAL_POLICY = 0x00120075

LEGACY_SUPER_ECO_KEYS = (
    "super_eco_enabled",
    "super_eco_delay_seconds",
    "super_eco_cpu_threshold",
    "windows_energy_saver_in_super_eco",
)

DEFAULT_CONFIG: Dict[str, Any] = {
    "battery_charge_limit": 60,
    "startup_boost_seconds": 180,
    "idle_timeout_seconds": 180,
    "poll_interval_seconds": 2.0,
    "game_directories": [],
    "game_process_names": [],
    "auto_switching_enabled": True,
    "manual_override_guid": None,
    "minimize_to_tray": True,
    "open_dashboard_on_startup": False,
    "start_with_windows": False,
    "notify_on_plan_change": False,
    "icon_style": "style_d",
    "language": "ru",
    "github_token": "",
    "check_updates_daily": True,
    "last_update_check": 0.0,
    "ui_scale": 1.0,
    "ui_theme": "cyber_dark",
    "tray_menu_text_size": "standard",
    "asus_thermal_policy": 0,
    "perfboostmode_disabled_in_saver": True,
    "balanced_perf_boost_mode": 3,
    "windows_energy_saver_manual": False,
    "power_plans": {
        "high_performance": GUID_HIGH_PERFORMANCE,
        "balanced": GUID_BALANCED,
        "power_saver": GUID_POWER_SAVER,
    },
}

import base64
import logging

try:
    import win32crypt
    HAS_WIN32CRYPT = True
except ImportError:
    win32crypt = None
    HAS_WIN32CRYPT = False

DPAPI_PREFIX = "dpapi:"
_cfg_logger = logging.getLogger("PowerMaster.Config")


def encrypt_secret(plaintext: str) -> str:
    """Encrypts a plaintext secret using Windows DPAPI (CurrentUser scope)."""
    if not plaintext:
        return ""
    clean = str(plaintext).strip()
    if not clean or clean.startswith(DPAPI_PREFIX):
        return clean
    if not HAS_WIN32CRYPT or win32crypt is None:
        return clean
    try:
        raw_bytes = clean.encode("utf-8")
        encrypted_bytes = win32crypt.CryptProtectData(
            raw_bytes,
            "PowerMaster Secret",
            None,
            None,
            None,
            0,
        )
        return DPAPI_PREFIX + base64.b64encode(encrypted_bytes).decode("ascii")
    except Exception as e:
        _cfg_logger.error(f"DPAPI encryption failed: {e}")
        return clean


def decrypt_secret(ciphertext: str) -> str:
    """Decrypts a DPAPI-prefixed secret string; returns legacy plaintext as-is."""
    if not ciphertext:
        return ""
    clean = str(ciphertext).strip()
    if not clean.startswith(DPAPI_PREFIX):
        return clean  # Legacy plaintext fallback
    if not HAS_WIN32CRYPT or win32crypt is None:
        return ""
    try:
        payload = clean[len(DPAPI_PREFIX):]
        raw_encrypted = base64.b64decode(payload.encode("ascii"))
        _, decrypted_bytes = win32crypt.CryptUnprotectData(
            raw_encrypted,
            None,
            None,
            None,
            0,
        )
        return decrypted_bytes.decode("utf-8")
    except Exception as e:
        _cfg_logger.error(f"DPAPI decryption failed: {e}")
        return ""



class Config:
    def __init__(self, path: Path = CONFIG_PATH, stat_interval: Optional[float] = None):
        self._lock = threading.RLock()
        self._path = path
        self._data: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self._last_mtime: float = 0.0
        self._last_stat_check_time: float = 0.0
        self._stat_interval: float = 2.0 if stat_interval is None else float(stat_interval)
        self.load()

    def _maybe_reload(self, force: bool = False) -> None:
        with self._lock:
            try:
                import time
                now = time.monotonic()
                if not force and (now - self._last_stat_check_time < self._stat_interval):
                    return
                self._last_stat_check_time = now

                if self._path.exists():
                    mtime = os.path.getmtime(self._path)
                    if force or (mtime > self._last_mtime):
                        self.load()
            except Exception:
                pass

    def load(self) -> None:
        with self._lock:
            if self._path.exists():
                try:
                    self._last_mtime = os.path.getmtime(self._path)
                    with open(self._path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict):
                            self._data.update(loaded)
                    removed_legacy = False
                    for k in LEGACY_SUPER_ECO_KEYS:
                        if k in self._data:
                            del self._data[k]
                            removed_legacy = True
                    # Авто-миграция открытого github_token в DPAPI
                    raw_tok = self._data.get("github_token", "")
                    if isinstance(raw_tok, str) and raw_tok and not raw_tok.startswith(DPAPI_PREFIX):
                        encrypted_tok = encrypt_secret(raw_tok)
                        if encrypted_tok.startswith(DPAPI_PREFIX):
                            self._data["github_token"] = encrypted_tok
                            removed_legacy = True
                    if removed_legacy:
                        self.save()
                except Exception:
                    # Keep defaults if file corrupted
                    pass
            else:
                self.save()

    def save(self) -> bool:
        with self._lock:
            tmp_path: Optional[Path] = None
            try:
                # Гарантируем, что перед записью на диск github_token всегда зашифрован DPAPI
                raw_tok = self._data.get("github_token", "")
                if isinstance(raw_tok, str) and raw_tok and not raw_tok.startswith(DPAPI_PREFIX):
                    self._data["github_token"] = encrypt_secret(raw_tok)

                target_dir = self._path.parent
                target_dir.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    "w",
                    dir=target_dir,
                    delete=False,
                    suffix=".tmp",
                    encoding="utf-8",
                ) as f:
                    tmp_path = Path(f.name)
                    json.dump(self._data, f, indent=4, ensure_ascii=False)
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except OSError:
                        pass
                os.replace(tmp_path, self._path)
                if self._path.exists():
                    self._last_mtime = os.path.getmtime(self._path)
                return True
            except Exception as e:
                if tmp_path and tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except Exception:
                        pass
                _cfg_logger.error(f"Failed to save configuration to {self._path}: {e}")
                return False

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            self._maybe_reload()
            val = self._data.get(key, default)
            if key == "github_token" and isinstance(val, str):
                return decrypt_secret(val)
            return val

    def set(self, key: str, value: Any) -> bool:
        with self._lock:
            self._maybe_reload()
            if key == "github_token" and isinstance(value, str):
                value = encrypt_secret(value.strip())
            self._data[key] = value
            return self.save()

    @property
    def battery_charge_limit(self) -> int:
        return int(self.get("battery_charge_limit", 60))

    @battery_charge_limit.setter
    def battery_charge_limit(self, value: int) -> None:
        self.set("battery_charge_limit", int(value))

    @property
    def startup_boost_seconds(self) -> int:
        return int(self.get("startup_boost_seconds", 180))

    @property
    def idle_timeout_seconds(self) -> int:
        return int(self.get("idle_timeout_seconds", 180))

    @property
    def poll_interval_seconds(self) -> float:
        return float(self.get("poll_interval_seconds", 2.0))

    @property
    def game_directories(self) -> List[str]:
        raw_dirs = list(self.get("game_directories", DEFAULT_CONFIG["game_directories"]))
        return [os.path.expandvars(d) for d in raw_dirs]

    @property
    def auto_switching_enabled(self) -> bool:
        return bool(self.get("auto_switching_enabled", True))

    @auto_switching_enabled.setter
    def auto_switching_enabled(self, value: bool) -> None:
        self.set("auto_switching_enabled", bool(value))

    @property
    def manual_override_guid(self) -> Optional[str]:
        val = self.get("manual_override_guid", None)
        return str(val) if val else None

    @manual_override_guid.setter
    def manual_override_guid(self, value: Optional[str]) -> None:
        self.set("manual_override_guid", str(value) if value else None)

    def save_atomic(self, new_data: Dict[str, Any]) -> bool:
        with self._lock:
            self._maybe_reload()
            for k, v in new_data.items():
                if k == "github_token" and isinstance(v, str):
                    self._data[k] = encrypt_secret(v.strip())
                else:
                    self._data[k] = v
            return self.save()

    @property
    def minimize_to_tray(self) -> bool:
        return bool(self.get("minimize_to_tray", True))

    @minimize_to_tray.setter
    def minimize_to_tray(self, value: bool) -> None:
        self.set("minimize_to_tray", bool(value))

    @property
    def open_dashboard_on_startup(self) -> bool:
        return bool(self.get("open_dashboard_on_startup", False))

    @open_dashboard_on_startup.setter
    def open_dashboard_on_startup(self, value: bool) -> None:
        self.set("open_dashboard_on_startup", bool(value))

    @property
    def icon_style(self) -> str:
        return str(self.get("icon_style", "style_d"))

    @icon_style.setter
    def icon_style(self, value: str) -> None:
        self.set("icon_style", str(value))

    @property
    def language(self) -> str:
        return str(self.get("language", "ru"))

    @language.setter
    def language(self, value: str) -> None:
        self.set("language", str(value))

    @property
    def notify_on_plan_change(self) -> bool:
        return bool(self.get("notify_on_plan_change", False))

    @notify_on_plan_change.setter
    def notify_on_plan_change(self, value: bool) -> None:
        self.set("notify_on_plan_change", bool(value))

    @property
    def github_token(self) -> str:
        return str(self.get("github_token", ""))

    @github_token.setter
    def github_token(self, value: str) -> None:
        self.set("github_token", str(value).strip())

    @property
    def check_updates_daily(self) -> bool:
        return bool(self.get("check_updates_daily", True))

    @check_updates_daily.setter
    def check_updates_daily(self, value: bool) -> None:
        self.set("check_updates_daily", bool(value))

    @property
    def last_update_check(self) -> float:
        return float(self.get("last_update_check", 0.0))

    @last_update_check.setter
    def last_update_check(self, value: float) -> None:
        self.set("last_update_check", float(value))

    @property
    def ui_scale(self) -> float:
        try:
            return float(self.get("ui_scale", 1.0))
        except (ValueError, TypeError):
            return 1.0

    @ui_scale.setter
    def ui_scale(self, value: float) -> None:
        self.set("ui_scale", float(value))

    @property
    def ui_theme(self) -> str:
        return str(self.get("ui_theme", "cyber_dark"))

    @ui_theme.setter
    def ui_theme(self, value: str) -> None:
        self.set("ui_theme", str(value))




    @property
    def asus_thermal_policy(self) -> int:
        return int(self.get("asus_thermal_policy", 0))

    @asus_thermal_policy.setter
    def asus_thermal_policy(self, value: int) -> None:
        self.set("asus_thermal_policy", int(value))

    @property
    def perfboostmode_disabled_in_saver(self) -> bool:
        return bool(self.get("perfboostmode_disabled_in_saver", True))

    @perfboostmode_disabled_in_saver.setter
    def perfboostmode_disabled_in_saver(self, value: bool) -> None:
        self.set("perfboostmode_disabled_in_saver", bool(value))

    @property
    def balanced_perf_boost_mode(self) -> int:
        return int(self.get("balanced_perf_boost_mode", 3))

    @balanced_perf_boost_mode.setter
    def balanced_perf_boost_mode(self, value: int) -> None:
        self.set("balanced_perf_boost_mode", max(0, min(4, int(value))))


    @property
    def windows_energy_saver_manual(self) -> bool:
        return bool(self.get("windows_energy_saver_manual", False))

    @windows_energy_saver_manual.setter
    def windows_energy_saver_manual(self, value: bool) -> None:
        self.set("windows_energy_saver_manual", bool(value))

    @property
    def tray_menu_text_size(self) -> str:
        val = str(self.get("tray_menu_text_size", "standard"))
        if val not in ("standard", "large", "huge"):
            return "standard"
        return val

    @tray_menu_text_size.setter
    def tray_menu_text_size(self, value: str) -> None:
        if value not in ("standard", "large", "huge"):
            value = "standard"
        self.set("tray_menu_text_size", value)


# Global config singleton
config = Config()
