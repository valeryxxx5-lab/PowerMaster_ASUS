import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import tkinter as tk

from config import Config

# Mock tk.Tk before importing dashboard
class MockTk:
    def __init__(self, *args, **kwargs):
        self.tk = MagicMock()
        self.title = MagicMock()
        self.geometry = MagicMock()
        self.resizable = MagicMock()
        self.configure = MagicMock()
        self.protocol = MagicMock()
        self.winfo_screenwidth = MagicMock(return_value=1920)
        self.winfo_screenheight = MagicMock(return_value=1080)
        self.winfo_reqwidth = MagicMock(return_value=0)
        self.winfo_reqheight = MagicMock(return_value=0)
        self.update_idletasks = MagicMock()
        self.destroy = MagicMock()
        self.after = MagicMock(return_value="timer_id")
        self.after_cancel = MagicMock()
        self.withdraw = MagicMock()
        self.deiconify = MagicMock()
        self.lift = MagicMock()
        self.focus_force = MagicMock()
        self.attributes = MagicMock()
        self.minsize = MagicMock()

    def _root(self):
        return self

class MockFrame:
    def __init__(self, *args, **kwargs):
        self.tk = MagicMock()
        self._w = "mock_frame"
    def pack(self, *args, **kwargs): pass
    def pack_forget(self, *args, **kwargs): pass
    def grid(self, *args, **kwargs): pass
    def columnconfigure(self, *args, **kwargs): pass
    def rowconfigure(self, *args, **kwargs): pass
    def grid_columnconfigure(self, *args, **kwargs): pass
    def grid_rowconfigure(self, *args, **kwargs): pass

class MockLabel:
    def __init__(self, *args, **kwargs):
        self.config = MagicMock()
        self.configure = MagicMock()
    def pack(self, *args, **kwargs): pass
    def pack_forget(self, *args, **kwargs): pass
    def grid(self, *args, **kwargs): pass
    def bind(self, *args, **kwargs): pass

class MockButton:
    def __init__(self, *args, **kwargs):
        self.config = MagicMock()
        self.configure = MagicMock()
        self.cget = MagicMock(return_value="")
    def pack(self, *args, **kwargs): pass
    def pack_forget(self, *args, **kwargs): pass
    def grid(self, *args, **kwargs): pass

class MockCheckbutton:
    def __init__(self, *args, **kwargs):
        self.config = MagicMock()
        self.configure = MagicMock()
    def pack(self, *args, **kwargs): pass
    def pack_forget(self, *args, **kwargs): pass
    def grid(self, *args, **kwargs): pass

class MockStyle:
    def __init__(self, *args, **kwargs): pass
    def theme_use(self, *args, **kwargs): pass
    def configure(self, *args, **kwargs): pass
    def map(self, *args, **kwargs): pass

from dashboard import DashboardWindow, show_dashboard_window
import dashboard

