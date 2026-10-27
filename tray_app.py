"""
PowerMaster_ASUS - System Tray Application
Provides a system tray icon, live status notifications, and context menu for:
- Manual power plan switching
- ASUS battery charge limit toggle (60%, 80%, 100%)
- Auto-switching toggle
- Windows autostart toggle
- UAC elevation request
"""

from __future__ import annotations
import ctypes
import logging
import os
import sys

from typing import Any, Callable, Optional

from PIL import Image, ImageDraw
import pystray
from pystray import Menu, MenuItem
import tkinter as tk

from asus_battery import AsusBatteryController, is_admin
from autostart import AutostartManager
from config import (
    APP_NAME,
    APP_TITLE,
    APP_VERSION,
    GUID_HIGH_PERFORMANCE,
    GUID_BALANCED,
    GUID_POWER_SAVER,
    PLAN_NAMES,
    config,
)
from power_plan import PowerPlanManager
from power_watcher import PowerWatcher

logger = logging.getLogger("PowerMaster.Tray")


class IconGenerator:
    """Dynamically generates modern 64x64 system tray icons based on power state."""

    COLORS = {
        GUID_HIGH_PERFORMANCE: {"bg": "#1E1E1E", "ring": "#FF3344", "bolt": "#FF5555"},
        GUID_BALANCED: {"bg": "#1E1E1E", "ring": "#00A8FF", "bolt": "#00D2D3"},
        GUID_POWER_SAVER: {"bg": "#1E1E1E", "ring": "#10AC84", "bolt": "#1DD1A1"},
    }

    @classmethod
    def create_icon_image(
        cls,
        plan_guid: Optional[str] = None,
        is_ac: bool = True,
        style: Optional[str] = None,
        has_update: bool = False,
    ) -> Image.Image:
        plan_guid = (plan_guid or GUID_BALANCED).lower()
        palette = cls.COLORS.get(plan_guid, cls.COLORS[GUID_BALANCED])
        style = (style or getattr(config, "icon_style", "style_d")).lower()

        if style in ("style_tile", "huge_tile", "tile"):
            try:
                from icon_generator import IconSpeedMetaphorGenerator
                pg = (plan_guid or GUID_BALANCED).lower()
                if pg == GUID_HIGH_PERFORMANCE.lower() or "07fa2daf" in pg or "high" in pg:
                    plan_key = "high"
                elif pg == GUID_POWER_SAVER.lower() or "d6c42cfd" in pg or "saver" in pg:
                    plan_key = "saver"
                else:
                    plan_key = "balanced"
                return IconSpeedMetaphorGenerator.draw_tile_icon(plan_key, is_ac, has_update=has_update)
            except Exception as e:
                logger.debug(f"Failed to generate tile icon: {e}")

        if style in ("style_d", "speed", "silhouette"):
            try:
                from icon_generator import IconSpeedMetaphorGenerator
                pg = (plan_guid or GUID_BALANCED).lower()
                if pg == GUID_HIGH_PERFORMANCE.lower() or "07fa2daf" in pg or "high" in pg:
                    plan_key = "high"
                elif pg == GUID_POWER_SAVER.lower() or "d6c42cfd" in pg or "saver" in pg:
                    plan_key = "saver"
                else:
                    plan_key = "balanced"
                return IconSpeedMetaphorGenerator.generate_icon(plan_key, is_ac, has_update=has_update)
            except Exception as e:
                logger.debug(f"Failed to generate speed metaphor icon: {e}")

        width, height = 64, 64
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        if style == "style_b":
            # Style B: Minimal Battery Indicator
            draw.rounded_rectangle((8, 16, 48, 48), radius=4, outline=palette["ring"], width=3, fill=palette["bg"])
            draw.rounded_rectangle((48, 26, 54, 38), radius=2, fill=palette["ring"])
            fill_color = palette["bolt"]
            draw.rounded_rectangle((13, 21, 43, 43), radius=2, fill=fill_color)
        elif style == "style_c":
            # Style C: ASUS TUF Shield
            shield_pts = [
                (12, 10),
                (52, 10),
                (52, 38),
                (32, 58),
                (12, 38),
            ]
            draw.polygon(shield_pts, fill=palette["bg"], outline=palette["ring"])
            inner_pts = [
                (20, 18),
                (44, 18),
                (44, 34),
                (32, 48),
                (20, 34),
            ]
            draw.polygon(inner_pts, fill=palette["bolt"])
        else:
            # Style A: Default Neon Ring with Lightning Bolt
            ring_color = palette["ring"]
            draw.ellipse((2, 2, width - 3, height - 3), outline=ring_color, width=4)
            draw.ellipse((6, 6, width - 7, height - 7), fill=palette["bg"])
            bolt_points = [
                (34, 12),
                (20, 32),
                (32, 32),
                (26, 52),
                (46, 28),
                (34, 28),
            ]
            draw.polygon(bolt_points, fill=palette["bolt"])

        # Small AC indicator badge at bottom-right
        if is_ac:
            draw.rectangle((44, 44, 58, 58), fill="#00D2D3", outline="#FFFFFF", width=1)
        else:
            draw.rectangle((44, 44, 58, 58), fill="#FFA801", outline="#FFFFFF", width=1)

        # Update indicator badge at top-left
        if has_update:
            draw.ellipse([2, 2, 18, 18], fill="#FF4757", outline="#FFFFFF", width=2)
            draw.polygon([(10, 5), (6, 11), (9, 11), (9, 15), (11, 15), (11, 11), (14, 11)], fill="#FFFFFF")

        return img


