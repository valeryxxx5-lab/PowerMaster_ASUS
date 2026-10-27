"""
Settings GUI Dialog Module for PowerMaster_ASUS (ТЗ-28).
Легковесное графическое окно настроек на нативном Tkinter / ttk (без внешних зависимостей).
Включает:
- Вкладка 1: Игры и процессы (управление папками и исполняемыми файлами).
- Вкладка 2: Внешний вид (выбор и предпросмотр 3 стилей иконки трея).
- Вкладка 3: Система и локализация (RU/EN, лимит заряда 60/80/100, таймер простоя).
- Гарантия Single-Instance (lift() и focus_force()).
- Атомарное сохранение в config.json через tempfile + fsync + os.replace.

Strict Zero-Stub Policy. Production-ready implementation.
"""

from __future__ import annotations
import logging
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Dict, Any, Optional, Callable

logger = logging.getLogger("PowerMaster.SettingsGUI")

# Словарь встроенной интернационализации (I18N)
I18N = {
    "ru": {
        "title": "PowerMaster ASUS - Настройки",
        "tab_games": "🎮 Игры и процессы",
        "tab_appearance": "🎨 Внешний вид",
        "tab_system": "⚙️ Система и Язык",
        "game_dirs": "Отслеживаемые каталоги игр:",
        "btn_add_dir": "+ Добавить папку...",
        "btn_remove_dir": "- Удалить папку",
        "game_procs": "Исполняемые файлы игр (.exe):",
        "btn_add_proc": "+ Добавить процесс",
        "btn_remove_proc": "- Удалить",
        "icon_style": "Стиль иконки в системном трее:",
        "icon_style_tile": "🔲 Огромная (Сплошная плитка - стиль Antigravity)",
        "icon_style_d": "🚀 Увеличенный силуэт (Скорость: Ракета / Авто / Вело)",
        "icon_style_a": "⚡ Неоновое кольцо с молнией (Адаптивное)",
        "icon_style_b": "🔋 Минималистичный индикатор батареи",
        "icon_style_c": "🛡️ Классический щит ASUS TUF / ROG",
        "preview": "Предпросмотр иконки:",
        "language": "Язык интерфейса (Language):",
        "charge_limit": "Лимит заряда батареи ASUS:",
        "battery_note": "ℹ️ Если батарея уже заряжена на 100%, отключите зарядку и дайте разрядиться ниже лимита. Ноутбук не разряжает батарею от сети.",
        "idle_timeout": "Таймер системного простоя (минуты):",
        "notify_change": "Всплывающие уведомления при смене плана питания",
        "github_token": "GitHub Token (для обновлений из приватного репозитория):",
        "btn_paste": "📋 Вставить",
        "btn_check_updates": "🔍 Проверить обновления сейчас",
        "btn_save": "Сохранить и применить",
        "btn_cancel": "Отмена",
        "saved_success": "Настройки успешно сохранены и применены!",
        "ui_theme": "Тема оформления интерфейса:",
        "ui_theme_cyber": "TUF Cyber Dark (Игровая)",
        "ui_theme_minimal": "Clean Minimalist (Нейтральная)",
        "ui_theme_oled": "High-Contrast OLED (Высокий контраст)",
        "ui_theme_light": "Light Modern (Светлая)",
        "ui_scale": "Масштаб интерфейса и шрифтов:",
        "ui_scale_100": "100% (Стандартный)",
        "ui_scale_125": "125% (Увеличенный)",
        "ui_scale_150": "150% (Огромный / Крупный)",
        "auto_switching": "Включить авто-переключение планов питания (FSM правила)",
        "btn_resume_auto": "⚡ Возобновить авторежим",
        "resumed_auto_msg": "Автоматический режим успешно возобновлен!\nРучные ограничения сброшены.",
        "asus_services_title": "Службы ASUS (конфликтующие с PowerMaster):",
        "asus_services_running": "⚠️ Работают службы ASUS: {count} шт. (могут сбрасывать лимит батареи)",
        "asus_services_disabled": "✅ Службы ASUS отключены и нейтрализованы",
        "asus_services_none": "ℹ️ Службы ASUS не установлены в системе",
        "btn_disable_asus_services": "🛑 Отключить службы ASUS",
        "btn_enable_asus_services": "🔄 Включить службы ASUS",
        "asus_services_disabled_success": "Службы ASUS успешно остановлены и отключены!",
        "asus_services_enabled_success": "Службы ASUS успешно включены и запущены!"
    },
    "en": {
        "title": "PowerMaster ASUS - Settings",
        "tab_games": "🎮 Games & Processes",
        "tab_appearance": "🎨 Appearance",
        "tab_system": "⚙️ System & Language",
        "game_dirs": "Monitored Game Directories:",
        "btn_add_dir": "+ Add Folder...",
        "btn_remove_dir": "- Remove Folder",
        "game_procs": "Monitored Game Executables (.exe):",
        "btn_add_proc": "+ Add Process",
        "btn_remove_proc": "- Remove",
        "icon_style": "System Tray Icon Style:",
        "icon_style_tile": "🔲 Huge Icon (Solid App Tile - Antigravity Style)",
        "icon_style_d": "🚀 Large Silhouette (Speed: Rocket / Car / Bike)",
        "icon_style_a": "⚡ Neon Dynamic Ring with Lightning",
        "icon_style_b": "🔋 Minimal Battery Percentage Gauge",
        "icon_style_c": "🛡️ Classic ASUS TUF / ROG Shield",
        "preview": "Icon Preview:",
        "language": "Interface Language:",
        "charge_limit": "ASUS Battery Charge Limit:",
        "battery_note": "ℹ️ If battery is at 100%, unplug charger to discharge below threshold. Laptop does not actively drain on AC.",
        "idle_timeout": "Idle Timeout (minutes):",
        "notify_change": "Show notifications on power plan switch",
        "github_token": "GitHub Token (for private repository updates):",
        "btn_paste": "📋 Paste",
        "btn_check_updates": "🔍 Check for updates now",
        "btn_save": "Save & Apply",
        "btn_cancel": "Cancel",
        "saved_success": "Settings saved and applied successfully!",
        "ui_theme": "UI Theme:",
        "ui_theme_cyber": "TUF Cyber Dark (Gaming)",
        "ui_theme_minimal": "Clean Minimalist (Neutral)",
        "ui_theme_oled": "High-Contrast OLED (Max Contrast)",
        "ui_theme_light": "Light Modern (Light Theme)",
        "ui_scale": "UI & Font Scaling:",
        "ui_scale_100": "100% (Standard)",
        "ui_scale_125": "125% (Large)",
        "ui_scale_150": "150% (Huge)",
        "auto_switching": "Enable automatic power plan switching (FSM rules)",
        "btn_resume_auto": "⚡ Resume Auto Mode",
        "resumed_auto_msg": "Automatic mode resumed successfully!\nManual overrides cleared.",
        "asus_services_title": "ASUS Services (conflicting with PowerMaster):",
        "asus_services_running": "⚠️ ASUS services running: {count} (may override battery limit)",
        "asus_services_disabled": "✅ ASUS services disabled and neutralized",
        "asus_services_none": "ℹ️ ASUS services not found on system",
        "btn_disable_asus_services": "🛑 Disable ASUS Services",
        "btn_enable_asus_services": "🔄 Enable ASUS Services",
        "asus_services_disabled_success": "ASUS services successfully stopped and disabled!",
        "asus_services_enabled_success": "ASUS services successfully enabled and started!"
    }
}

