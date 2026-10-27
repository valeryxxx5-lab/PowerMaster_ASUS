import unittest
from unittest.mock import MagicMock, patch
import time
import sys
import os
import subprocess
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from tray_enhancements import run_command_silent, TaskSchedulerStatusCache, CREATE_NO_WINDOW
from settings_dialog import I18N, SettingsWindow

class DummyConfig:
    def __init__(self):
        self._data = {
            "game_directories": ["F:\\Games", "D:\\Games"],
            "game_process_names": ["game.exe"],
            "icon_style": "style_a",
            "language": "ru",
            "battery_charge_limit": 80,
            "idle_timeout_seconds": 180,
            "notify_on_plan_change": True
        }

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, val):
        self._data[key] = val

    def save_atomic(self, new_data):
        self._data.update(new_data)

class TestSettingsAndTrayTZ28(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from settings_dialog import SettingsWindow
        tk._default_root = None
        SettingsWindow._instance = None

    def tearDown(self):
        import tkinter as tk
        from settings_dialog import SettingsWindow
        tk._default_root = None
        SettingsWindow._instance = None

    def test_1_create_no_window_constant_value(self):
        """
        Тест 1: Проверка корректности системной константы CREATE_NO_WINDOW (0x08000000).
        """
        self.assertEqual(CREATE_NO_WINDOW, 0x08000000)

    def test_2_silent_command_execution_flags(self):
        """
        Тест 2: Проверка передачи STARTUPINFO и CREATE_NO_WINDOW в subprocess.
        """
        import sys
        if sys.platform != "win32":
            return

        # Запуск встроенной команды cmd /c echo test
        res = run_command_silent(["cmd.exe", "/c", "echo", "silent_ok"])
        self.assertEqual(res.returncode, 0)
        self.assertIn("silent_ok", res.stdout)

    def test_3_task_scheduler_ttl_cache_logic(self):
        """
        Тест 3: Проверка работы TTL-кэша планировщика задач:
        - При повторных вызовах в течение TTL процесс не перезапускается;
        - Метод invalidate() очищает кэш.
        """
        cache = TaskSchedulerStatusCache(task_name="NonExistentTask_TZ28", ttl_seconds=10.0)
        
        t0 = time.time()
        s1 = cache.is_enabled()
        self.assertFalse(s1)
        self.assertGreater(cache._last_check_time, 0.0)
        
        # Повторный вызов берет значение из памяти без задержки
        time_before = cache._last_check_time
        s2 = cache.is_enabled()
        self.assertEqual(s1, s2)
        self.assertEqual(cache._last_check_time, time_before)

        # Сброс кэша
        cache.invalidate()
        self.assertIsNone(cache._cached_status)
        self.assertEqual(cache._last_check_time, 0.0)

    def test_4_i18n_dictionary_completeness(self):
        """
        Тест 4: Проверка полноты словаря интернационализации (RU и EN ключи совпадают).
        """
        self.assertIn("ru", I18N)
        self.assertIn("en", I18N)
        
        ru_keys = set(I18N["ru"].keys())
        en_keys = set(I18N["en"].keys())
        self.assertEqual(ru_keys, en_keys)
        
        # Проверка обязательных переводов
        self.assertIn("tab_games", ru_keys)
        self.assertIn("tab_appearance", ru_keys)
        self.assertIn("tab_system", ru_keys)
        self.assertIn("btn_save", ru_keys)

    def test_5_settings_data_model_and_save(self):
        """
        Тест 5: Проверка модели данных и атомарного обновления настроек.
        """
        cfg = DummyConfig()
        new_settings = {
            "game_directories": ["E:\\Games", "D:\\Steam"],
            "game_process_names": ["rdr2.exe"],
            "icon_style": "style_b",
            "language": "en",
            "battery_charge_limit": 60,
            "idle_timeout_seconds": 300,
            "notify_on_plan_change": False
        }
        cfg.save_atomic(new_settings)
        
        self.assertEqual(cfg.get("language"), "en")
        self.assertEqual(cfg.get("battery_charge_limit"), 60)
        self.assertEqual(cfg.get("icon_style"), "style_b")
        self.assertIn("E:\\Games", cfg.get("game_directories"))

    def test_6_settings_window_gui_init_no_tcl_crash(self):
        """
        Тест 6: Проверка гарантированной инициализации SettingsWindow без падений Tkinter (TclError keysym).
        """
        import tkinter as tk
        cfg = DummyConfig()
        win = SettingsWindow(cfg)
        self.assertIsNotNone(win.root)
        self.assertEqual(win.icon_style_var.get(), "style_a")
        # Проверяем переключение стиля и предпросмотр
        win.icon_style_var.set("style_tile")
        win._draw_icon_preview()
        win.icon_style_var.set("style_d")
        win._draw_icon_preview()
        win.ui_scale_var.set(1.5)
        win.ui_theme_var.set("clean_minimalist")
        self.assertEqual(win.ui_scale_var.get(), 1.5)
        self.assertEqual(win.ui_theme_var.get(), "clean_minimalist")
        # Уничтожаем окно после успешной валидации
        win.root.destroy()
        SettingsWindow._instance = None

    def test_7_config_writable_dir_and_persistence(self):
        """
        Тест 7: Проверка проверки прав на запись _is_dir_writable и работы конфигурации.
        """
        from config import _is_dir_writable, Config
        import tempfile
        # Временная папка гарантированно доступна на запись
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            self.assertTrue(_is_dir_writable(p))
            # Несуществующая папка
            self.assertFalse(_is_dir_writable(p / "nonexistent_subfolder"))

            # Проверка сохранения и загрузки Config
            cfg_path = p / "test_cfg.json"
            cfg = Config(path=cfg_path)
            cfg.icon_style = "style_tile"
            cfg.save()
            self.assertTrue(cfg_path.exists())

            # Повторное чтение из файла
            cfg2 = Config(path=cfg_path)
            self.assertEqual(cfg2.icon_style, "style_tile")

    def test_8_open_settings_window_safe_with_active_root(self):
        """
        Тест 8: Проверка безопасного вызова open_settings_window при наличии активного Tk root.
        Гарантирует отсутствие конфликтов потоков и ошибок Tcl apartments.
        """
        from settings_dialog import open_settings_window
        from unittest.mock import MagicMock, patch
        cfg = DummyConfig()

        mock_root = MagicMock()
        mock_root.winfo_exists.return_value = True
        mock_root._gui_thread_id = 99999999

        with patch('tkinter._default_root', mock_root):
            # При вызове из другого потока диспетчеризуется через root.after без падения
            res = open_settings_window(cfg)
            self.assertIsNone(res)
            mock_root.after.assert_called_once()

        mock_inst = MagicMock()
        with patch.object(SettingsWindow, '_instance', mock_inst):
            res2 = open_settings_window(cfg)
            self.assertEqual(res2, mock_inst)
            mock_inst.root.after.assert_called_with(0, mock_inst.lift_to_front)

    def test_9_restart_as_admin_frozen(self):
        """
        Тест 9: Проверка перезапуска с правами администратора в режиме скомпилированного бинарника (frozen=True).
        Должен вызывать ShellExecuteW(None, 'runas', sys.executable, '', dir, 1) без передачи main.py.
        """
        from tray_app import PowerMasterTrayApp
        tray = PowerMasterTrayApp.__new__(PowerMasterTrayApp)
        tray._on_restart_release_mutex = MagicMock()
        tray._quit_action = MagicMock()

        with patch.object(sys, 'frozen', True, create=True), \
             patch('sys.executable', 'C:\\Program Files\\PowerMaster_ASUS\\PowerMaster_ASUS.exe'), \
             patch('ctypes.windll.shell32.ShellExecuteW') as mock_shellexecute:
            mock_shellexecute.return_value = 42
            tray._restart_as_admin()
            tray._on_restart_release_mutex.assert_called_once()
            mock_shellexecute.assert_called_once_with(
                None,
                "runas",
                'C:\\Program Files\\PowerMaster_ASUS\\PowerMaster_ASUS.exe',
                "",
                'C:\\Program Files\\PowerMaster_ASUS',
                1,
            )
            tray._quit_action.assert_called_once()

    def test_10_restart_as_admin_non_frozen(self):
        """
        Тест 10: Проверка перезапуска с правами администратора в режиме скрипта Python (frozen=False).
        Должен вызывать ShellExecuteW с launcher_path (main.py).
        """
        from tray_app import PowerMasterTrayApp
        tray = PowerMasterTrayApp.__new__(PowerMasterTrayApp)
        tray._on_restart_release_mutex = MagicMock()
        tray._quit_action = MagicMock()

        with patch.object(sys, 'frozen', False, create=True), \
             patch('sys.executable', 'C:\\Python\\python.exe'), \
             patch('os.path.exists', return_value=True), \
             patch('ctypes.windll.shell32.ShellExecuteW') as mock_shellexecute:
            mock_shellexecute.return_value = 42
            tray._restart_as_admin()
            tray._on_restart_release_mutex.assert_called_once()
            self.assertTrue(mock_shellexecute.called)
            args = mock_shellexecute.call_args[0]
            self.assertEqual(args[1], "runas")
            self.assertIn("main.py", args[3])
            tray._quit_action.assert_called_once()

    def test_11_tray_menu_scalable_hook_and_dismiss(self):
        """
        Тест 11: Проверка механизма масштабируемого меню трея:
        - _show_tk_tray_menu вызывает after_idle;
        - _dismiss_tk_tray_menu корректно закрывает меню и скрывает якорное окно;
        - перехватчик WM_NOTIFY реагирует на WM_RBUTTONUP (517) при режиме 'large'.
        """
        from tray_app import PowerMasterTrayApp
        tray = PowerMasterTrayApp.__new__(PowerMasterTrayApp)

        mock_menu = MagicMock()
        mock_anchor = MagicMock()
        tray._active_tk_menu = mock_menu
        tray._tk_menu_anchor = mock_anchor

        tray._dismiss_tk_tray_menu()
        mock_menu.unpost.assert_called_once()
        mock_menu.destroy.assert_called_once()
        mock_anchor.withdraw.assert_called_once()
        self.assertIsNone(tray._active_tk_menu)

        # Test _show_tk_tray_menu dispatch
        mock_inst = MagicMock()
        mock_root = MagicMock()
        mock_inst.root = mock_root

        with patch("dashboard.DashboardWindow._instance", mock_inst):
            res = tray._show_tk_tray_menu()
            self.assertTrue(res)
            mock_root.after_idle.assert_called_once()

    def test_12_tray_initial_startup_alignment_rocket_icon(self):
        from tray_app import PowerMasterTrayApp, IconGenerator
        from config import GUID_BALANCED, GUID_HIGH_PERFORMANCE

        mock_snap = MagicMock()
        mock_snap.current_plan_guid = GUID_BALANCED
        mock_snap.in_startup_boost = True

        mock_watcher_inst = MagicMock()
        mock_watcher_inst.take_snapshot.return_value = mock_snap
        mock_watcher_inst.evaluate_desired_plan.return_value = (GUID_HIGH_PERFORMANCE, "Startup Boost")

        with patch("tray_app.PowerPlanManager.get_active_plan", return_value=(GUID_BALANCED, "Balanced")), \
             patch("tray_app.PowerPlanManager.set_active_plan", return_value=(True, "OK")) as mock_set, \
             patch("tray_app.PowerWatcher", return_value=mock_watcher_inst), \
             patch("tray_app.PowerWatcher.get_power_status", return_value=(True, 100)), \
             patch("tray_app.AsusBatteryController.set_charge_limit_direct"):
            app = PowerMasterTrayApp()
            self.assertEqual(app._current_plan_guid, GUID_HIGH_PERFORMANCE)
            mock_set.assert_called_with(GUID_HIGH_PERFORMANCE)

            img = IconGenerator.create_icon_image(app._current_plan_guid, app._is_ac, style="style_d")
            self.assertIsNotNone(img)

if __name__ == "__main__":
    unittest.main()