class TestDashboard(unittest.TestCase):
    def setUp(self):
        tk._default_root = None
        self.patcher_tk = patch('tkinter.Tk', new=MockTk)
        self.patcher_frame = patch('tkinter.ttk.Frame', new=MockFrame)
        self.patcher_label = patch('tkinter.ttk.Label', new=MockLabel)
        self.patcher_button = patch('tkinter.ttk.Button', new=MockButton)
        self.patcher_checkbutton = patch('tkinter.ttk.Checkbutton', new=MockCheckbutton)
        self.patcher_tk_label = patch('tkinter.Label', new=MockLabel)
        self.patcher_tk_button = patch('tkinter.Button', new=MockButton)
        self.patcher_style = patch('tkinter.ttk.Style', new=MockStyle)

        self.patcher_tk.start()
        self.patcher_frame.start()
        self.patcher_label.start()
        self.patcher_button.start()
        self.patcher_checkbutton.start()
        self.patcher_tk_label.start()
        self.patcher_tk_button.start()
        self.patcher_style.start()

        DashboardWindow._instance = None
        self.tmp_cfg_file = tempfile.NamedTemporaryFile("w", delete=False, suffix=".json", encoding="utf-8")
        json.dump({"battery_charge_limit": 80, "ui_scale": 1.0, "ui_theme": "cyber_dark"}, self.tmp_cfg_file)
        self.tmp_cfg_file.close()
        self.config = Config(path=Path(self.tmp_cfg_file.name), stat_interval=9999.0)
        self.config.battery_charge_limit = 80
        self.config.charge_limit = 80
        self.tray_app = MagicMock()
        self.watcher = MagicMock()

    def tearDown(self):
        if DashboardWindow._instance:
            try:
                DashboardWindow._instance.is_standalone = False
                DashboardWindow._instance._on_close()
            except SystemExit:
                pass
        DashboardWindow._instance = None
        if hasattr(self, "tmp_cfg_file") and os.path.exists(self.tmp_cfg_file.name):
            try:
                os.unlink(self.tmp_cfg_file.name)
            except Exception:
                pass
        if hasattr(dashboard, "config") and dashboard.config:
            dashboard.config.manual_override_guid = None
            dashboard.config.battery_charge_limit = 60
            if hasattr(dashboard.config, "_data") and "test_key_audit" in dashboard.config._data:
                del dashboard.config._data["test_key_audit"]
            dashboard.config.save()
        self.patcher_tk.stop()
        self.patcher_frame.stop()
        self.patcher_label.stop()
        self.patcher_button.stop()
        self.patcher_checkbutton.stop()
        self.patcher_tk_label.stop()
        self.patcher_tk_button.stop()
        self.patcher_style.stop()
        tk._default_root = None

    def test_singleton_instance(self):
        win1 = DashboardWindow(self.tray_app, self.config, self.watcher)
        self.assertIsNotNone(DashboardWindow._instance)
        self.assertEqual(DashboardWindow._instance, win1)

        # Test show_dashboard_window returns existing instance
        result = show_dashboard_window(self.tray_app, self.config, self.watcher)
        self.assertEqual(result, win1)
        win1.root.after.assert_called_with(0, win1.lift_to_front)

    @patch('psutil.cpu_percent', return_value=45.6)
    @patch('psutil.cpu_freq')
    @patch('psutil.sensors_battery')
    def test_telemetry_formatting(self, mock_battery, mock_freq, mock_cpu_percent):
        mock_freq_obj = MagicMock()
        mock_freq_obj.current = 3200.0
        mock_freq.return_value = mock_freq_obj

        mock_batt_obj = MagicMock()
        mock_batt_obj.percent = 85
        mock_batt_obj.power_plugged = True
        mock_battery.return_value = mock_batt_obj

        mock_cpu = MagicMock()
        mock_cpu.get_frequency_ghz.return_value = 3.20
        mock_cpu.get_temperature_c.return_value = 75.0
        mock_cpu.get_fan_rpm.return_value = 4500

        mock_gpu = MagicMock()
        mock_gpu.get_utilization_pct.return_value = 82
        mock_gpu.get_clock_mhz.return_value = 1500
        mock_gpu.get_temperature_c.return_value = 68
        mock_gpu.get_fan_rpm.return_value = 3200

        win = DashboardWindow(self.tray_app, self.config, self.watcher, cpu_telemetry=mock_cpu, gpu_telemetry=mock_gpu)
        win.cpu_pct_lbl = MagicMock()
        win.cpu_freq_lbl = MagicMock()
        win.cpu_temp_lbl = MagicMock()

        win.gpu_pct_lbl = MagicMock()
        win.gpu_freq_lbl = MagicMock()
        win.gpu_temp_lbl = MagicMock()

        win.battery_lbl = MagicMock()

        win._poll_telemetry()

        win.cpu_pct_lbl.config.assert_called_with(text="45.6 %")
        win.cpu_freq_lbl.config.assert_called_with(text="3.20 GHz")
        win.cpu_temp_lbl.config.assert_called_with(text="75 °C")

        win.gpu_pct_lbl.config.assert_called_with(text="82 %")
        win.gpu_freq_lbl.config.assert_called_with(text="1500 MHz")
        win.gpu_temp_lbl.config.assert_called_with(text="68 °C")

        win.battery_lbl.config.assert_called_with(text="🔌 85% (Лимит: 80% • не заряжается)")

        mock_batt_obj.power_plugged = False
        win._poll_telemetry()
        win.battery_lbl.config.assert_called_with(text="🔋 85% (Лимит: 80%)")

    @patch('dashboard.ctypes.WinDLL', create=True)
    def test_gpu_telemetry_nvml_fallback(self, mock_windll):
        mock_windll.side_effect = Exception("nvml.dll not found")
        from dashboard import GpuTelemetry
        gpu = GpuTelemetry()
        self.assertFalse(gpu._initialized)
        self.assertIsNone(gpu.get_utilization_pct())
        self.assertIsNone(gpu.get_clock_mhz())
        self.assertIsNone(gpu.get_temperature_c())
        # Fan might still try WMI, which could return None if mocked appropriately (already none by default if WMI fails)

    @patch('power_plan.PowerPlanManager')
    def test_ui_update_state(self, mock_ppm_class):
        mock_ppm = MagicMock()
        mock_ppm.get_active_plan.return_value = (dashboard.GUID_HIGH_PERFORMANCE, "High Performance")
        mock_ppm_class.return_value = mock_ppm

        self.config.auto_switching_enabled = True
        self.watcher.has_manual_override = False
        self.tray_app._watcher = self.watcher

        win = DashboardWindow(self.tray_app, self.config, self.watcher)

        # Test default auto state High Performance
        win._update_ui_state()
        win.active_mode_lbl.config.assert_called_with(text="⚡ Высокая производительность", foreground="#f38ba8")
        win.fan_lbl.config.assert_called_with(text="Турбо / Максимум")
        win.auto_status_lbl.config.assert_called_with(text="Управляется автоматически (FSM)", foreground="#a6e3a1")

        # Test manual override state Balanced
        mock_ppm.get_active_plan.return_value = (dashboard.GUID_BALANCED, "Balanced")
        self.watcher.has_manual_override = True
        win._update_ui_state()
        win.active_mode_lbl.config.assert_called_with(text="⚖️ Сбалансированная", foreground="#89b4fa")
        win.fan_lbl.config.assert_called_with(text="Сбалансированный")
        win.auto_status_lbl.config.assert_called_with(text="Ручной выбор (переопределено)", foreground="#f9e2af")

        # Test manual mode disabled
        self.config.auto_switching_enabled = False
        mock_ppm.get_active_plan.return_value = (dashboard.GUID_POWER_SAVER, "Power Saver")
        win._update_ui_state()
        win.active_mode_lbl.config.assert_called_with(text="🍃 Экономия энергии", foreground="#a6e3a1")
        win.fan_lbl.config.assert_called_with(text="Тихий / Эко")
        win.auto_status_lbl.config.assert_called_with(text="Ручной выбор (авто-режим выключен)", foreground="#f9e2af")

    @patch('power_plan.PowerPlanManager')
    def test_set_plan(self, mock_ppm_class):
        mock_ppm = MagicMock()
        mock_ppm.get_active_plan.return_value = (dashboard.GUID_HIGH_PERFORMANCE, "High Performance")
        mock_ppm_class.return_value = mock_ppm
        self.tray_app._watcher = self.watcher

        win = DashboardWindow(self.tray_app, self.config, self.watcher)
        win._update_ui_state = MagicMock()

        win._set_plan(dashboard.GUID_BALANCED)
        mock_ppm.set_active_plan.assert_called_with(dashboard.GUID_BALANCED)
        self.assertTrue(self.tray_app._watcher.has_manual_override)
        self.tray_app.update_icon.assert_called_once()
        win._update_ui_state.assert_called_once()

    @patch('power_plan.PowerPlanManager')
    def test_quick_switcher_highlight_states(self, mock_ppm_class):
        mock_ppm = MagicMock()
        mock_ppm.get_active_plan.return_value = (dashboard.GUID_HIGH_PERFORMANCE, "High Performance")
        mock_ppm_class.return_value = mock_ppm
        self.tray_app._watcher = self.watcher

        win = DashboardWindow(self.tray_app, self.config, self.watcher)
        self.assertTrue(hasattr(win, 'btn_turbo'))
        self.assertTrue(hasattr(win, 'btn_balance'))
        self.assertTrue(hasattr(win, 'btn_eco'))

        # 1. Auto mode: all 3 buttons are neutral dark
        self.config.auto_switching_enabled = True
        self.watcher.has_manual_override = False
        win._update_ui_state()

        self.assertEqual(win.btn_turbo.configure.call_args[1].get('bg'), dashboard.THEMES[win.current_theme]['btn_bg'])
        self.assertEqual(win.btn_balance.configure.call_args[1].get('bg'), dashboard.THEMES[win.current_theme]['btn_bg'])
        self.assertEqual(win.btn_eco.configure.call_args[1].get('bg'), dashboard.THEMES[win.current_theme]['btn_bg'])

        # 2. Manual mode Turbo
        self.watcher.has_manual_override = True
        mock_ppm.get_active_plan.return_value = (dashboard.GUID_HIGH_PERFORMANCE, "High Performance")
        win._update_ui_state()
        self.assertEqual(win.btn_turbo.configure.call_args[1].get('bg'), dashboard.THEMES[win.current_theme]['turbo_fg'])

        # 3. Manual mode Balanced
        mock_ppm.get_active_plan.return_value = (dashboard.GUID_BALANCED, "Balanced")
        win._update_ui_state()
        self.assertEqual(win.btn_balance.configure.call_args[1].get('bg'), dashboard.THEMES[win.current_theme]['balance_fg'])

        # 4. Manual mode Eco
        mock_ppm.get_active_plan.return_value = (dashboard.GUID_POWER_SAVER, "Power Saver")
        win._update_ui_state()
        self.assertEqual(win.btn_eco.configure.call_args[1].get('bg'), dashboard.THEMES[win.current_theme]['eco_fg'])

        # 5. Resume auto resets back to neutral
        win._resume_auto()
        self.assertEqual(win.btn_turbo.configure.call_args[1].get('bg'), dashboard.THEMES[win.current_theme]['btn_bg'])
        self.assertEqual(win.btn_balance.configure.call_args[1].get('bg'), dashboard.THEMES[win.current_theme]['btn_bg'])
        self.assertEqual(win.btn_eco.configure.call_args[1].get('bg'), dashboard.THEMES[win.current_theme]['btn_bg'])

    def test_standalone_on_close_exits(self):
        win = DashboardWindow(self.tray_app, self.config, self.watcher, is_standalone=True)
        with self.assertRaises(SystemExit) as ctx:
            win._on_close()
        self.assertEqual(ctx.exception.code, 0)

    @patch('dashboard._bring_existing_dashboard_to_front')
    @patch('ctypes.windll.kernel32.GetLastError', return_value=183)
    @patch('ctypes.windll.kernel32.CreateMutexW', return_value=12345)
    @patch('ctypes.windll.kernel32.CloseHandle')
    def test_run_standalone_dashboard_mutex_conflict(self, mock_close, mock_mutex, mock_err, mock_bring):
        with self.assertRaises(SystemExit) as ctx:
            dashboard.run_standalone_dashboard()
        self.assertEqual(ctx.exception.code, 0)
        mock_bring.assert_called_once()
        mock_close.assert_called_with(12345)

    @patch('dashboard.DashboardWindow')
    @patch('ctypes.windll.kernel32.GetLastError', return_value=0)
    @patch('ctypes.windll.kernel32.CreateMutexW', return_value=12345)
    @patch('ctypes.windll.kernel32.CloseHandle')
    def test_run_standalone_dashboard_success(self, mock_close, mock_mutex, mock_err, mock_win_cls):
        mock_win = MagicMock()
        mock_win_cls.return_value = mock_win

        with self.assertRaises(SystemExit) as ctx:
            dashboard.run_standalone_dashboard()
        self.assertEqual(ctx.exception.code, 0)
        mock_win.root.mainloop.assert_called_once()
        mock_close.assert_called_with(12345)

    @patch('dashboard.show_dashboard_window')
    def test_tray_app_open_dashboard_fast(self, mock_show):
        from tray_app import PowerMasterTrayApp
        tray = PowerMasterTrayApp.__new__(PowerMasterTrayApp)
        tray._watcher = MagicMock()
        tray._open_dashboard_action()
        mock_show.assert_called_once_with(
            tray_app=tray,
            config_obj=dashboard.config,
            watcher=tray._watcher,
        )

    def test_dashboard_startup_withdraw_prevents_flicker(self):
        win = DashboardWindow(self.tray_app, self.config, self.watcher, initially_hidden=False)
        win.root.withdraw.assert_called()
        win.root.deiconify.assert_called()

        win_hidden = DashboardWindow(self.tray_app, self.config, self.watcher, initially_hidden=True)
        win_hidden.root.withdraw.assert_called()

    def test_dashboard_scale_switching(self):
        win = DashboardWindow(self.tray_app, self.config, self.watcher)
        self.assertEqual(win.current_scale, 1.0)
        self.assertIn(1.0, win.scale_btns)
        self.assertIn(1.25, win.scale_btns)
        self.assertIn(1.5, win.scale_btns)
        win.set_scale(1.25)
        self.assertEqual(win.current_scale, 1.25)
        self.assertEqual(self.config.ui_scale, 1.25)
        win.root.geometry.assert_called_with("730x770+595+155")
        win.set_scale(1.5)
        self.assertEqual(win.current_scale, 1.5)
        self.assertEqual(self.config.ui_scale, 1.5)
        win.root.geometry.assert_called_with("840x850+540+115")
        win.set_scale(1.0)
        self.assertEqual(win.current_scale, 1.0)
        win.root.geometry.assert_called_with("620x700+650+190")

    def test_dashboard_theme_switching(self):
        win = DashboardWindow(self.tray_app, self.config, self.watcher)
        self.assertEqual(win.current_theme, "cyber_dark")
        win.set_theme("clean_minimalist")
        self.assertEqual(win.current_theme, "clean_minimalist")
        self.assertEqual(self.config.ui_theme, "clean_minimalist")
        win.set_theme("oled_contrast")
        self.assertEqual(win.current_theme, "oled_contrast")
        self.assertEqual(self.config.ui_theme, "oled_contrast")

    def test_dashboard_hide_and_deiconify(self):
        win = DashboardWindow(self.tray_app, self.config, self.watcher, is_standalone=False)
        win.hide_window()
        win.root.withdraw.assert_called()
        self.assertIsNone(win.telemetry_timer)

        win.lift_to_front()
        win.root.deiconify.assert_called()
        win.root.lift.assert_called()

    @patch('threading.Thread')
    def test_prewarm_dashboard(self, mock_thread):
        DashboardWindow._instance = None
        mock_t = MagicMock()
        mock_thread.return_value = mock_t
        t = dashboard.prewarm_dashboard(self.tray_app, self.config, self.watcher)
        mock_thread.assert_called_once()
        mock_t.start.assert_called_once()

    @patch('dashboard.run_standalone_dashboard')
    def test_main_cli_dashboard_flag(self, mock_run_dash):
        import sys
        from main import main
        with patch.object(sys, 'argv', ['main.py', '--dashboard']):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 0)
            mock_run_dash.assert_called_once()

    @patch('settings_dialog.open_settings_window')
    def test_dashboard_open_settings(self, mock_open_settings):
        win = DashboardWindow(self.tray_app, self.config, self.watcher)
        win._open_settings()
        mock_open_settings.assert_called_once()

    @patch('windows_energy_saver.WindowsEnergySaver.set_state', return_value=(False, "Permission denied"))
    @patch('dashboard.os.startfile')
    def test_dashboard_windows_energy_saver_toggle_launches_settings(self, mock_startfile, mock_set_state):
        win = DashboardWindow(self.tray_app, self.config, self.watcher)
        win._on_windows_energy_saver_toggled()
        mock_startfile.assert_called_once_with("ms-settings:batterysaver")

    @patch('windows_energy_saver.WindowsEnergySaver.set_state', return_value=(True, "OK"))
    @patch('windows_energy_saver.WindowsEnergySaver.get_state', return_value=0)
    def test_dashboard_windows_energy_saver_toggle_success(self, mock_get_state, mock_set_state):
        win = DashboardWindow(self.tray_app, self.config, self.watcher)
        win._on_windows_energy_saver_toggled()
        mock_set_state.assert_called_once_with(True)
        self.assertTrue(self.config.windows_energy_saver_manual)

    def test_dashboard_resume_auto(self):
        self.watcher.has_manual_override = True
        self.config.auto_switching_enabled = False
        self.tray_app._watcher = self.watcher

        win = DashboardWindow(self.tray_app, self.config, self.watcher)
        win._resume_auto()
        self.assertFalse(self.watcher.has_manual_override)
        self.assertTrue(self.config.auto_switching_enabled)
        self.assertIsNone(self.config.manual_override_guid)
        self.tray_app.update_icon.assert_called()

    def test_standalone_set_plan_persists_config(self):
        win = DashboardWindow(tray_app=None, config_obj=self.config, watcher=None, is_standalone=True)
        with patch('power_plan.PowerPlanManager.set_active_plan') as mock_set:
            win._set_plan(dashboard.GUID_HIGH_PERFORMANCE)
            mock_set.assert_called_with(dashboard.GUID_HIGH_PERFORMANCE)
            self.assertEqual(self.config.manual_override_guid, dashboard.GUID_HIGH_PERFORMANCE)
        win.is_standalone = False

    @patch('dashboard.win32pdh', create=True)
    def test_dynamic_cpu_telemetry_pdh_calculation(self, mock_pdh):
        """Fallback path: % Processor Performance × base_mhz."""
        # % Processor Performance returns 135% → 135 * 3000 / 100 = 4050 MHz = 4.05 GHz
        mock_pdh.GetFormattedCounterValue.return_value = (0, 135.0)
        import sys
        sys.modules['win32pdh'] = mock_pdh

        from dashboard import DynamicCpuTelemetry
        with patch('psutil.cpu_freq') as mock_psutil:
            mock_psutil.return_value = None
            telemetry = DynamicCpuTelemetry()
            # _counter_actual=None → primary skipped; _counter_perf active → fallback path
            telemetry._pdh_query = 1234
            telemetry._counter_actual = None
            telemetry._counter_perf = 5678
            telemetry._base_mhz = 3000.0

            freq = telemetry.get_frequency_ghz()
            del sys.modules['win32pdh']

            # 3000 MHz * 135 / 100 = 4050 MHz = 4.05 GHz
            self.assertAlmostEqual(freq, 4.05, places=2)

    @patch('dashboard.win32pdh', create=True)
    def test_dynamic_cpu_telemetry_actual_frequency_primary(self, mock_pdh):
        """Actual Frequency counter (primary path) returns MHz directly — like Task Manager."""
        # Actual Frequency returns 3530 MHz → 3.53 GHz
        mock_pdh.GetFormattedCounterValue.return_value = (0, 3530.0)
        import sys
        sys.modules['win32pdh'] = mock_pdh

        from dashboard import DynamicCpuTelemetry
        with patch('psutil.cpu_freq') as mock_psutil:
            mock_psutil.return_value = None
            telemetry = DynamicCpuTelemetry()
            telemetry._pdh_query = 1234
            telemetry._counter_actual = 9999   # primary counter active
            telemetry._counter_perf = 5678
            telemetry._base_mhz = 3000.0

            freq = telemetry.get_frequency_ghz()
            del sys.modules['win32pdh']

            # Actual Frequency: 3530 MHz / 1000 = 3.53 GHz
            self.assertAlmostEqual(freq, 3.53, places=2)

    def test_dynamic_cpu_telemetry_fallback_psutil(self):
        from dashboard import DynamicCpuTelemetry
        telemetry = DynamicCpuTelemetry()
        telemetry._pdh_query = None
        telemetry._counter_perf = None

        with patch('psutil.cpu_freq') as mock_freq:
            mock_freq.return_value.current = 2900.0
            freq = telemetry.get_frequency_ghz()
            self.assertAlmostEqual(freq, 2.9, places=2)

    @patch('power_watcher.PowerWatcher.get_user_idle_seconds', return_value=0)
    def test_standalone_resume_auto_sets_desired_plan(self, mock_idle):
        win = DashboardWindow(tray_app=None, config_obj=self.config, watcher=None, is_standalone=True)
        self.config.manual_override_guid = dashboard.GUID_HIGH_PERFORMANCE
        with patch('power_plan.PowerPlanManager.set_active_plan') as mock_set:
            win._resume_auto()
            self.assertIsNone(self.config.manual_override_guid)
            self.assertTrue(self.config.auto_switching_enabled)
            mock_set.assert_called()
        win.is_standalone = False

    @patch('pythoncom.CoInitialize')
    @patch('win32com.client.Dispatch')
    def test_dynamic_cpu_telemetry_temperature_high_precision(self, mock_dispatch, mock_coinit):
        from dashboard import DynamicCpuTelemetry
        mock_loc = MagicMock()
        mock_dispatch.return_value = mock_loc
        mock_cim = MagicMock()
        mock_loc.ConnectServer.return_value = mock_cim

        mock_tz = MagicMock()
        mock_tz.HighPrecisionTemperature = 3282
        mock_tz.Temperature = 328
        mock_cim.ExecQuery.return_value = [mock_tz]

        telemetry = DynamicCpuTelemetry()
        temp = telemetry.get_temperature_c()
        self.assertIsNotNone(temp)
        self.assertAlmostEqual(temp, 55.0, places=1)
        mock_loc.ConnectServer.assert_called_with(".", r"root\cimv2")

    @patch('pythoncom.CoInitialize')
    @patch('win32com.client.Dispatch')
    def test_dynamic_cpu_telemetry_temperature_standard_fallback(self, mock_dispatch, mock_coinit):
        from dashboard import DynamicCpuTelemetry
        mock_loc = MagicMock()
        mock_dispatch.return_value = mock_loc
        mock_cim = MagicMock()
        mock_loc.ConnectServer.return_value = mock_cim

        mock_tz = MagicMock()
        mock_tz.HighPrecisionTemperature = None
        mock_tz.Temperature = 328
        mock_cim.ExecQuery.return_value = [mock_tz]

        telemetry = DynamicCpuTelemetry()
        temp = telemetry.get_temperature_c()
        self.assertIsNotNone(temp)
        self.assertAlmostEqual(temp, 328 - 273.15, places=2)

    @patch('pythoncom.CoInitialize')
    @patch('win32com.client.Dispatch')
    def test_dynamic_cpu_telemetry_temperature_msacpi_fallback(self, mock_dispatch, mock_coinit):
        from dashboard import DynamicCpuTelemetry
        mock_loc = MagicMock()
        mock_dispatch.return_value = mock_loc

        def fake_connect(server, namespace):
            if namespace == r"root\cimv2":
                raise Exception("CIM failed")
            elif namespace == r"root\wmi":
                svc = MagicMock()
                mock_tz = MagicMock()
                mock_tz.CurrentTemperature = 3302
                svc.ExecQuery.return_value = [mock_tz]
                return svc
            return MagicMock()

        mock_loc.ConnectServer.side_effect = fake_connect

        telemetry = DynamicCpuTelemetry()
        temp = telemetry.get_temperature_c()
        self.assertIsNotNone(temp)
        self.assertAlmostEqual(temp, 57.0, places=1)

    @patch('pythoncom.CoInitialize')
    @patch('win32com.client.Dispatch')
    def test_dynamic_cpu_telemetry_fan_rpm_dsts(self, mock_dispatch, mock_coinit):
        from dashboard import DynamicCpuTelemetry
        mock_loc = MagicMock()
        mock_dispatch.return_value = mock_loc
        mock_wmi = MagicMock()
        mock_loc.ConnectServer.return_value = mock_wmi

        mock_asus = MagicMock()
        mock_asus.DSTS.return_value = 3800
        mock_wmi.ExecQuery.return_value = [mock_asus]

        telemetry = DynamicCpuTelemetry()
        rpm = telemetry.get_fan_rpm()
        self.assertEqual(rpm, 3800)
        mock_asus.DSTS.assert_called_with(0x00110013)

    @patch('pythoncom.CoInitialize')
    @patch('win32com.client.Dispatch')
    def test_dynamic_cpu_telemetry_fan_rpm_zero_stopped(self, mock_dispatch, mock_coinit):
        from dashboard import DynamicCpuTelemetry
        mock_loc = MagicMock()
        mock_dispatch.return_value = mock_loc
        mock_wmi = MagicMock()
        mock_loc.ConnectServer.return_value = mock_wmi

        mock_asus = MagicMock()
        mock_asus.DSTS.return_value = 0
        mock_wmi.ExecQuery.return_value = [mock_asus]

        telemetry = DynamicCpuTelemetry()
        rpm = telemetry.get_fan_rpm()
        self.assertEqual(rpm, 0)

    @patch('pythoncom.CoInitialize')
    @patch('win32com.client.Dispatch')
    def test_dynamic_cpu_telemetry_fan_rpm_invalid(self, mock_dispatch, mock_coinit):
        from dashboard import DynamicCpuTelemetry
        mock_loc = MagicMock()
        mock_dispatch.return_value = mock_loc
        mock_wmi = MagicMock()
        mock_loc.ConnectServer.return_value = mock_wmi

        mock_asus = MagicMock()
        mock_asus.DSTS.return_value = 65535
        mock_wmi.ExecQuery.return_value = [mock_asus]

        telemetry = DynamicCpuTelemetry()
        rpm = telemetry.get_fan_rpm()
        self.assertIsNone(rpm)

    @patch('pythoncom.CoInitialize')
    @patch('win32com.client.Dispatch')
    def test_gpu_telemetry_fan_rpm_asus_wmi(self, mock_dispatch, mock_coinit):
        from dashboard import GpuTelemetry
        mock_loc = MagicMock()
        mock_dispatch.return_value = mock_loc
        mock_wmi = MagicMock()
        mock_loc.ConnectServer.return_value = mock_wmi

        mock_asus = MagicMock()
        mock_asus.DSTS.return_value = 3400
        mock_wmi.ExecQuery.return_value = [mock_asus]

        gpu = GpuTelemetry()
        rpm = gpu.get_fan_rpm()
        self.assertEqual(rpm, 3400)
        mock_asus.DSTS.assert_called_with(0x00110014)

    @patch('pythoncom.CoInitialize')
    @patch('win32com.client.Dispatch')
    def test_gpu_telemetry_fan_rpm_nvml_fallback(self, mock_dispatch, mock_coinit):
        from dashboard import GpuTelemetry
        mock_dispatch.side_effect = Exception("WMI failed")

        gpu = GpuTelemetry()
        gpu._initialized = True
        gpu._handle = MagicMock()
        gpu._nvml = MagicMock()
        def fake_fan(handle, ref):
            ref._obj.value = 55
            return 0
        gpu._nvml.nvmlDeviceGetFanSpeed.side_effect = fake_fan

        rpm = gpu.get_fan_rpm()
        self.assertEqual(rpm, 55)

    @patch('pythoncom.CoInitialize')
    @patch('win32com.client.Dispatch')
    def test_dynamic_cpu_telemetry_fan_rpm_exec_method_device_status(self, mock_dispatch, mock_coinit):
        from dashboard import DynamicCpuTelemetry
        mock_loc = MagicMock()
        mock_dispatch.return_value = mock_loc
        mock_wmi = MagicMock()
        mock_loc.ConnectServer.return_value = mock_wmi

        mock_asus = MagicMock()
        mock_asus.DSTS.side_effect = Exception("Type mismatch")
        mock_in_params = MagicMock()
        mock_asus.Methods_.return_value.InParameters.SpawnInstance_.return_value = mock_in_params
        mock_out = MagicMock()
        mock_out.device_status = 3900
        mock_asus.ExecMethod_.return_value = mock_out
        mock_wmi.ExecQuery.return_value = [mock_asus]

        telemetry = DynamicCpuTelemetry()
        rpm = telemetry.get_fan_rpm()
        self.assertEqual(rpm, 3900)
        self.assertEqual(mock_in_params.Device_ID, 0x00110013)
        mock_asus.ExecMethod_.assert_called_with("DSTS", mock_in_params)

    @patch('pythoncom.CoInitialize')
    @patch('win32com.client.Dispatch')
    def test_gpu_telemetry_fan_rpm_exec_method_device_status(self, mock_dispatch, mock_coinit):
        from dashboard import GpuTelemetry
        mock_loc = MagicMock()
        mock_dispatch.return_value = mock_loc
        mock_wmi = MagicMock()
        mock_loc.ConnectServer.return_value = mock_wmi

        mock_asus = MagicMock()
        mock_asus.DSTS.side_effect = Exception("Type mismatch")
        mock_in_params = MagicMock()
        mock_asus.Methods_.return_value.InParameters.SpawnInstance_.return_value = mock_in_params
        mock_out = MagicMock()
        mock_out.device_status = 3100
        mock_asus.ExecMethod_.return_value = mock_out
        mock_wmi.ExecQuery.return_value = [mock_asus]

        gpu = GpuTelemetry()
        rpm = gpu.get_fan_rpm()
        self.assertEqual(rpm, 3100)
        self.assertEqual(mock_in_params.Device_ID, 0x00110014)
        mock_asus.ExecMethod_.assert_called_with("DSTS", mock_in_params)

    def test_parse_fan_result_variants(self):
        from dashboard import DynamicCpuTelemetry
        # Standard values >= 100 preserved
        self.assertEqual(DynamicCpuTelemetry._parse_fan_result(3200), 3200)
        self.assertEqual(DynamicCpuTelemetry._parse_fan_result(100), 100)
        # Scaled values (0 < rpm < 100 scaled by 100)
        self.assertEqual(DynamicCpuTelemetry._parse_fan_result(25), 2500)
        self.assertEqual(DynamicCpuTelemetry._parse_fan_result(1), 100)
        self.assertEqual(DynamicCpuTelemetry._parse_fan_result(99), 9900)
        # Stop state
        self.assertEqual(DynamicCpuTelemetry._parse_fan_result(0), 0)
        # Invalid / out of range & types
        self.assertIsNone(DynamicCpuTelemetry._parse_fan_result(65535))
        self.assertIsNone(DynamicCpuTelemetry._parse_fan_result(-1))
        self.assertIsNone(DynamicCpuTelemetry._parse_fan_result(-2))
        self.assertIsNone(DynamicCpuTelemetry._parse_fan_result(-100))
        self.assertIsNone(DynamicCpuTelemetry._parse_fan_result(True))
        self.assertIsNone(DynamicCpuTelemetry._parse_fan_result(False))
        self.assertIsNone(DynamicCpuTelemetry._parse_fan_result(None))

        # ACPI bitmask with high status bits
        self.assertIsNone(DynamicCpuTelemetry._parse_fan_result(0x00010019))
        self.assertEqual(DynamicCpuTelemetry._parse_fan_result(0x00010000), 0)
        self.assertIsNone(DynamicCpuTelemetry._parse_fan_result(0x0001FFFF))

        # Object with device_status attribute (scaled)
        obj_ec = MagicMock()
        obj_ec.device_status = 25
        self.assertEqual(DynamicCpuTelemetry._parse_fan_result(obj_ec), 2500)

        # Object with device_status attribute (absolute)
        obj1 = MagicMock()
        obj1.device_status = 2500
        self.assertEqual(DynamicCpuTelemetry._parse_fan_result(obj1), 2500)

        # Object with ReturnValue attribute
        obj2 = MagicMock(spec=['ReturnValue'])
        obj2.ReturnValue = 2700
        self.assertEqual(DynamicCpuTelemetry._parse_fan_result(obj2), 2700)

        # Object with Properties_ collection
        obj3 = MagicMock(spec=['Properties_'])
        mock_prop = MagicMock()
        mock_prop.Value = 2800
        obj3.Properties_.return_value = mock_prop
        self.assertEqual(DynamicCpuTelemetry._parse_fan_result(obj3), 2800)



    @patch('psutil.sensors_battery')
    def test_battery_charge_limit_display_scenarios(self, mock_battery):
        mock_batt = MagicMock()
        mock_batt.percent = 61
        mock_batt.power_plugged = True
        mock_battery.return_value = mock_batt

        # Case 1: Active config has battery_charge_limit = 60
        cfg = MagicMock()
        cfg.battery_charge_limit = 60
        cfg.charge_limit = None
        cfg.auto_switching_enabled = True
        cfg.manual_override_guid = None

        win = DashboardWindow(self.tray_app, cfg, self.watcher)
        win.battery_lbl = MagicMock()
        win._poll_telemetry()
        win.battery_lbl.config.assert_called_with(text="🔌 61% (Лимит: 60% • не заряжается)")

        # Case 2: Fallback to asus_battery.get_current_limit when not set in config
        dummy_cfg = MagicMock()
        dummy_cfg.battery_charge_limit = None
        dummy_cfg.charge_limit = None
        dummy_cfg.auto_switching_enabled = True
        dummy_cfg.manual_override_guid = None
        with patch('asus_battery.AsusBatteryController.get_current_limit', return_value=(80, "OK")):
            win2 = DashboardWindow(self.tray_app, dummy_cfg, self.watcher)
            win2.battery_lbl = MagicMock()
            win2._poll_telemetry()
            win2.battery_lbl.config.assert_called_with(text="🔌 61% (Лимит: 80%)")

        # Case 3: Complete fallback to --%
        with patch('asus_battery.AsusBatteryController.get_current_limit', return_value=(None, "Not supported")):
            win3 = DashboardWindow(self.tray_app, dummy_cfg, self.watcher)
            win3.battery_lbl = MagicMock()
            win3._poll_telemetry()
            win3.battery_lbl.config.assert_called_with(text="🔌 61% (Лимит: --%)")