class SettingsWindow:
    """
    Потокобезопасное Single-Instance окно настроек PowerMaster_ASUS на Tkinter.
    """
    _instance: Optional[SettingsWindow] = None

    def __new__(cls, config_obj, on_save_callback=None, on_quit_callback=None):
        if cls._instance is not None:
            cls._instance.lift_to_front()
            return cls._instance
        instance = super().__new__(cls)
        cls._instance = instance
        return instance

    def __init__(
        self,
        config_obj,
        on_save_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_quit_callback: Optional[Callable[[], None]] = None,
    ):
        self.config_obj = config_obj
        self.on_save_callback = on_save_callback
        self.on_quit_callback = on_quit_callback

        root_win = getattr(tk, "_default_root", None)
        if root_win is not None:
            try:
                if root_win.winfo_exists():
                    self.root = tk.Toplevel(master=root_win)
                else:
                    self.root = tk.Tk()
            except Exception:
                self.root = tk.Tk()
        else:
            self.root = tk.Tk()
        self.lang = str(self.config_obj.get("language", "ru")).lower()
        if self.lang not in I18N:
            self.lang = "ru"

        self.t = I18N[self.lang]
        self.root.title(self.t["title"])
        self.root.geometry("640x560")
        self.root.minsize(580, 520)

        # Центрирование окна
        self._center_window(640, 560)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Модели данных
        self.game_dirs_list = list(self.config_obj.get("game_directories", []) or [])
        self.game_procs_list = list(self.config_obj.get("game_process_names", []))
        self.icon_style_var = tk.StringVar(master=self.root, value=str(self.config_obj.get("icon_style", "style_tile")))
        self.ui_scale_var = tk.DoubleVar(master=self.root, value=float(self.config_obj.get("ui_scale", 1.0)))
        self.ui_theme_var = tk.StringVar(master=self.root, value=str(self.config_obj.get("ui_theme", "cyber_dark")))
        self.language_var = tk.StringVar(master=self.root, value=self.lang)
        self.charge_limit_var = tk.IntVar(master=self.root, value=int(self.config_obj.get("battery_charge_limit", 60)))
        self.idle_timeout_var = tk.IntVar(master=self.root, value=int(self.config_obj.get("idle_timeout_seconds", 180) // 60))
        self.notify_var = tk.BooleanVar(master=self.root, value=bool(self.config_obj.get("notify_on_plan_change", True)))
        self.auto_switching_var = tk.BooleanVar(master=self.root, value=bool(self.config_obj.get("auto_switching_enabled", True)))

        self._build_ui()
        self.lift_to_front()

    def _center_window(self, width: int, height: int):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - width) // 2
        y = (sh - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def lift_to_front(self):
        """Выводит окно на передний план при повторном клике."""
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _on_close(self):
        SettingsWindow._instance = None
        self.root.destroy()

    def _build_ui(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # Вкладка 1: Игры
        tab_games = ttk.Frame(notebook)
        notebook.add(tab_games, text=self.t["tab_games"])
        self._build_tab_games(tab_games)

        # Вкладка 2: Внешний вид
        tab_appearance = ttk.Frame(notebook)
        notebook.add(tab_appearance, text=self.t["tab_appearance"])
        self._build_tab_appearance(tab_appearance)

        # Вкладка 3: Система и локализация
        tab_system = ttk.Frame(notebook)
        notebook.add(tab_system, text=self.t["tab_system"])
        self._build_tab_system(tab_system)

        # Нижняя панель кнопок
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=10)

        resume_auto_btn = ttk.Button(btn_frame, text=self.t.get("btn_resume_auto", "⚡ Возобновить авторежим"), command=self._resume_auto_mode)
        resume_auto_btn.pack(side="left", padx=5)

        save_btn = ttk.Button(btn_frame, text=self.t["btn_save"], command=self._on_save)
        save_btn.pack(side="right", padx=5)

        cancel_btn = ttk.Button(btn_frame, text=self.t["btn_cancel"], command=self._on_close)
        cancel_btn.pack(side="right", padx=5)

    def _build_tab_games(self, parent):
        # Каталоги
        lbl_dirs = ttk.Label(parent, text=self.t["game_dirs"], font=("Segoe UI", 9, "bold"))
        lbl_dirs.pack(anchor="w", padx=10, pady=(10, 5))

        dir_frame = ttk.Frame(parent)
        dir_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.dir_listbox = tk.Listbox(dir_frame, height=5)
        self.dir_listbox.pack(side="left", fill="both", expand=True)
        for d in self.game_dirs_list:
            self.dir_listbox.insert("end", d)

        dir_btn_frame = ttk.Frame(dir_frame)
        dir_btn_frame.pack(side="right", fill="y", padx=(5, 0))

        add_dir_btn = ttk.Button(dir_btn_frame, text=self.t["btn_add_dir"], command=self._add_directory)
        add_dir_btn.pack(fill="x", pady=2)

        del_dir_btn = ttk.Button(dir_btn_frame, text=self.t["btn_remove_dir"], command=self._remove_directory)
        del_dir_btn.pack(fill="x", pady=2)

        # Процессы
        lbl_procs = ttk.Label(parent, text=self.t["game_procs"], font=("Segoe UI", 9, "bold"))
        lbl_procs.pack(anchor="w", padx=10, pady=(15, 5))

        proc_frame = ttk.Frame(parent)
        proc_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.proc_listbox = tk.Listbox(proc_frame, height=5)
        self.proc_listbox.pack(side="left", fill="both", expand=True)
        for p in self.game_procs_list:
            self.proc_listbox.insert("end", p)

        proc_btn_frame = ttk.Frame(proc_frame)
        proc_btn_frame.pack(side="right", fill="y", padx=(5, 0))

        self.proc_entry = ttk.Entry(proc_btn_frame, width=18)
        self.proc_entry.pack(fill="x", pady=2)

        add_proc_btn = ttk.Button(proc_btn_frame, text=self.t["btn_add_proc"], command=self._add_process)
        add_proc_btn.pack(fill="x", pady=2)

        del_proc_btn = ttk.Button(proc_btn_frame, text=self.t["btn_remove_proc"], command=self._remove_process)
        del_proc_btn.pack(fill="x", pady=2)

    def _build_tab_appearance(self, parent):
        # Тема интерфейса
        lbl_theme = ttk.Label(parent, text=self.t["ui_theme"], font=("Segoe UI", 9, "bold"))
        lbl_theme.pack(anchor="w", padx=15, pady=(10, 4))

        theme_frame = ttk.Frame(parent)
        theme_frame.pack(anchor="w", padx=25, pady=2)
        ttk.Radiobutton(theme_frame, text=self.t["ui_theme_cyber"], variable=self.ui_theme_var, value="cyber_dark").pack(side="left", padx=5)
        ttk.Radiobutton(theme_frame, text=self.t["ui_theme_minimal"], variable=self.ui_theme_var, value="clean_minimalist").pack(side="left", padx=5)
        ttk.Radiobutton(theme_frame, text=self.t["ui_theme_oled"], variable=self.ui_theme_var, value="oled_contrast").pack(side="left", padx=5)
        ttk.Radiobutton(theme_frame, text=self.t.get("ui_theme_light", "Light Modern (Светлая)"), variable=self.ui_theme_var, value="light").pack(side="left", padx=5)

        # Масштаб интерфейса
        lbl_scale = ttk.Label(parent, text=self.t["ui_scale"], font=("Segoe UI", 9, "bold"))
        lbl_scale.pack(anchor="w", padx=15, pady=(10, 4))

        scale_frame = ttk.Frame(parent)
        scale_frame.pack(anchor="w", padx=25, pady=2)
        ttk.Radiobutton(scale_frame, text=self.t["ui_scale_100"], variable=self.ui_scale_var, value=1.0).pack(side="left", padx=5)
        ttk.Radiobutton(scale_frame, text=self.t["ui_scale_125"], variable=self.ui_scale_var, value=1.25).pack(side="left", padx=5)
        ttk.Radiobutton(scale_frame, text=self.t["ui_scale_150"], variable=self.ui_scale_var, value=1.5).pack(side="left", padx=5)

        # Стиль иконки трея
        lbl_style = ttk.Label(parent, text=self.t["icon_style"], font=("Segoe UI", 9, "bold"))
        lbl_style.pack(anchor="w", padx=15, pady=(12, 6))

        r0 = ttk.Radiobutton(parent, text=self.t.get("icon_style_tile", "🔲 Огромная (Сплошная плитка)"), variable=self.icon_style_var, value="style_tile")
        r0.pack(anchor="w", padx=25, pady=3)

        r4 = ttk.Radiobutton(parent, text=self.t.get("icon_style_d", "🚀 Увеличенный силуэт (Скорость)"), variable=self.icon_style_var, value="style_d")
        r4.pack(anchor="w", padx=25, pady=5)

        r1 = ttk.Radiobutton(parent, text=self.t["icon_style_a"], variable=self.icon_style_var, value="style_a")
        r1.pack(anchor="w", padx=25, pady=5)

        r2 = ttk.Radiobutton(parent, text=self.t["icon_style_b"], variable=self.icon_style_var, value="style_b")
        r2.pack(anchor="w", padx=25, pady=5)

        r3 = ttk.Radiobutton(parent, text=self.t["icon_style_c"], variable=self.icon_style_var, value="style_c")
        r3.pack(anchor="w", padx=25, pady=5)

        lbl_prev = ttk.Label(parent, text=self.t["preview"], font=("Segoe UI", 9, "italic"))
        lbl_prev.pack(anchor="w", padx=15, pady=(20, 5))

        self.preview_canvas = tk.Canvas(parent, width=128, height=128, bg="#1e1e1e", highlightthickness=1)
        self.preview_canvas.pack(anchor="w", padx=25, pady=5)
        self._draw_icon_preview()
        self.icon_style_var.trace_add("write", lambda *args: self._draw_icon_preview())

    def _draw_icon_preview(self):
        self.preview_canvas.delete("all")
        style = self.icon_style_var.get()
        if style in ("style_tile", "huge_tile"):
            # Огромная сплошная плитка (100% площади слота трея)
            self.preview_canvas.create_rectangle(14, 14, 114, 114, fill="#E84118", outline="#990000", width=3)
            self.preview_canvas.create_polygon(64, 26, 84, 58, 76, 92, 52, 92, 44, 58, fill="#FFFFFF", outline="#4A0E07", width=2)
            self.preview_canvas.create_oval(58, 48, 70, 60, fill="#00E5FF", outline="#FFFFFF", width=2)
            self.preview_canvas.create_polygon(64, 108, 52, 92, 64, 98, 76, 92, fill="#FFDD00")
            self.preview_canvas.create_text(64, 122, text="🔲 Сплошная плитка (100%)", fill="#FFFFFF", font=("Segoe UI", 8, "bold"))
        elif style == "style_a":
            # Неоновое кольцо
            self.preview_canvas.create_oval(24, 24, 104, 104, outline="#00ffcc", width=5)
            self.preview_canvas.create_polygon(64, 34, 50, 68, 64, 68, 60, 94, 78, 60, 64, 60, fill="#ffff00")
        elif style == "style_b":
            # Батарея
            self.preview_canvas.create_rectangle(34, 40, 94, 88, outline="#00e676", width=4)
            self.preview_canvas.create_rectangle(94, 54, 102, 74, fill="#00e676", outline="")
            self.preview_canvas.create_text(64, 64, text="80%", fill="#ffffff", font=("Segoe UI", 12, "bold"))
        elif style == "style_d":
            # Скорость и транспорт (Ракета)
            self.preview_canvas.create_polygon(64, 20, 84, 56, 76, 96, 52, 96, 44, 56, fill="#FF3838", outline="#570000", width=3)
            self.preview_canvas.create_oval(58, 48, 70, 60, fill="#00D2D3", outline="#FFFFFF", width=2)
            self.preview_canvas.create_text(64, 110, text="🚀 Скорость", fill="#FF4757", font=("Segoe UI", 9, "bold"))
        else:
            # Щит ASUS TUF
            self.preview_canvas.create_polygon(34, 30, 94, 30, 94, 74, 64, 104, 34, 74, outline="#ff9100", width=4, fill="#2a1b00")
            self.preview_canvas.create_text(64, 60, text="TUF", fill="#ff9100", font=("Segoe UI", 11, "bold"))

    def _build_tab_system(self, parent):
        # Язык
        lbl_lang = ttk.Label(parent, text=self.t["language"], font=("Segoe UI", 9, "bold"))
        lbl_lang.pack(anchor="w", padx=15, pady=(15, 5))

        lang_frame = ttk.Frame(parent)
        lang_frame.pack(anchor="w", padx=25, pady=2)
        r_ru = ttk.Radiobutton(lang_frame, text="Русский", variable=self.language_var, value="ru")
        r_ru.pack(side="left", padx=5)
        r_en = ttk.Radiobutton(lang_frame, text="English", variable=self.language_var, value="en")
        r_en.pack(side="left", padx=5)

        # Лимит батареи
        lbl_batt = ttk.Label(parent, text=self.t["charge_limit"], font=("Segoe UI", 9, "bold"))
        lbl_batt.pack(anchor="w", padx=15, pady=(15, 5))

        batt_frame = ttk.Frame(parent)
        batt_frame.pack(anchor="w", padx=25, pady=2)
        for lim in [60, 80, 100]:
            rb = ttk.Radiobutton(batt_frame, text=f"{lim}%", variable=self.charge_limit_var, value=lim)
            rb.pack(side="left", padx=8)

        lbl_batt_note = ttk.Label(parent, text=self.t.get("battery_note", ""), font=("Segoe UI", 8), wraplength=460, foreground="#555555")
        lbl_batt_note.pack(anchor="w", padx=25, pady=(2, 10))

        # Таймер простоя
        lbl_idle = ttk.Label(parent, text=self.t["idle_timeout"], font=("Segoe UI", 9, "bold"))
        lbl_idle.pack(anchor="w", padx=15, pady=(5, 5))

        idle_spin = ttk.Spinbox(parent, from_=1, to=60, textvariable=self.idle_timeout_var, width=10)
        idle_spin.pack(anchor="w", padx=25, pady=2)

        # Чекбокс авто-переключения планов
        chk_auto = ttk.Checkbutton(parent, text=self.t.get("auto_switching", "Включить авто-переключение планов питания (FSM правила)"), variable=self.auto_switching_var)
        chk_auto.pack(anchor="w", padx=15, pady=(10, 5))


        # Чекбокс уведомлений
        chk_notif = ttk.Checkbutton(parent, text=self.t["notify_change"], variable=self.notify_var)
        chk_notif.pack(anchor="w", padx=15, pady=(5, 5))

        # Разделитель и GitHub Token для приватных обновлений
        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=15, pady=10)

        lbl_token = ttk.Label(parent, text=self.t.get("github_token", "GitHub Token:"), font=("Segoe UI", 9, "bold"))
        lbl_token.pack(anchor="w", padx=15, pady=(5, 2))

        token_frame = ttk.Frame(parent)
        token_frame.pack(anchor="w", padx=25, pady=2, fill="x")

        self.token_entry = ttk.Entry(token_frame, width=28, show="*")
        curr_token = str(self.config_obj.get("github_token", ""))
        self.token_entry.insert(0, curr_token)
        self.token_entry.pack(side="left", padx=(0, 4))

        self.btn_toggle_eye = ttk.Button(token_frame, text="👁️", width=3, command=self._toggle_token_visibility)
        self.btn_toggle_eye.pack(side="left", padx=(0, 4))

        btn_paste = ttk.Button(token_frame, text=self.t.get("btn_paste", "📋 Вставить"), width=11, command=self._paste_clipboard_token)
        btn_paste.pack(side="left", padx=(0, 10))

        # Поддержка горячих клавиш вставки Ctrl+V на любой раскладке клавиатуры (RU / EN)
        def _on_key_paste(event=None):
            self._paste_clipboard_token()
            return "break"

        def _on_key_press(event):
            try:
                # event.state & 4 means Control modifier is active
                if event.state & 4:
                    # \x16 is ASCII SYN (Ctrl+V) on Windows regardless of keyboard layout
                    if event.char == "\x16" or getattr(event, "keysym", "").lower() in ("v", "m"):
                        return _on_key_paste(event)
            except Exception:
                pass

        try:
            self.token_entry.bind("<Key>", _on_key_press)
            self.token_entry.bind("<Control-v>", _on_key_paste)
            self.token_entry.bind("<Control-V>", _on_key_paste)
        except Exception as e:
            logger.debug(f"Key binding fallback: {e}")

        # Контекстное меню по правому клику мыши
        self.token_menu = tk.Menu(self.token_entry, tearoff=0)
        self.token_menu.add_command(label="Вставить", command=self._paste_clipboard_token)
        self.token_menu.add_command(label="Копировать", command=lambda: self._copy_to_clipboard(self.token_entry.get()))
        self.token_menu.add_command(label="Очистить", command=lambda: self.token_entry.delete(0, tk.END))
        self.token_entry.bind("<Button-3>", lambda event: self.token_menu.tk_popup(event.x_root, event.y_root))

        btn_check = ttk.Button(token_frame, text=self.t.get("btn_check_updates", "🔍 Проверить обновления"), command=self._check_updates_now)
        btn_check.pack(side="left")

        # Разделитель и управление службами ASUS (v0.2.56-beta)
        ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=15, pady=10)

        lbl_asus = ttk.Label(parent, text=self.t.get("asus_services_title", "Службы ASUS:"), font=("Segoe UI", 9, "bold"))
        lbl_asus.pack(anchor="w", padx=15, pady=(5, 2))

        asus_frame = ttk.Frame(parent)
        asus_frame.pack(anchor="w", padx=25, pady=2, fill="x")

        self.lbl_asus_status = ttk.Label(asus_frame, text="...", font=("Segoe UI", 8))
        self.lbl_asus_status.pack(side="left", padx=(0, 10))

        self.btn_toggle_asus = ttk.Button(asus_frame, text="...", command=self._toggle_asus_services)
        self.btn_toggle_asus.pack(side="left")

        self._refresh_asus_services_ui()


    def _refresh_asus_services_ui(self):
        try:
            from asus_services import AsusServiceManager
            status = AsusServiceManager.get_status()
            running = status.get("running_count", 0)
            installed = status.get("installed_count", 0)

            if installed == 0:
                self.lbl_asus_status.config(text=self.t.get("asus_services_none", "ℹ️ Службы ASUS не найдены"), foreground="#555555")
                self.btn_toggle_asus.config(state="disabled", text=self.t.get("btn_disable_asus_services", "🛑 Отключить"))
            elif running > 0:
                msg = self.t.get("asus_services_running", "⚠️ Работают службы ASUS: {count} шт.").format(count=running)
                self.lbl_asus_status.config(text=msg, foreground="#cc5500")
                self.btn_toggle_asus.config(state="normal", text=self.t.get("btn_disable_asus_services", "🛑 Отключить службы ASUS"))
            else:
                self.lbl_asus_status.config(text=self.t.get("asus_services_disabled", "✅ Службы ASUS отключены"), foreground="#008800")
                self.btn_toggle_asus.config(state="normal", text=self.t.get("btn_enable_asus_services", "🔄 Включить службы ASUS"))
        except Exception as e:
            logger.debug(f"Error checking ASUS services UI: {e}")
            if hasattr(self, "lbl_asus_status"):
                self.lbl_asus_status.config(text=f"Статус недоступен: {e}", foreground="#888888")

    def _toggle_asus_services(self):
        try:
            import threading
            import time
            from asus_services import AsusServiceManager
            status = AsusServiceManager.get_status()
            running = status.get("running_count", 0)
            action = "disable" if running > 0 else "enable"

            self.btn_toggle_asus.config(state="disabled")
            self.lbl_asus_status.config(text="⏳ Выполнение операции...", foreground="#888888")

            def _worker():
                try:
                    if action == "disable":
                        ok, msg = AsusServiceManager.disable_all()
                    else:
                        ok, msg = AsusServiceManager.enable_all()

                    # Poll up to 3.0s in background thread so elevated process finishes applying
                    if ok:
                        for _ in range(15):
                            time.sleep(0.2)
                            st = AsusServiceManager.get_status()
                            if action == "disable" and st.get("running_count", 0) == 0:
                                break
                            elif action == "enable" and st.get("running_count", 0) > 0:
                                break

                    self.root.after(0, lambda: self._on_toggle_completed(ok, msg, action))
                except Exception as ex:
                    self.root.after(0, lambda: self._on_toggle_completed(False, str(ex), action))

            threading.Thread(target=_worker, daemon=True).start()
        except Exception as e:
            logger.error(f"Failed to toggle ASUS services: {e}")
            self._refresh_asus_services_ui()
            messagebox.showerror("PowerMaster", f"Ошибка изменения служб: {e}", parent=self.root)

    def _on_toggle_completed(self, ok: bool, msg: str, action: str):
        self._refresh_asus_services_ui()
        if ok:
            succ_msg = self.t.get(
                "asus_services_disabled_success" if action == "disable" else "asus_services_enabled_success",
                "Операция со службами успешно завершена!"
            )
            messagebox.showinfo("PowerMaster", succ_msg, parent=self.root)
        else:
            messagebox.showwarning("PowerMaster", msg or "Операция отменена.", parent=self.root)

    def _paste_clipboard_token(self):
        try:
            clipboard_text = self.root.clipboard_get().strip()
            if clipboard_text:
                self.token_entry.delete(0, tk.END)
                self.token_entry.insert(0, clipboard_text)
        except Exception as e:
            logger.warning(f"Failed to paste from clipboard: {e}")

    def _toggle_token_visibility(self):
        if self.token_entry.cget("show") == "*":
            self.token_entry.configure(show="")
            self.btn_toggle_eye.configure(text="🔒")
        else:
            self.token_entry.configure(show="*")
            self.btn_toggle_eye.configure(text="👁️")

    def _copy_to_clipboard(self, text: str):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
        except Exception as e:
            logger.warning(f"Failed to copy to clipboard: {e}")

    def _check_updates_now(self):
        token = self.token_entry.get().strip()
        from config import APP_VERSION
        from updater import GitHubPrivateUpdater
        from update_dialog import show_update_dialog

        def _worker():
            updater = GitHubPrivateUpdater(current_version=APP_VERSION, token=token)
            has_update, rel_info, msg = updater.check_for_updates()
            if has_update and rel_info:
                self.root.after(0, lambda: show_update_dialog(updater, rel_info, on_complete_callback=self.on_quit_callback))
            else:
                self.root.after(0, lambda: messagebox.showinfo("PowerMaster", msg or "У вас установлена последняя версия!", parent=self.root))

        threading.Thread(target=_worker, daemon=True).start()

    def _add_directory(self):
        selected = filedialog.askdirectory(parent=self.root)
        if selected and selected not in self.game_dirs_list:
            norm_dir = os.path.normpath(selected)
            self.game_dirs_list.append(norm_dir)
            self.dir_listbox.insert("end", norm_dir)

    def _remove_directory(self):
        sel = self.dir_listbox.curselection()
        if sel:
            idx = sel[0]
            del self.game_dirs_list[idx]
            self.dir_listbox.delete(idx)

    def _add_process(self):
        proc_name = self.proc_entry.get().strip().lower()
        if proc_name and proc_name not in self.game_procs_list:
            if not proc_name.endswith(".exe"):
                proc_name += ".exe"
            self.game_procs_list.append(proc_name)
            self.proc_listbox.insert("end", proc_name)
            self.proc_entry.delete(0, "end")

    def _remove_process(self):
        sel = self.proc_listbox.curselection()
        if sel:
            idx = sel[0]
            del self.game_procs_list[idx]
            self.proc_listbox.delete(idx)

    def _on_save(self):
        # Сбор данных
        updated_data = {
            "game_directories": self.game_dirs_list,
            "game_process_names": self.game_procs_list,
            "icon_style": self.icon_style_var.get(),
            "ui_scale": float(self.ui_scale_var.get()),
            "ui_theme": str(self.ui_theme_var.get()),
            "language": self.language_var.get(),
            "battery_charge_limit": int(self.charge_limit_var.get()),
            "idle_timeout_seconds": int(self.idle_timeout_var.get() * 60),
            "notify_on_plan_change": bool(self.notify_var.get()),
            "auto_switching_enabled": bool(self.auto_switching_var.get()),
            "github_token": self.token_entry.get().strip() if hasattr(self, "token_entry") else "",
        }

        # Атомарное сохранение
        if hasattr(self.config_obj, "save_atomic"):
            self.config_obj.save_atomic(updated_data)
        else:
            for k, v in updated_data.items():
                self.config_obj.set(k, v)

        if self.on_save_callback:
            try:
                self.on_save_callback(updated_data)
            except Exception as e:
                logger.error(f"Error in on_save_callback: {e}")

        messagebox.showinfo("PowerMaster", self.t["saved_success"], parent=self.root)
        self._on_close()

    def _resume_auto_mode(self):
        """Сбрасывает ручные переопределения и возобновляет автоматический режим переключения планов."""
        try:
            self.config_obj.set("manual_override_guid", None)
            self.config_obj.set("auto_switching_enabled", True)
            if hasattr(self.config_obj, "save"):
                self.config_obj.save()
            if self.on_save_callback:
                try:
                    self.on_save_callback({"manual_override_guid": None, "auto_switching_enabled": True})
                except Exception as e:
                    logger.error(f"Error in on_save_callback during resume auto: {e}")
            msg = self.t.get("resumed_auto_msg", "Автоматический режим успешно возобновлен!\nРучные ограничения сброшены.")
            messagebox.showinfo("PowerMaster", msg, parent=self.root)
        except Exception as err:
            logger.error(f"Error resuming auto mode: {err}")
            messagebox.showerror("PowerMaster", f"Ошибка: {err}", parent=self.root)

