import sys
import unittest.mock
import ctypes

if sys.platform != "win32" or not hasattr(ctypes, "windll"):
    ctypes.windll = unittest.mock.MagicMock()

try:
    import pytest
    import tkinter as tk

    @pytest.fixture(autouse=True)
    def clean_tkinter_state():
        yield
        if hasattr(tk, "_default_root"):
            tk._default_root = None
        try:
            from settings_dialog import SettingsWindow
            SettingsWindow._instance = None
        except Exception:
            pass
        try:
            from dashboard import DashboardWindow
            DashboardWindow._instance = None
        except Exception:
            pass
except ImportError:
    pass