class TestAsusWinIOFanReader(unittest.TestCase):
    def setUp(self):
        from dashboard import AsusWinIOFanReader
        AsusWinIOFanReader.reset_instance()

    def tearDown(self):
        from dashboard import AsusWinIOFanReader
        AsusWinIOFanReader.reset_instance()

    @patch('glob.glob')
    @patch('os.path.isfile')
    def test_find_dll_path_found(self, mock_isfile, mock_glob):
        from dashboard import AsusWinIOFanReader
        mock_glob.side_effect = lambda pat: [r"C:\fake\AsusWinIO64.dll"] if "asussci2" in pat else []
        mock_isfile.return_value = True

        with patch('os.path.getmtime', return_value=123456):
            found = AsusWinIOFanReader.find_dll_path()
            self.assertEqual(found, r"C:\fake\AsusWinIO64.dll")

    @patch('glob.glob')
    @patch('os.path.isfile')
    def test_find_dll_path_not_found(self, mock_isfile, mock_glob):
        from dashboard import AsusWinIOFanReader
        mock_glob.return_value = []
        mock_isfile.return_value = False

        found = AsusWinIOFanReader.find_dll_path()
        self.assertIsNone(found)

    @patch('win32service.OpenSCManager')
    @patch('win32service.OpenService')
    @patch('win32service.QueryServiceStatus')
    @patch('win32service.StartService')
    @patch('win32service.CloseServiceHandle')
    def test_ensure_service_running_win32service_stopped_starts(
        self, mock_close, mock_start, mock_status, mock_open_svc, mock_scm
    ):
        from dashboard import AsusWinIOFanReader
        import win32service
        mock_status.return_value = (0, win32service.SERVICE_STOPPED)

        reader = AsusWinIOFanReader.__new__(AsusWinIOFanReader)
        reader._service_attempted = False
        res = reader._ensure_service_running()
        self.assertTrue(res)
        mock_start.assert_called_once()

    @patch('win32service.OpenSCManager')
    @patch('win32service.OpenService')
    @patch('win32service.QueryServiceStatus')
    @patch('win32service.StartService')
    @patch('win32service.CloseServiceHandle')
    def test_ensure_service_running_win32service_already_running(
        self, mock_close, mock_start, mock_status, mock_open_svc, mock_scm
    ):
        from dashboard import AsusWinIOFanReader
        import win32service
        mock_status.return_value = (0, win32service.SERVICE_RUNNING)

        reader = AsusWinIOFanReader.__new__(AsusWinIOFanReader)
        reader._service_attempted = False
        res = reader._ensure_service_running()
        self.assertTrue(res)
        mock_start.assert_not_called()

    @patch('win32service.OpenSCManager', side_effect=Exception("Access denied"))
    @patch('subprocess.run')
    def test_ensure_service_running_fallback_sc(self, mock_subproc, mock_scm):
        from dashboard import AsusWinIOFanReader
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_subproc.return_value = mock_res

        reader = AsusWinIOFanReader.__new__(AsusWinIOFanReader)
        reader._service_attempted = False
        res = reader._ensure_service_running()
        self.assertTrue(res)
        mock_subproc.assert_called_once()
        self.assertIn("asussaio", mock_subproc.call_args[0][0])

    @patch('dashboard.AsusWinIOFanReader.find_dll_path', return_value=r"C:\fake\AsusWinIO64.dll")
    @patch('ctypes.WinDLL')
    def test_init_winio_success(self, mock_windll, mock_find):
        from dashboard import AsusWinIOFanReader
        mock_dll = MagicMock()
        mock_dll.InitializeWinIo.return_value = True
        mock_windll.return_value = mock_dll

        with patch.object(AsusWinIOFanReader, '_ensure_service_running', return_value=True):
            reader = AsusWinIOFanReader()
            self.assertTrue(reader._initialized)
            self.assertIs(reader._dll, mock_dll)

    @patch('dashboard.AsusWinIOFanReader.find_dll_path', return_value=r"C:\fake\AsusWinIO64.dll")
    @patch('ctypes.WinDLL')
    def test_init_winio_initialize_fails(self, mock_windll, mock_find):
        from dashboard import AsusWinIOFanReader
        mock_dll = MagicMock()
        mock_dll.InitializeWinIo.return_value = False
        mock_windll.return_value = mock_dll

        with patch.object(AsusWinIOFanReader, '_ensure_service_running', return_value=True):
            reader = AsusWinIOFanReader()
            self.assertFalse(reader._initialized)
            self.assertIsNone(reader._dll)

    @patch('dashboard.AsusWinIOFanReader.find_dll_path', return_value=r"C:\fake\AsusWinIO64.dll")
    @patch('ctypes.WinDLL', side_effect=OSError("DLL load failed"))
    def test_init_winio_dll_load_error(self, mock_windll, mock_find):
        from dashboard import AsusWinIOFanReader
        with patch.object(AsusWinIOFanReader, '_ensure_service_running', return_value=True):
            reader = AsusWinIOFanReader()
            self.assertFalse(reader._initialized)
            self.assertIsNone(reader._dll)

    def test_get_fan_rpm_success(self):
        from dashboard import AsusWinIOFanReader
        reader = AsusWinIOFanReader.__new__(AsusWinIOFanReader)
        mock_dll = MagicMock()
        mock_dll.HealthyTable_FanRPM.side_effect = lambda idx: 3300 if idx == 0 else 3100
        reader._dll = mock_dll
        reader._initialized = True

        self.assertEqual(reader.get_fan_rpm(0), 3300)
        self.assertEqual(reader.get_cpu_fan_rpm(), 3300)
        self.assertEqual(reader.get_fan_rpm(1), 3100)
        self.assertEqual(reader.get_gpu_fan_rpm(), 3100)

    def test_get_fan_rpm_invalid_and_exceptions(self):
        from dashboard import AsusWinIOFanReader
        reader = AsusWinIOFanReader.__new__(AsusWinIOFanReader)
        mock_dll = MagicMock()
        reader._dll = mock_dll
        reader._initialized = True

        # Returns <= 0 (e.g. -1 or 0)
        mock_dll.HealthyTable_FanRPM.return_value = -1
        self.assertIsNone(reader.get_fan_rpm(0))

        mock_dll.HealthyTable_FanRPM.return_value = 0
        self.assertIsNone(reader.get_fan_rpm(0))

        # Raises exception
        mock_dll.HealthyTable_FanRPM.side_effect = RuntimeError("Access violation")
        self.assertIsNone(reader.get_fan_rpm(0))

        # Uninitialized
        reader._initialized = False
        self.assertIsNone(reader.get_fan_rpm(0))

    def test_close_and_singleton(self):
        from dashboard import AsusWinIOFanReader
        mock_dll = MagicMock()
        mock_dll.InitializeWinIo.return_value = True

        with patch.object(AsusWinIOFanReader, 'find_dll_path', return_value=r"C:\fake\AsusWinIO64.dll"), \
             patch('ctypes.WinDLL', return_value=mock_dll), \
             patch.object(AsusWinIOFanReader, '_ensure_service_running', return_value=True):
            inst1 = AsusWinIOFanReader.get_instance()
            inst2 = AsusWinIOFanReader.get_instance()
            self.assertIs(inst1, inst2)
            self.assertTrue(inst1._initialized)

            inst1.close()
            mock_dll.ShutdownWinIo.assert_called_once()
            self.assertFalse(inst1._initialized)
            self.assertIsNone(AsusWinIOFanReader._instance)

    def test_dynamic_cpu_telemetry_uses_winio_success(self):
        from dashboard import DynamicCpuTelemetry
        mock_reader = MagicMock()
        mock_reader.get_cpu_fan_rpm.return_value = 4200

        telemetry = DynamicCpuTelemetry(fan_reader=mock_reader)
        with patch('win32com.client.Dispatch') as mock_dispatch:
            rpm = telemetry.get_fan_rpm()
            self.assertEqual(rpm, 4200)
            mock_reader.get_cpu_fan_rpm.assert_called_once()
            mock_dispatch.assert_not_called()

    @patch('pythoncom.CoInitialize')
    @patch('win32com.client.Dispatch')
    def test_dynamic_cpu_telemetry_winio_fallback_to_wmi(self, mock_dispatch, mock_coinit):
        from dashboard import DynamicCpuTelemetry
        mock_reader = MagicMock()
        mock_reader.get_cpu_fan_rpm.return_value = None

        mock_loc = MagicMock()
        mock_dispatch.return_value = mock_loc
        mock_wmi = MagicMock()
        mock_loc.ConnectServer.return_value = mock_wmi
        mock_asus = MagicMock()
        mock_asus.DSTS.return_value = 3500
        mock_wmi.ExecQuery.return_value = [mock_asus]

        telemetry = DynamicCpuTelemetry(fan_reader=mock_reader)
        rpm = telemetry.get_fan_rpm()
        self.assertEqual(rpm, 3500)
        mock_reader.get_cpu_fan_rpm.assert_called_once()
        mock_asus.DSTS.assert_called_with(0x00110013)

    def test_gpu_telemetry_uses_winio_success(self):
        from dashboard import GpuTelemetry
        mock_reader = MagicMock()
        mock_reader.get_gpu_fan_rpm.return_value = 3800

        gpu = GpuTelemetry(fan_reader=mock_reader)
        with patch('win32com.client.Dispatch') as mock_dispatch:
            rpm = gpu.get_fan_rpm()
            self.assertEqual(rpm, 3800)
            mock_reader.get_gpu_fan_rpm.assert_called_once()
            mock_dispatch.assert_not_called()

    @patch('pythoncom.CoInitialize')
    @patch('win32com.client.Dispatch')
    def test_gpu_telemetry_winio_fallback_to_wmi(self, mock_dispatch, mock_coinit):
        from dashboard import GpuTelemetry
        mock_reader = MagicMock()
        mock_reader.get_gpu_fan_rpm.return_value = None

        mock_loc = MagicMock()
        mock_dispatch.return_value = mock_loc
        mock_wmi = MagicMock()
        mock_loc.ConnectServer.return_value = mock_wmi
        mock_asus = MagicMock()
        mock_asus.DSTS.return_value = 3300
        mock_wmi.ExecQuery.return_value = [mock_asus]

        gpu = GpuTelemetry(fan_reader=mock_reader)
        rpm = gpu.get_fan_rpm()
        self.assertEqual(rpm, 3300)
        mock_reader.get_gpu_fan_rpm.assert_called_once()
        mock_asus.DSTS.assert_called_with(0x00110014)