import threading

def open_settings_window(config_obj, on_save_callback=None, on_quit_callback=None):
    """
    Глобальная потокобезопасная точка входа для открытия окна настроек.
    Если окно уже открыто, выводит его на передний план.
    Если Tkinter root уже работает в приложении (в дашборде),
    создает окно в том же Tkinter-потоке через root.after, избегая 'Calling Tcl from different apartment'.
    Если Tkinter root отсутствует, запускает собственный поток Tkinter mainloop.
    """
    if SettingsWindow._instance is not None:
        try:
            SettingsWindow._instance.root.after(0, SettingsWindow._instance.lift_to_front)
            return SettingsWindow._instance
        except Exception:
            SettingsWindow._instance = None

    root = getattr(tk, "_default_root", None)
    if root is not None:
        try:
            if root.winfo_exists():
                gui_thread_id = getattr(root, "_gui_thread_id", None)
                if (gui_thread_id is not None and threading.get_ident() == gui_thread_id) or threading.current_thread().name == "PowerMasterDashboardGUI":
                    win = SettingsWindow(config_obj, on_save_callback, on_quit_callback)
                    return win
                else:
                    root.after(0, lambda: SettingsWindow(config_obj, on_save_callback, on_quit_callback))
                    return None
        except Exception as e:
            logger.debug(f"Error checking active Tk root: {e}")

    def _tk_thread():
        try:
            win = SettingsWindow(config_obj, on_save_callback, on_quit_callback)
            win.root.mainloop()
        except Exception as e:
            logger.error(f"Error in Tkinter mainloop: {e}")
        finally:
            SettingsWindow._instance = None

    t = threading.Thread(target=_tk_thread, daemon=True, name="PowerMasterSettingsGUI")
    t.start()
    return t