class PowerMasterTrayApp:
    """System Tray GUI and event loop for PowerMaster."""

    def __init__(
        self,
        on_restart_release_mutex: Optional[Callable[[], None]] = None,
        auto_open_dashboard: bool = False,
    ):
        self._on_restart_release_mutex = on_restart_release_mutex
        self._auto_open_dashboard = auto_open_dashboard
        self._is_running = True
        self._watcher = PowerWatcher(on_plan_changed=self._on_plan_changed)
        self._icon: Optional[pystray.Icon] = None
        self._current_plan_guid = GUID_BALANCED
        try:
            curr_guid, _ = PowerPlanManager.get_active_plan()
            if curr_guid:
                self._current_plan_guid = curr_guid
        except Exception:
            pass
        self._is_ac = True
        try:
            p_stat = PowerWatcher.get_power_status()
            if isinstance(p_stat, (tuple, list)) and len(p_stat) >= 1:
                self._is_ac = bool(p_stat[0])
        except Exception:
            pass
        self._has_available_update: bool = False
        self._latest_release_info: Optional[Any] = None

        # Pre-evaluate target power plan according to FSM rules (startup boost / battery / games)
        # BEFORE creating tray icon so initial icon matches desired state immediately without glitch
        try:
            snapshot = self._watcher.take_snapshot()
            if snapshot:
                desired_guid, reason = self._watcher.evaluate_desired_plan(snapshot)
                curr_guid = getattr(snapshot, "current_plan_guid", self._current_plan_guid)
                if desired_guid and curr_guid and str(curr_guid).lower() != str(desired_guid).lower():
                    logger.info(f"Initial startup alignment: {reason} -> switching to {desired_guid}")
                    ok, _ = PowerPlanManager.set_active_plan(desired_guid)
                    if ok:
                        self._watcher._last_applied_guid = desired_guid
                        self._watcher._last_reason = reason
                        self._current_plan_guid = desired_guid
                elif desired_guid:
                    self._current_plan_guid = str(desired_guid)
        except Exception as ex:
            logger.debug(f"Initial startup plan alignment skipped: {ex}")

        # Automatically enforce battery charge limit on startup (direct IOCTL works without elevation)
        try:
            AsusBatteryController.set_charge_limit_direct(config.battery_charge_limit)
            logger.info(f"Hardware battery charge limit enforced on startup: {config.battery_charge_limit}%")
        except Exception as e:
            logger.debug(f"Failed to enforce battery limit on init: {e}")

        self._start_update_checker()
        self._start_ipc_listener()
        self._prewarm_dashboard()

    def _start_ipc_listener(self) -> None:
        """Listens for external activation events (e.g. shortcut clicked while running) to lift Dashboard or quit."""
        def _ipc_loop():
            try:
                import ctypes
                from ctypes import wintypes
                kernel32 = ctypes.windll.kernel32
                kernel32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
                kernel32.CreateEventW.restype = wintypes.HANDLE
                kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                kernel32.WaitForSingleObject.restype = wintypes.DWORD
                kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
                kernel32.CloseHandle.restype = wintypes.BOOL

                h_event = kernel32.CreateEventW(None, False, False, "Local\\PowerMaster_ASUS_ShowDashboard_Event")
                if not h_event:
                    return
                try:
                    while getattr(self, "_is_running", True):
                        res = kernel32.WaitForSingleObject(h_event, 1000)
                        if res == 0:  # WAIT_OBJECT_0
                            logger.info("ShowDashboard event signaled via IPC. Opening Dashboard window...")
                            try:
                                self._open_dashboard_action()
                            except Exception as ex:
                                logger.error(f"Error opening dashboard from IPC: {ex}")
                finally:
                    kernel32.CloseHandle(h_event)
            except Exception as e:
                logger.debug(f"IPC listener thread exception: {e}")

        def _ipc_shutdown_loop():
            try:
                import ctypes
                from ctypes import wintypes
                kernel32 = ctypes.windll.kernel32
                kernel32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
                kernel32.CreateEventW.restype = wintypes.HANDLE
                kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                kernel32.WaitForSingleObject.restype = wintypes.DWORD
                kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
                kernel32.CloseHandle.restype = wintypes.BOOL

                h_shutdown = kernel32.CreateEventW(None, False, False, "Local\\PowerMaster_ASUS_Shutdown_Event")
                if not h_shutdown:
                    return
                try:
                    while getattr(self, "_is_running", True):
                        res = kernel32.WaitForSingleObject(h_shutdown, 1000)
                        if res == 0:  # WAIT_OBJECT_0
                            logger.info("Shutdown event signaled via IPC. Cleanly terminating old instance...")
                            try:
                                self._quit_action()
                            except Exception as ex:
                                logger.error(f"Error executing clean shutdown on IPC event: {ex}")
                            break
                finally:
                    kernel32.CloseHandle(h_shutdown)
            except Exception as e:
                logger.debug(f"IPC shutdown listener exception: {e}")

        import threading
        t1 = threading.Thread(target=_ipc_loop, daemon=True, name="PowerMasterIPCShowDashboard")
        t1.start()
        t2 = threading.Thread(target=_ipc_shutdown_loop, daemon=True, name="PowerMasterIPCShutdown")
        t2.start()

    def _prewarm_dashboard(self) -> None:
        def _warm():
            try:
                from dashboard import prewarm_dashboard
                prewarm_dashboard(self, config, self._watcher)
                if self._auto_open_dashboard:
                    self._open_dashboard_action()
            except Exception as e:
                logger.debug(f"Dashboard prewarm failed: {e}")
        import threading
        t = threading.Thread(target=_warm, daemon=True, name="PowerMasterPrewarmDashboard")
        t.start()

    def _start_update_checker(self) -> None:
        import threading
        def _check_loop():
            import time
            time.sleep(15)
            while getattr(self._watcher, "_running", True):
                try:
                    now = time.time()
                    if config.check_updates_daily and (now - config.last_update_check >= 86400):
                        self._check_for_updates_silent()
                except Exception as e:
                    logger.debug(f"Periodic update check error: {e}")
                time.sleep(3600)

        t = threading.Thread(target=_check_loop, daemon=True, name="PowerMasterUpdateCheck")
        t.start()

    def _check_for_updates_silent(self) -> None:
        try:
            import time
            from updater import GitHubPrivateUpdater
            token = config.github_token or os.environ.get("GITHUB_TOKEN") or ""
            updater = GitHubPrivateUpdater(current_version=APP_VERSION, token=token)
            has_update, rel_info, msg = updater.check_for_updates()
            config.last_update_check = time.time()
            if has_update and rel_info:
                self._has_available_update = True
                self._latest_release_info = rel_info
                self.update_icon()
                if self._icon:
                    self._icon.menu = self.build_menu()
                    if config.notify_on_plan_change:
                        self._icon.notify(
                            f"Доступно обновление {rel_info.tag_name}!",
                            title=APP_TITLE,
                        )
        except Exception as e:
            logger.debug(f"Silent update check failed: {e}")

    def _open_updater_action(self) -> None:
        if self._latest_release_info:
            from update_dialog import show_update_dialog
            from updater import GitHubPrivateUpdater
            token = config.github_token or os.environ.get("GITHUB_TOKEN") or ""
            updater = GitHubPrivateUpdater(current_version=APP_VERSION, token=token)
            show_update_dialog(updater, self._latest_release_info, on_complete_callback=self._quit_action)
        else:
            self._check_updates_manual_action()

    def _check_updates_manual_action(self) -> None:
        import threading
        def _do_check():
            from updater import GitHubPrivateUpdater
            token = config.github_token or os.environ.get("GITHUB_TOKEN") or ""
            updater = GitHubPrivateUpdater(current_version=APP_VERSION, token=token)
            has_update, rel_info, msg = updater.check_for_updates()
            if has_update and rel_info:
                self._has_available_update = True
                self._latest_release_info = rel_info
                self.update_icon()
                if self._icon:
                    self._icon.menu = self.build_menu()
                self._open_updater_action()
            else:
                if self._icon:
                    self._icon.notify(msg or "У вас установлена актуальная версия.", title=APP_TITLE)
        threading.Thread(target=_do_check, daemon=True).start()

    def _on_plan_changed(self, new_guid: str, friendly_name: str, reason: str) -> None:
        """Callback invoked by PowerWatcher on plan change."""
        self._current_plan_guid = new_guid
        logger.info(f"Tray update on plan change: {friendly_name} ({reason})")
        self.update_icon()

        if config.notify_on_plan_change and self._icon:
            try:
                self._icon.notify(
                    f"План: {friendly_name}\nТриггер: {reason}",
                    title=f"{APP_TITLE} v{APP_VERSION}",
                )
            except Exception as e:
                logger.debug(f"Failed to show toast notification: {e}")

    def update_icon(self) -> None:
        if not self._icon:
            return
        curr_guid, _ = PowerPlanManager.get_active_plan()
        if curr_guid:
            self._current_plan_guid = curr_guid
        is_ac, _ = PowerWatcher.get_power_status()
        self._is_ac = is_ac
        try:
            new_img = IconGenerator.create_icon_image(
                self._current_plan_guid,
                is_ac,
                style=config.icon_style,
                has_update=self._has_available_update,
            )
            self._icon.icon = new_img

            active_name = PLAN_NAMES.get((self._current_plan_guid or "").lower(), "План")
            mode_tag = " (Ручной)" if self._watcher.has_manual_override else ""
            upd_tag = "\n⚡ Доступно обновление!" if self._has_available_update else ""
            self._icon.title = f"{APP_TITLE}\nПлан: {active_name}{mode_tag}\nСеть: {'AC (220V)' if is_ac else 'Батарея'}{upd_tag}"
        except Exception as e:
            logger.debug(f"Pystray icon/title update suppressed: {e}")

    def _open_dashboard_action(self) -> None:
        logger.info("Opening Dashboard Window from tray (instant in-process show)...")
        try:
            from dashboard import show_dashboard_window
            show_dashboard_window(
                tray_app=self,
                config_obj=config,
                watcher=self._watcher,
            )
        except Exception as e:
            logger.error(f"Error opening dashboard window: {e}")

    def _open_settings_action(self) -> None:
        logger.info("Opening Settings Window from tray...")
        try:
            from settings_dialog import open_settings_window
            open_settings_window(
                config,
                on_save_callback=self._on_settings_saved,
                on_quit_callback=self._quit_action,
            )
        except Exception as e:
            logger.error(f"Error opening settings window: {e}")

    def _on_settings_saved(self, new_data: dict) -> None:
        logger.info("Settings updated via GUI, refreshing tray...")
        self.update_icon()
        if self._icon:
            self._icon.menu = self.build_menu()
        if "battery_charge_limit" in new_data:
            AsusBatteryController.set_charge_limit_elevated(new_data["battery_charge_limit"])
        try:
            from dashboard import DashboardWindow
            if DashboardWindow._instance is not None:
                if "ui_theme" in new_data:
                    DashboardWindow._instance.root.after(0, lambda: DashboardWindow._instance.set_theme(new_data["ui_theme"]))
                if "ui_scale" in new_data:
                    DashboardWindow._instance.root.after(0, lambda: DashboardWindow._instance.set_scale(float(new_data["ui_scale"])))
        except Exception as e:
            logger.debug(f"Error syncing settings to dashboard: {e}")

    # --- Power Plan Handlers ---
    def _is_plan_checked(self, guid: str) -> bool:
        active, _ = PowerPlanManager.get_active_plan()
        return bool(active and active.lower() == guid.lower())

    def _set_plan_action(self, guid: str) -> None:
        logger.info(f"User manually selected power plan: {guid}")
        self._watcher.set_manual_override(guid)
        config.manual_override_guid = guid
        self._current_plan_guid = guid
        self.update_icon()

    def _resume_auto_action(self) -> None:
        self._watcher.clear_manual_override()
        config.manual_override_guid = None
        config.auto_switching_enabled = True
        logger.info("Resumed automatic rules from tray menu.")
        if self._icon and config.notify_on_plan_change:
            self._icon.notify("Авто-режим возобновлен. Динамические правила активны.", title=APP_TITLE)
        self.update_icon()

    # --- Battery Limit Handlers ---
    def _is_limit_checked(self, limit: int) -> bool:
        return config.battery_charge_limit == limit

    def _set_limit_action(self, limit: int) -> None:
        logger.info(f"User requested battery charge limit: {limit}%")
        ok, msg = AsusBatteryController.set_charge_limit_direct(limit)
        if not ok:
            ok, msg = AsusBatteryController.set_charge_limit_elevated(limit)
        if ok:
            config.battery_charge_limit = limit
            config.save()
            try:
                from dashboard import DashboardWindow
                inst = DashboardWindow._instance
                if inst is not None and getattr(inst, "root", None) is not None:
                    inst.root.after_idle(inst._update_battery_label)
            except Exception:
                pass
            if self._icon:
                self._icon.notify(
                    f"Лимит зарядки аккумулятора установлен на {limit}%",
                    title="ASUS Battery Guard",
                )
        else:
            if self._icon:
                self._icon.notify(
                    f"Не удалось установить лимит: {msg}",
                    title="ASUS Battery Guard - Ошибка",
                )

    # --- Icon Style Handlers ---
    def _is_icon_style_checked(self, style_code: str) -> bool:
        cur = str(getattr(config, "icon_style", "style_tile")).lower()
        if style_code == "style_tile" and cur in ("style_tile", "huge_tile", "tile"):
            return True
        return cur == style_code.lower()

    def _set_icon_style_action(self, style_code: str) -> None:
        logger.info(f"User switched icon style to: {style_code}")
        config.icon_style = style_code
        config.save()
        self.update_icon()
        if self._icon:
            self._icon.menu = self.build_menu()

    # --- Tray Menu Text Size Handlers ---
    def _is_tray_menu_size_checked(self, mode: str) -> bool:
        return config.tray_menu_text_size == mode

    def _set_tray_menu_size_action(self, mode: str) -> None:
        logger.info(f"User switched tray menu text size to: {mode}")
        config.tray_menu_text_size = mode
        config.save()
        if self._icon:
            self._icon.menu = self.build_menu()
        if self._icon and config.notify_on_plan_change:
            names = {"standard": "Стандартный", "large": "Крупный", "huge": "Большой"}
            self._icon.notify(f"Размер текста меню: {names.get(mode, mode)}", title=APP_TITLE)

    def _is_ui_theme_checked(self, theme_key: str) -> bool:
        return getattr(config, "ui_theme", "oled_contrast") == theme_key

    def _set_ui_theme_action(self, theme_key: str) -> None:
        logger.info(f"User switched UI theme to: {theme_key}")
        config.set("ui_theme", theme_key)
        try:
            from dashboard import DashboardWindow
            inst = DashboardWindow._instance
            if inst is not None and getattr(inst, "root", None) is not None:
                inst.root.after_idle(lambda: inst.set_theme(theme_key))
        except Exception as e:
            logger.debug(f"Failed to update dashboard theme: {e}")
        if self._icon:
            self._icon.menu = self.build_menu()
        if self._icon and config.notify_on_plan_change:
            names = {
                "oled_contrast": "High-Contrast OLED (Чёрная)",
                "cyber_dark": "TUF Cyber Dark (Тёмная)",
                "clean_minimalist": "Clean Minimalist (Графит)",
                "light": "Светлая",
            }
            self._icon.notify(f"Тема оформления: {names.get(theme_key, theme_key)}", title=APP_TITLE)

    # --- Toggle Handlers ---
    def _is_auto_switching_checked(self) -> bool:
        return config.auto_switching_enabled

    def _toggle_auto_switching(self) -> None:
        new_val = not config.auto_switching_enabled
        config.auto_switching_enabled = new_val
        if new_val:
            self._watcher.clear_manual_override()
            config.manual_override_guid = None
        logger.info(f"Auto-switching toggled to: {new_val}")
        if self._icon and config.notify_on_plan_change:
            status = "ВКЛЮЧЕНО" if new_val else "ПАУЗА (Ручной режим)"
            self._icon.notify(f"Авто-переключение планов: {status}", title=APP_TITLE)
        if self._icon:
            self._icon.menu = self.build_menu()
        self.update_icon()

    def _is_energy_saver_checked(self) -> bool:
        from windows_energy_saver import WindowsEnergySaver
        return WindowsEnergySaver.get_state() == 1

    def _toggle_energy_saver(self) -> None:
        from windows_energy_saver import WindowsEnergySaver
        curr = WindowsEnergySaver.get_state()
        new_val = (curr != 1)
        ok, _ = WindowsEnergySaver.set_state(new_val)
        if ok:
            config.windows_energy_saver_manual = new_val
        logger.info(f"Windows Energy Saver toggled via tray to: {new_val} (ok={ok})")
        if self._icon and config.notify_on_plan_change:
            status = "ВКЛЮЧЕНО" if new_val else "ОТКЛЮЧЕНО"
            self._icon.notify(f"Энергосбережение Windows: {status}", title=APP_TITLE)
        if self._icon:
            self._icon.menu = self.build_menu()
        try:
            from dashboard import DashboardWindow
            inst = DashboardWindow._instance
            if inst is not None and getattr(inst, "root", None) is not None:
                if hasattr(inst, "_update_toggles_ui"):
                    inst.root.after(0, inst._update_toggles_ui)
                elif hasattr(inst, "_update_ui_state"):
                    inst.root.after(0, inst._update_ui_state)
        except Exception:
            pass

    def _is_notifications_checked(self) -> bool:
        return config.notify_on_plan_change

    def _toggle_notifications(self) -> None:
        new_val = not config.notify_on_plan_change
        config.notify_on_plan_change = new_val
        logger.info(f"Notifications toggled to: {new_val}")
        if self._icon:
            # Show single confirmation toast if user explicitly turned notifications ON
            if new_val:
                self._icon.notify("Всплывающие уведомления включены.", title=APP_TITLE)
        self.update_icon()

    def _get_autostart_mode(self) -> str:
        return AutostartManager.get_mode()

    def _toggle_autostart_admin(self) -> None:
        curr = AutostartManager.get_mode()
        new_mode = "none" if curr == "admin" else "admin"
        ok, msg = AutostartManager.set_mode(new_mode)
        if self._icon and config.notify_on_plan_change:
            self._icon.notify(msg, title=APP_TITLE)
        if self._icon:
            self._icon.menu = self.build_menu()

    def _toggle_autostart_user(self) -> None:
        curr = AutostartManager.get_mode()
        new_mode = "none" if curr == "user" else "user"
        ok, msg = AutostartManager.set_mode(new_mode)
        if self._icon and config.notify_on_plan_change:
            self._icon.notify(msg, title=APP_TITLE)
        if self._icon:
            self._icon.menu = self.build_menu()

    def _is_task_scheduler_checked(self) -> bool:
        return AutostartManager.is_task_scheduler_enabled()

    def _toggle_task_scheduler(self) -> None:
        current = AutostartManager.is_task_scheduler_enabled()
        ok, msg = AutostartManager.set_task_scheduler_enabled(not current)
        if self._icon and config.notify_on_plan_change:
            self._icon.notify(msg, title=APP_TITLE)
        if self._icon:
            self._icon.menu = self.build_menu()

    def _is_autostart_checked(self) -> bool:
        return AutostartManager.is_enabled()

    def _toggle_autostart(self) -> None:
        ok, msg = AutostartManager.toggle()
        if self._icon and config.notify_on_plan_change:
            self._icon.notify(msg, title=APP_TITLE)
        if self._icon:
            self._icon.menu = self.build_menu()

    def _restart_as_admin(self) -> None:
        """Relaunches PowerMaster with elevated Administrator privileges."""
        logger.info("Restarting PowerMaster as Administrator via UAC...")

        # Release single instance mutex prior to launching elevated instance
        if self._on_restart_release_mutex:
            try:
                self._on_restart_release_mutex()
            except Exception as e:
                logger.debug(f"Error releasing mutex on restart: {e}")

        try:
            if getattr(sys, "frozen", False):
                ret = ctypes.windll.shell32.ShellExecuteW(
                    None,
                    "runas",
                    sys.executable,
                    "",
                    os.path.dirname(sys.executable),
                    1,  # SW_SHOWNORMAL
                )
            else:
                pythonw_exe = sys.executable
                if "python.exe" in pythonw_exe.lower():
                    py_dir = os.path.dirname(pythonw_exe)
                    candidate = os.path.join(py_dir, "pythonw.exe")
                    if os.path.exists(candidate):
                        pythonw_exe = candidate

                launcher_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
                ret = ctypes.windll.shell32.ShellExecuteW(
                    None,
                    "runas",
                    pythonw_exe,
                    f'"{launcher_path}"',
                    os.path.dirname(launcher_path),
                    1,  # SW_SHOWNORMAL
                )
            try:
                ret_code = int(ret)
            except (ValueError, TypeError):
                ret_code = 42
            if ret_code > 32:
                self._quit_action()
            else:
                logger.warning(f"UAC elevation cancelled or failed (code {ret})")
        except Exception as e:
            logger.error(f"Failed to elevate process: {e}")

    def _quit_action(self) -> None:
        logger.info("Exiting PowerMaster...")
        self._is_running = False
        try:
            from dashboard import close_dashboard_permanently
            close_dashboard_permanently()
        except Exception as e:
            logger.debug(f"Error closing dashboard on quit: {e}")
        self._watcher.stop()
        if self._icon:
            self._icon.visible = False
            self._icon.stop()
        if getattr(self, "_on_restart_release_mutex", None):
            try:
                self._on_restart_release_mutex()
            except Exception:
                pass

    def build_menu(self) -> Menu:
        """Builds the comprehensive tray context menu."""
        admin_status = " (Админ)" if is_admin() else " (Обычные права)"
        menu_size = getattr(config, "tray_menu_text_size", "standard")

        def _fmt(text: str) -> str:
            if menu_size == "huge":
                return f"【 {text} 】"
            elif menu_size == "large":
                return f"  {text}  "
            return text

        items = []
        # Dynamic update notification at very top if available
        if self._has_available_update and self._latest_release_info:
            items.append(
                MenuItem(
                    _fmt(f"🚀 Доступно обновление {self._latest_release_info.tag_name}!"),
                    self._open_updater_action,
                )
            )
            items.append(Menu.SEPARATOR)

        items.extend([
            # Dashboard (Primary LMB action: default=True)
            MenuItem(
                _fmt("📊 Панель управления"),
                self._open_dashboard_action,
                default=True,
            ),
            MenuItem(
                _fmt("⚙️ Настройки..."),
                self._open_settings_action,
            ),
            MenuItem(
                _fmt("🎨 Стиль и размер иконки"),
                Menu(
                    MenuItem(
                        "🔲 Огромная (Сплошная плитка) [100% слота]",
                        lambda: self._set_icon_style_action("style_tile"),
                        checked=lambda item: self._is_icon_style_checked("style_tile"),
                    ),
                    MenuItem(
                        "🚀 Увеличенный силуэт (Скорость)",
                        lambda: self._set_icon_style_action("style_d"),
                        checked=lambda item: self._is_icon_style_checked("style_d"),
                    ),
                    MenuItem(
                        "⚡ Неоновое кольцо с молнией",
                        lambda: self._set_icon_style_action("style_a"),
                        checked=lambda item: self._is_icon_style_checked("style_a"),
                    ),
                    MenuItem(
                        "🔋 Индикатор батареи",
                        lambda: self._set_icon_style_action("style_b"),
                        checked=lambda item: self._is_icon_style_checked("style_b"),
                    ),
                    MenuItem(
                        "🛡️ Щит ASUS TUF",
                        lambda: self._set_icon_style_action("style_c"),
                        checked=lambda item: self._is_icon_style_checked("style_c"),
                    ),
                ),
            ),
            MenuItem(
                _fmt("🔍 Размер текста меню"),
                Menu(
                    MenuItem(
                        "• Стандартный",
                        lambda: self._set_tray_menu_size_action("standard"),
                        checked=lambda item: self._is_tray_menu_size_checked("standard"),
                    ),
                    MenuItem(
                        "• Крупный",
                        lambda: self._set_tray_menu_size_action("large"),
                        checked=lambda item: self._is_tray_menu_size_checked("large"),
                    ),
                    MenuItem(
                        "• Большой",
                        lambda: self._set_tray_menu_size_action("huge"),
                        checked=lambda item: self._is_tray_menu_size_checked("huge"),
                    ),
                ),
            ),
            MenuItem(
                _fmt("🎨 Тема оформления"),
                Menu(
                    MenuItem(
                        "• High-Contrast OLED (Чёрная)",
                        lambda: self._set_ui_theme_action("oled_contrast"),
                        checked=lambda item: self._is_ui_theme_checked("oled_contrast"),
                    ),
                    MenuItem(
                        "• TUF Cyber Dark (Тёмная)",
                        lambda: self._set_ui_theme_action("cyber_dark"),
                        checked=lambda item: self._is_ui_theme_checked("cyber_dark"),
                    ),
                    MenuItem(
                        "• Clean Minimalist (Графит)",
                        lambda: self._set_ui_theme_action("clean_minimalist"),
                        checked=lambda item: self._is_ui_theme_checked("clean_minimalist"),
                    ),
                    MenuItem(
                        "• Светлая",
                        lambda: self._set_ui_theme_action("light"),
                        checked=lambda item: self._is_ui_theme_checked("light"),
                    ),
                ),
            ),
            Menu.SEPARATOR,
            # Status Header
            MenuItem(
                f"{APP_TITLE} v{APP_VERSION}{admin_status}",
                action=None,
                enabled=False,
            ),
            Menu.SEPARATOR,
            # Power Plan Selection (Locked when Auto-switching is active)
            MenuItem(
                lambda item: "Планы питания (Управляется Авто)" if config.auto_switching_enabled else "Планы питания (Ручной выбор)",
                Menu(
                    MenuItem(
                        f"⚡ {PLAN_NAMES[GUID_HIGH_PERFORMANCE]}",
                        lambda: self._set_plan_action(GUID_HIGH_PERFORMANCE),
                        checked=lambda item: self._is_plan_checked(GUID_HIGH_PERFORMANCE),
                        enabled=lambda item: not config.auto_switching_enabled,
                    ),
                    MenuItem(
                        f"⚖️ {PLAN_NAMES[GUID_BALANCED]}",
                        lambda: self._set_plan_action(GUID_BALANCED),
                        checked=lambda item: self._is_plan_checked(GUID_BALANCED),
                        enabled=lambda item: not config.auto_switching_enabled,
                    ),
                    MenuItem(
                        f"🍃 {PLAN_NAMES[GUID_POWER_SAVER]}",
                        lambda: self._set_plan_action(GUID_POWER_SAVER),
                        checked=lambda item: self._is_plan_checked(GUID_POWER_SAVER),
                        enabled=lambda item: not config.auto_switching_enabled,
                    ),
                ),
                enabled=lambda item: not config.auto_switching_enabled,
            ),
            MenuItem(
                "🔄 Возобновить авто-режим",
                self._resume_auto_action,
                visible=lambda item: (not config.auto_switching_enabled) or bool(self._watcher.has_manual_override) or bool(config.manual_override_guid),
            ),
            # ASUS Battery Charge Limit Submenu
            MenuItem(
                "Лимит заряда батареи (ASUS WMI)",
                Menu(
                    MenuItem(
                        "• 80% (Рекомендуемый: баланс долговечности)",
                        lambda: self._set_limit_action(80),
                        checked=lambda item: self._is_limit_checked(80),
                    ),
                    MenuItem(
                        "• 60% (Максимальная защита от износа)",
                        lambda: self._set_limit_action(60),
                        checked=lambda item: self._is_limit_checked(60),
                    ),
                    MenuItem(
                        "• 100% (Полная емкость)",
                        lambda: self._set_limit_action(100),
                        checked=lambda item: self._is_limit_checked(100),
                    ),
                ),
            ),
            Menu.SEPARATOR,
            # Automation Toggles
            MenuItem(
                "Авто-переключение планов",
                self._toggle_auto_switching,
                checked=lambda item: self._is_auto_switching_checked(),
            ),
            MenuItem(
                "🍃 Энергосбережение Windows",
                self._toggle_energy_saver,
                checked=lambda item: self._is_energy_saver_checked(),
            ),
            MenuItem(
                "🔔 Всплывающие уведомления",
                self._toggle_notifications,
                checked=lambda item: self._is_notifications_checked(),
            ),
            MenuItem(
                "🛡️ Автозапуск: От имени Администратора (без UAC)",
                self._toggle_autostart_admin,
                checked=lambda item: self._get_autostart_mode() == "admin",
            ),
            MenuItem(
                "👤 Автозапуск: Обычный (без прав Администратора)",
                self._toggle_autostart_user,
                checked=lambda item: self._get_autostart_mode() == "user",
            ),
            Menu.SEPARATOR,
            MenuItem("🔍 Проверить обновления...", self._check_updates_manual_action),
            # Administrator Elevation & Status Section
            *(
                [
                    MenuItem(
                        "🛡️ Запущен с правами Администратора",
                        action=None,
                        enabled=False,
                    ),
                    MenuItem(
                        "🔄 Перезапустить программу",
                        self._restart_as_admin,
                    ),
                ]
                if is_admin()
                else [
                    MenuItem(
                        "🛡️ Перезапустить с правами Администратора",
                        self._restart_as_admin,
                    ),
                ]
            ),
            MenuItem("Выход", self._quit_action),
        ])

        return Menu(*items)

    def _dismiss_tk_tray_menu(self) -> None:
        menu = getattr(self, "_active_tk_menu", None)
        self._active_tk_menu = None
        if menu is not None:
            for act in (menu.unpost, menu.destroy):
                try:
                    act()
                except Exception:
                    pass
        anchor = getattr(self, "_tk_menu_anchor", None)
        if anchor is not None:
            try:
                anchor.withdraw()
            except Exception:
                pass

    def _show_tk_tray_menu(self) -> bool:
        try:
            from dashboard import DashboardWindow
            inst = DashboardWindow._instance
            if inst is None or getattr(inst, "root", None) is None:
                return False

            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            x, y = int(pt.x), int(pt.y)
            inst.root.after_idle(lambda: self._popup_tk_menu_on_gui(inst.root, x, y))
            return True
        except Exception as e:
            logger.debug(f"Failed to show Tk tray menu: {e}")
            return False

    def _popup_tk_menu_on_gui(self, root, x, y):
        self._dismiss_tk_tray_menu()

        anchor = getattr(self, "_tk_menu_anchor", None)
        try:
            if anchor is None or not anchor.winfo_exists():
                anchor = tk.Toplevel(root)
                anchor.overrideredirect(True)
                anchor.attributes("-topmost", True)
                anchor.attributes("-alpha", 0.01)
                anchor.bind("<FocusOut>", lambda e: root.after(50, self._dismiss_tk_tray_menu))
                anchor.bind("<Escape>", lambda e: self._dismiss_tk_tray_menu())
                self._tk_menu_anchor = anchor
            anchor.geometry(f"1x1+{x}+{y}")
            anchor.deiconify()
            anchor.lift()
            anchor.update_idletasks()
        except Exception:
            anchor = root

        size_mode = getattr(config, "tray_menu_text_size", "standard")
        if size_mode == "huge":
            font_main = ("Segoe UI", 15, "bold")
            font_sub = ("Segoe UI", 14, "bold")
        elif size_mode == "large":
            font_main = ("Segoe UI", 12, "bold")
            font_sub = ("Segoe UI", 11, "bold")
        else:
            font_main = ("Segoe UI", 10, "bold")
            font_sub = ("Segoe UI", 10)

        t_key = getattr(config, "ui_theme", "oled_contrast")
        from dashboard import THEMES
        t = THEMES.get(t_key, THEMES.get("oled_contrast", THEMES["cyber_dark"]))
        bg_col = t.get("bg_card", "#0c0c0c")
        fg_col = t.get("fg_main", "#ffffff")
        active_bg = t.get("btn_accent_bg", "#00ffff")
        active_fg = t.get("btn_accent_fg", "#000000")

        menu = tk.Menu(
            anchor,
            tearoff=0,
            font=font_main,
            bg=bg_col,
            fg=fg_col,
            activebackground=active_bg,
            activeforeground=active_fg,
            relief="flat",
            bd=1,
        )
        self._active_tk_menu = menu

        def make_sub():
            return tk.Menu(
                menu,
                tearoff=0,
                font=font_sub,
                bg=bg_col,
                fg=fg_col,
                activebackground=active_bg,
                activeforeground=active_fg,
                relief="flat",
                bd=1,
            )

        if self._has_available_update and self._latest_release_info:
            menu.add_command(
                label=f"🚀 Доступно обновление {self._latest_release_info.tag_name}!",
                command=self._open_updater_action,
            )
            menu.add_separator()

        menu.add_command(label="📊 Панель управления", command=self._open_dashboard_action)
        menu.add_command(label="⚙️ Настройки...", command=self._open_settings_action)

        style_sub = make_sub()
        for code, label in [
            ("style_tile", "🔲 Огромная (Сплошная плитка)"),
            ("style_d", "🚀 Увеличенный силуэт (Скорость)"),
            ("style_a", "⚡ Неоновое кольцо с молнией"),
            ("style_b", "🔋 Индикатор батареи"),
            ("style_c", "🛡️ Щит ASUS TUF"),
        ]:
            checked = self._is_icon_style_checked(code)
            prefix = "✓ " if checked else "   "
            style_sub.add_command(
                label=f"{prefix}{label}",
                command=lambda c=code: self._set_icon_style_action(c),
            )
        menu.add_cascade(label="🎨 Стиль и размер иконки", menu=style_sub)

        size_sub = make_sub()
        for mode_key, mode_label in [
            ("standard", "Стандартный"),
            ("large", "Крупный"),
            ("huge", "Большой"),
        ]:
            checked = (size_mode == mode_key)
            prefix = "✓ " if checked else "   "
            size_sub.add_command(
                label=f"{prefix}{mode_label}",
                command=lambda m=mode_key: self._set_tray_menu_size_action(m),
            )
        menu.add_cascade(label="🔍 Размер текста меню", menu=size_sub)

        theme_sub = make_sub()
        current_theme = getattr(config, "ui_theme", "oled_contrast")
        for th_key, th_label in [
            ("oled_contrast", "🖤 High-Contrast OLED (Чёрная)"),
            ("cyber_dark", "🌌 TUF Cyber Dark (Тёмная)"),
            ("clean_minimalist", "🌑 Clean Minimalist (Графит)"),
            ("light", "☀️ Светлая"),
        ]:
            checked = (current_theme == th_key)
            prefix = "✓ " if checked else "   "
            theme_sub.add_command(
                label=f"{prefix}{th_label}",
                command=lambda k=th_key: self._set_ui_theme_action(k),
            )
        menu.add_cascade(label="🎨 Тема оформления", menu=theme_sub)

        menu.add_separator()

        admin_status = " (Админ)" if is_admin() else " (Обычные права)"
        menu.add_command(
            label=f"{APP_TITLE} v{APP_VERSION}{admin_status}",
            state=tk.DISABLED,
        )

        menu.add_separator()

        plan_sub = make_sub()
        for guid, name, emoji in [
            (GUID_HIGH_PERFORMANCE, PLAN_NAMES.get(GUID_HIGH_PERFORMANCE, "Высокая"), "⚡"),
            (GUID_BALANCED, PLAN_NAMES.get(GUID_BALANCED, "Баланс"), "⚖️"),
            (GUID_POWER_SAVER, PLAN_NAMES.get(GUID_POWER_SAVER, "Эко"), "🍃"),
        ]:
            checked = self._is_plan_checked(guid)
            prefix = "✓ " if checked else "   "
            plan_sub.add_command(
                label=f"{prefix}{emoji} {name}",
                command=lambda g=guid: self._set_plan_action(g),
            )
        plan_sub.add_separator()
        plan_sub.add_command(label="⚡ Возобновить авторежим", command=self._resume_auto_action)
        plan_label = "Планы питания (Авто)" if config.auto_switching_enabled else "Планы питания (Ручной)"
        menu.add_cascade(label=f"⚡ {plan_label}", menu=plan_sub)

        bat_sub = make_sub()
        for lim, desc in [
            (60, "60% (Максимальная защита)"),
            (80, "80% (Рекомендуемый баланс)"),
            (100, "100% (Полная емкость)"),
        ]:
            checked = self._is_limit_checked(lim)
            prefix = "✓ " if checked else "   "
            bat_sub.add_command(
                label=f"{prefix}{desc}",
                command=lambda l=lim: self._set_limit_action(l),
            )
        menu.add_cascade(label="🔋 Лимит заряда батареи", menu=bat_sub)

        as_on = bool(config.auto_switching_enabled)
        menu.add_command(
            label=f"{'✓ ' if as_on else '   '}Авто-переключение планов",
            command=self._toggle_auto_switching,
        )

        es_on = self._is_energy_saver_checked()
        menu.add_command(
            label=f"{'✓ ' if es_on else '   '}🍃 Энергосбережение Windows",
            command=self._toggle_energy_saver,
        )

        notif_on = bool(config.notify_on_plan_change)
        menu.add_command(
            label=f"{'✓ ' if notif_on else '   '}🔔 Всплывающие уведомления",
            command=self._toggle_notifications,
        )

        auto_sub = make_sub()
        auto_mode = AutostartManager.get_mode()
        auto_sub.add_command(
            label=f"{'✓ ' if auto_mode == 'admin' else '   '}🛡️ От имени Администратора (без UAC)",
            command=self._toggle_autostart_admin,
        )
        auto_sub.add_command(
            label=f"{'✓ ' if auto_mode == 'user' else '   '}👤 Обычный запуск (без прав Администратора)",
            command=self._toggle_autostart_user,
        )
        menu.add_cascade(label="🚀 Автозагрузка", menu=auto_sub)

        menu.add_separator()
        menu.add_command(label="🔍 Проверить обновления...", command=self._check_updates_manual_action)

        if not is_admin():
            menu.add_command(
                label="🛡️ Перезапустить с правами Администратора",
                command=self._restart_as_admin,
            )
        else:
            menu.add_command(
                label="🔄 Перезапустить программу",
                command=self._restart_as_admin,
            )

        menu.add_separator()
        menu.add_command(label="Выход", command=self._quit_action)

        import ctypes
        user32 = ctypes.windll.user32
        hwnd = 0
        try:
            hwnd = anchor.winfo_id()
            user32.SetForegroundWindow(hwnd)
            anchor.focus_force()
        except Exception:
            pass

        def _on_menu_unmap(event=None):
            if hwnd:
                try:
                    user32.PostMessageW(hwnd, 0x0000, 0, 0)  # WM_NULL per Microsoft KB135788
                except Exception:
                    pass
            root.after(100, self._dismiss_tk_tray_menu)

        menu.bind("<Unmap>", _on_menu_unmap)
        menu.bind("<Escape>", lambda e: self._dismiss_tk_tray_menu())
        try:
            menu.tk_popup(x, y)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass
        return menu

    def run(self) -> None:
        """Starts the PowerWatcher and enters the pystray main loop."""
        logger.info(f"Starting {APP_TITLE} System Tray App...")

        # Ensure latest active plan and power status are verified before building initial UI
        try:
            curr_guid, _ = PowerPlanManager.get_active_plan()
            if curr_guid:
                self._current_plan_guid = curr_guid
            p_stat = PowerWatcher.get_power_status()
            if isinstance(p_stat, (tuple, list)) and len(p_stat) >= 1:
                self._is_ac = bool(p_stat[0])
        except Exception as ex:
            logger.debug(f"Tray run status check suppressed: {ex}")

        # Build initial icon with configured icon style and verified power state
        init_img = IconGenerator.create_icon_image(
            self._current_plan_guid,
            self._is_ac,
            style=config.icon_style,
            has_update=self._has_available_update,
        )
        active_name = PLAN_NAMES.get((self._current_plan_guid or "").lower(), "План")
        mode_tag = " (Ручной)" if self._watcher.has_manual_override else ""
        upd_tag = "\n⚡ Доступно обновление!" if self._has_available_update else ""

        self._icon = pystray.Icon(
            name=APP_NAME,
            icon=init_img,
            title=f"{APP_TITLE}\nПлан: {active_name}{mode_tag}\nСеть: {'AC (220V)' if self._is_ac else 'Батарея'}{upd_tag}",
            menu=self.build_menu(),
        )

        # Start background power watcher after initial icon alignment
        self._watcher.start()

        def on_tray_ready(icon):
            logger.info("Pystray message loop active, forcing icon.visible = True")
            icon.visible = True

            # Hook right click to support scalable font popup menu for visually impaired users
            try:
                from pystray._util import win32 as _pystray_w32
                tray_notify_msg = getattr(_pystray_w32, "WM_NOTIFY", 1035)
            except Exception:
                tray_notify_msg = 1035

            if hasattr(icon, "_message_handlers") and isinstance(icon._message_handlers, dict):
                target_keys = {tray_notify_msg}
                for k, fn in list(icon._message_handlers.items()):
                    if getattr(fn, "__name__", "") == "_on_notify":
                        target_keys.add(k)
                for msg_key in target_keys:
                    orig_handler = icon._message_handlers.get(msg_key, getattr(icon, "_on_notify", None))
                    def custom_on_notify(wparam, lparam, _orig=orig_handler):
                        # WM_RBUTTONUP = 0x0205 = 517, WM_CONTEXTMENU = 0x007B = 123
                        if lparam in (517, 123):
                            if self._show_tk_tray_menu():
                                return 0
                        elif lparam == 516:  # WM_RBUTTONDOWN = 0x0204 = 516
                            return 0
                        if _orig is not None:
                            return _orig(wparam, lparam)
                        return 0
                    icon._message_handlers[msg_key] = custom_on_notify

        try:
            # Blocking call: runs tray message loop
            self._icon.run(setup=on_tray_ready)
        except KeyboardInterrupt:
            self._quit_action()
        finally:
            self._watcher.stop()