class TestTelemetryRedesign(unittest.TestCase):
    def tearDown(self):
        import tkinter as tk
        tk._default_root = None
        import dashboard
        dashboard.DashboardWindow._instance = None

    def test_ivory_colors_in_themes(self):
        """1. Проверка наличия и корректного цвета слоновой кости во всех темах THEMES."""
        from dashboard import THEMES
        expected_ivory_colors = {"#FFF8E7", "#FDF6E2", "#F4EFEA"}
        self.assertTrue(len(THEMES) > 0, "THEMES dictionary should not be empty")
        for theme_name, theme_data in THEMES.items():
            self.assertIn("telemetry_val_fg", theme_data, f"Theme '{theme_name}' missing 'telemetry_val_fg'")
            color = theme_data["telemetry_val_fg"]
            self.assertIn(color, expected_ivory_colors, f"Theme '{theme_name}' color {color} is not an accepted ivory color")

    def test_window_geometry_scales(self):
        """2. Проверка корректности компактной геометрии окон при переключении масштабов."""
        from dashboard import SCALES
        expected_scales = {
            1.0: (620, 700),
            1.25: (730, 770),
            1.5: (840, 850)
        }
        for scale, (w, h) in expected_scales.items():
            self.assertIn(scale, SCALES, f"Scale {scale} missing from SCALES")
            self.assertEqual(SCALES[scale]["win_w"], w, f"Incorrect win_w for scale {scale}")
            self.assertEqual(SCALES[scale]["win_h"], h, f"Incorrect win_h for scale {scale}")

    @patch('tkinter.Tk', side_effect=MockTk)
    @patch('tkinter.ttk.Style', side_effect=MockStyle)
    @patch('tkinter.ttk.Frame', side_effect=MockFrame)
    @patch('tkinter.ttk.Label', side_effect=MockLabel)
    @patch('tkinter.ttk.Button', side_effect=MockButton)
    @patch('tkinter.ttk.Checkbutton', side_effect=MockCheckbutton)
    @patch('tkinter.Label', side_effect=MockLabel)
    @patch('tkinter.Button', side_effect=MockButton)
    def test_new_telemetry_widgets_and_polling(self, mock_tk_btn, mock_lbl, mock_chk, mock_btn, mock_tlbl, mock_tframe, mock_style, mock_tk):
        """3. Проверка инициализации виджетов телеметрии и безопасного опроса."""
        import dashboard
        dashboard.DashboardWindow._instance = None
        mock_cfg = MagicMock()
        mock_cfg.ui_theme = "oled_contrast"
        mock_cfg.ui_scale = 1.0

        mock_cpu_tel = MagicMock()
        mock_cpu_tel.get_frequency_ghz.return_value = 3.2
        mock_cpu_tel.get_temperature_c.return_value = 52.0

        mock_gpu_tel = MagicMock()
        mock_gpu_tel.get_utilization_pct.return_value = 15
        mock_gpu_tel.get_clock_mhz.return_value = 850
        mock_gpu_tel.get_temperature_c.return_value = 49.0

        dash = DashboardWindow(
            config_obj=mock_cfg,
            cpu_telemetry=mock_cpu_tel,
            gpu_telemetry=mock_gpu_tel,
            initially_hidden=True
        )

        self.assertTrue(hasattr(dash, 'ram_lbl'), "ram_lbl widget must exist")
        self.assertTrue(hasattr(dash, 'cpu_pct_lbl'), "cpu_pct_lbl widget must exist")
        self.assertTrue(hasattr(dash, 'gpu_pct_lbl'), "gpu_pct_lbl widget must exist")

        with patch('psutil.cpu_percent', return_value=35.5), \
             patch('psutil.virtual_memory') as mock_vm:
            mock_mem = MagicMock()
            mock_mem.used = 8 * (1024**3)
            mock_mem.total = 16 * (1024**3)
            mock_mem.percent = 50.0
            mock_vm.return_value = mock_mem

            dash._poll_telemetry()

            dash.cpu_pct_lbl.config.assert_called_with(text="35.5 %")
            dash.cpu_freq_lbl.config.assert_called_with(text="3.20 GHz")
            dash.cpu_temp_lbl.config.assert_called_with(text="52 °C")
            dash.gpu_pct_lbl.config.assert_called_with(text="15 %")
            dash.gpu_freq_lbl.config.assert_called_with(text="850 MHz")
            dash.gpu_temp_lbl.config.assert_called_with(text="49.0 °C")
            dash.ram_lbl.config.assert_called_with(text="📊 ОЗУ: 8.0 / 16.0 GB (50%)")

        dashboard.DashboardWindow._instance = None


if __name__ == '__main__':
    unittest.main()

