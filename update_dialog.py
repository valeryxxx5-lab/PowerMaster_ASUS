"""
Update Dialog Module for PowerMaster_ASUS (ТЗ-29).
Графическое окно уведомления о новом релизе с прогресс-баром скачивания на нативном Tkinter.
Strict Zero-Stub Policy. Production-ready implementation.
"""

from __future__ import annotations
import logging
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable
from updater import GitHubReleaseInfo, GitHubPrivateUpdater

logger = logging.getLogger("PowerMaster.UpdateDialog")

from config import config

try:
    from dashboard import THEMES
except Exception:
    THEMES = {
        "cyber_dark": {
            "name": "TUF Cyber Dark",
            "bg_main": "#1e1e2e",
            "bg_card": "#2b2b3b",
            "bg_card_inner": "#252535",
            "fg_main": "#cdd6f4",
            "fg_muted": "#a6adc8",
            "telemetry_val_fg": "#FDF6E2",
            "border": "#45475a",
            "accent": "#ff9f1c",
            "btn_bg": "#313244",
            "btn_active": "#45475a",
            "btn_fg": "#cdd6f4",
            "btn_accent_bg": "#89b4fa",
            "btn_accent_fg": "#1e1e2e",
        },
        "clean_minimalist": {
            "name": "Clean Minimalist",
            "bg_main": "#1e2022",
            "bg_card": "#2a2c31",
            "bg_card_inner": "#32353c",
            "fg_main": "#f8fafc",
            "fg_muted": "#94a3b8",
            "telemetry_val_fg": "#F4EFEA",
            "border": "#3f444e",
            "accent": "#388bfd",
            "btn_bg": "#373a40",
            "btn_active": "#4a4e56",
            "btn_fg": "#f8fafc",
            "btn_accent_bg": "#388bfd",
            "btn_accent_fg": "#ffffff",
        },
        "oled_contrast": {
            "name": "High-Contrast OLED",
            "bg_main": "#000000",
            "bg_card": "#0c0c0c",
            "bg_card_inner": "#161616",
            "fg_main": "#ffffff",
            "fg_muted": "#00ffff",
            "telemetry_val_fg": "#FFF8E7",
            "border": "#00ffff",
            "accent": "#00ffff",
            "btn_bg": "#1c1c1c",
            "btn_active": "#333333",
            "btn_fg": "#ffffff",
            "btn_accent_bg": "#00ffff",
            "btn_accent_fg": "#000000",
        },
    }

DIALOG_SCALES = {
    1.0: {"win_w": 540, "win_h": 450, "f_title": 12, "f_base": 9, "f_header": 10, "f_btn": 10},
    1.25: {"win_w": 650, "win_h": 530, "f_title": 14, "f_base": 11, "f_header": 12, "f_btn": 11},
    1.5: {"win_w": 750, "win_h": 610, "f_title": 16, "f_base": 13, "f_header": 14, "f_btn": 12},
}

class UpdateDialog:
    """
    Диалоговое окно обновления PowerMaster_ASUS с адаптивной темной темой.
    """
    _instance: Optional[UpdateDialog] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is not None:
            try:
                if hasattr(cls._instance, "root") and cls._instance.root.winfo_exists():
                    cls._instance.lift_to_front()
                    return cls._instance
            except Exception:
                pass
        instance = super().__new__(cls)
        cls._instance = instance
        return instance

    def lift_to_front(self):
        """Выводит окно обновления на передний план при повторном вызове."""
        try:
            if hasattr(self, "root") and self.root.winfo_exists():
                self.root.deiconify()
                self.root.lift()
                self.root.focus_force()
        except Exception:
            pass

    def __init__(
        self,
        updater: GitHubPrivateUpdater,
        release_info: GitHubReleaseInfo,
        on_complete_callback: Optional[Callable[[], None]] = None
    ):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True
        self.updater = updater
        self.release_info = release_info
        self.on_complete_callback = on_complete_callback

        theme_key = getattr(config, "ui_theme", "cyber_dark")
        self.theme = THEMES.get(theme_key, THEMES["cyber_dark"])
        ui_scale = getattr(config, "ui_scale", 1.0)
        self.scale_data = DIALOG_SCALES.get(ui_scale, DIALOG_SCALES[1.0])

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
        self.root.title("PowerMaster ASUS - Доступно обновление")

        w = self.scale_data["win_w"]
        h = self.scale_data["win_h"]
        self.root.geometry(f"{w}x{h}")
        self.root.minsize(int(w * 0.85), int(h * 0.85))
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._apply_theme()
        self._center_window(w, h)
        self._build_ui()

    def _apply_theme(self):
        t = self.theme
        s = self.scale_data
        try:
            self.root.configure(bg=t["bg_main"])
        except Exception:
            pass

        self.style = ttk.Style(self.root)
        try:
            self.style.theme_use("clam")
        except Exception:
            pass

        self.style.configure("UpdateMain.TFrame", background=t["bg_main"])
        self.style.configure("UpdateCard.TFrame", background=t["bg_card"], relief="flat")
        self.style.configure("UpdateInner.TFrame", background=t["bg_card_inner"], relief="flat")

        self.style.configure("UpdateTitle.TLabel", background=t["bg_main"], foreground=t["fg_main"], font=("Segoe UI", s["f_title"], "bold"))
        self.style.configure("UpdateSub.TLabel", background=t["bg_main"], foreground=t.get("fg_muted", "#888888"), font=("Segoe UI", s["f_base"]))
        self.style.configure("UpdateSection.TLabel", background=t["bg_main"], foreground=t.get("accent", t["fg_main"]), font=("Segoe UI", s["f_header"], "bold"))
        self.style.configure("UpdateStatus.TLabel", background=t["bg_main"], foreground=t.get("fg_muted", "#888888"), font=("Segoe UI", s["f_base"]))
        self.style.configure("UpdateIcon.TLabel", background=t["bg_main"], foreground=t["fg_main"], font=("Segoe UI Emoji", s["f_title"] + 12))

        self.style.configure("UpdateSec.TButton", background=t["btn_bg"], foreground=t["btn_fg"], font=("Segoe UI", s["f_btn"]), borderwidth=0, padding=6)
        self.style.map("UpdateSec.TButton", background=[("active", t.get("btn_active", "#45475a"))])

        self.style.configure("UpdateAccent.TButton", background=t["btn_accent_bg"], foreground=t["btn_accent_fg"], font=("Segoe UI", s["f_btn"], "bold"), borderwidth=0, padding=6)
        self.style.map("UpdateAccent.TButton", background=[("active", t.get("accent", "#388bfd"))])

        self.style.configure(
            "Update.Horizontal.TProgressbar",
            troughcolor=t["bg_card_inner"],
            background=t["accent"],
            bordercolor=t["border"],
            lightcolor=t["accent"],
            darkcolor=t["accent"]
        )

    def _center_window(self, width: int, height: int):
        self.root.update_idletasks()
        try:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
        except tk.TclError:
            return
        x = (sw - width) // 2
        y = (sh - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _build_ui(self):
        t = self.theme
        s = self.scale_data

        main_container = ttk.Frame(self.root, style="UpdateMain.TFrame", padding=15)
        main_container.pack(fill="both", expand=True)

        # Header Frame
        header_frame = ttk.Frame(main_container, style="UpdateMain.TFrame")
        header_frame.pack(fill="x", pady=(0, 10))

        lbl_icon = ttk.Label(header_frame, text="🚀", style="UpdateIcon.TLabel")
        lbl_icon.pack(side="left", padx=(0, 15))

        title_text = f"Доступна новая версия: v{self.release_info.version}"
        sub_text = f"Текущая версия: v{self.updater.current_version} • Размер: {self.release_info.asset_size / (1024*1024):.1f} MB"

        info_frame = ttk.Frame(header_frame, style="UpdateMain.TFrame")
        info_frame.pack(side="left", fill="both", expand=True)

        ttk.Label(info_frame, text=title_text, style="UpdateTitle.TLabel").pack(anchor="w")
        ttk.Label(info_frame, text=sub_text, style="UpdateSub.TLabel").pack(anchor="w", pady=(2, 0))

        # 2. Кнопки управления (Прижаты к самому низу side='bottom', гарантированно всегда видны)
        btn_frame = ttk.Frame(main_container, style="UpdateMain.TFrame")
        btn_frame.pack(side="bottom", fill="x", pady=(10, 0))

        self.update_btn = ttk.Button(btn_frame, text="Обновить сейчас", style="UpdateAccent.TButton", command=self._start_download)
        self.update_btn.pack(side="right", padx=(8, 0))

        self.later_btn = ttk.Button(btn_frame, text="Напомнить позже", style="UpdateSec.TButton", command=self._on_close)
        self.later_btn.pack(side="right")

        # 3. Прогресс-бар скачивания (Над кнопками)
        self.progress_frame = ttk.Frame(main_container, style="UpdateMain.TFrame")
        self.progress_frame.pack(side="bottom", fill="x", pady=(4, 6))

        self.progress_var = tk.DoubleVar(master=self.root, value=0.0)
        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            variable=self.progress_var,
            maximum=100.0,
            style="Update.Horizontal.TProgressbar"
        )
        self.progress_bar.pack(fill="x")

        self.status_lbl = ttk.Label(self.progress_frame, text="Готово к установке", style="UpdateStatus.TLabel")
        self.status_lbl.pack(anchor="w", pady=(4, 0))

        # 4. Заголовок описания релиза
        ttk.Label(main_container, text="Что нового в этой версии:", style="UpdateSection.TLabel").pack(side="top", anchor="w", pady=(5, 4))

        # 5. Описание релиза (Changelog Section) - заполняет все оставшееся место по центру
        txt_frame = ttk.Frame(main_container, style="UpdateMain.TFrame")
        txt_frame.pack(side="top", fill="both", expand=True, pady=(0, 6))

        self.changelog_text = tk.Text(
            txt_frame,
            wrap="word",
            height=6,
            bg=t["bg_card_inner"],
            fg=t["fg_main"],
            insertbackground=t["fg_main"],
            selectbackground=t["accent"],
            selectforeground=t["btn_accent_fg"],
            font=("Segoe UI", s["f_base"]),
            relief="flat",
            bd=0,
            padx=12,
            pady=10,
            highlightthickness=1,
            highlightbackground=t["border"],
            highlightcolor=t["accent"]
        )
        self.changelog_text.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(txt_frame, orient="vertical", command=self.changelog_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.changelog_text["yscrollcommand"] = scrollbar.set

        self._render_changelog(self.release_info.body)

        # Горячие клавиши: Enter для быстрого старта обновления, Esc для отмены
        self.root.bind("<Return>", lambda e: self._start_download())
        self.root.bind("<Escape>", lambda e: self._on_close())

    def _render_changelog(self, body_text: str):
        t = self.theme
        s = self.scale_data
        val_fg = t.get("telemetry_val_fg", "#FFF8E7")

        self.changelog_text.tag_configure("h1", font=("Segoe UI", s["f_header"] + 1, "bold"), foreground=t["accent"], spacing3=4)
        self.changelog_text.tag_configure("bullet", font=("Segoe UI", s["f_base"], "bold"), foreground=t["accent"])
        self.changelog_text.tag_configure("bold", font=("Segoe UI", s["f_base"], "bold"), foreground=val_fg)
        self.changelog_text.tag_configure("body", font=("Segoe UI", s["f_base"]), foreground=t["fg_main"])

        self.changelog_text.configure(state="normal")
        self.changelog_text.delete("1.0", tk.END)

        if not body_text:
            self.changelog_text.insert(tk.END, "Описание релиза отсутствует.", "body")
            self.changelog_text.configure(state="disabled")
            return

        import re
        lines = body_text.strip().splitlines()
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                self.changelog_text.insert(tk.END, "\n")
                continue

            # Header lines (# or ##)
            if line.startswith("#"):
                header_text = re.sub(r"^#+\s*", "", line)
                self.changelog_text.insert(tk.END, f"{header_text}\n", "h1")
                continue

            # Bullet points (- or *)
            if line.startswith(("- ", "* ")):
                self.changelog_text.insert(tk.END, "  • ", "bullet")
                content = line[2:]
            else:
                content = line

            # Parse markdown bold (**text**)
            parts = re.split(r"(\*\*.*?\*\*)", content)
            for part in parts:
                if part.startswith("**") and part.endswith("**") and len(part) >= 4:
                    self.changelog_text.insert(tk.END, part[2:-2], "bold")
                else:
                    self.changelog_text.insert(tk.END, part, "body")
            self.changelog_text.insert(tk.END, "\n")

        self.changelog_text.configure(state="disabled")

    def _start_download(self):
        self.update_btn.configure(state="disabled")
        self.later_btn.configure(state="disabled")
        self.status_lbl.configure(text="Подключение к защищенному серверу и скачивание...")

        # Скачивание в фоновом потоке
        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self):
        def progress(downloaded, total):
            if total > 0:
                pct = (downloaded / total) * 100.0
                mb_down = downloaded / (1024 * 1024)
                mb_tot = total / (1024 * 1024)
                self.root.after(0, lambda: self._update_progress(pct, f"Скачано: {mb_down:.1f} MB из {mb_tot:.1f} MB ({pct:.0f}%)"))

        ok, result = self.updater.download_installer(self.release_info, progress_callback=progress)
        if ok:
            installer_path = result
            self.root.after(0, lambda: self._on_download_complete(installer_path))
        else:
            err_msg = result
            self.root.after(0, lambda: self._on_download_error(err_msg))

    def _update_progress(self, pct: float, status_text: str):
        self.progress_var.set(pct)
        self.status_lbl.configure(text=status_text)

    def _on_download_complete(self, installer_path: str):
        self.status_lbl.configure(text="Загрузка завершена! Запуск установщика...")
        logger.info(f"Installer downloaded successfully to: {installer_path}")

        ok = self.updater.execute_inno_setup(installer_path, silent=True)
        if ok:
            self.status_lbl.configure(text="Установщик запущен!\nПриложение закроется и перезапустится автоматически...")
            self.update_btn.configure(state="disabled")
            self.later_btn.configure(state="disabled")
            # 1 секунда — показать статус пользователю и быстро освободить процесс/файлы
            self.root.after(1000, self._do_shutdown_and_exit)
        else:
            messagebox.showerror(
                "Ошибка обновления",
                f"Не удалось запустить установщик:\n{installer_path}\nЗапустите файл вручную.",
                parent=self.root,
            )
            self.update_btn.configure(state="normal")
            self.later_btn.configure(state="normal")

    def _do_shutdown_and_exit(self):
        try:
            self._on_close()
        except Exception:
            pass
        if self.on_complete_callback:
            try:
                self.on_complete_callback()
            except Exception as e:
                logger.error(f"Error in on_complete_callback: {e}")
        # Гарантированное завершение через 1.5 сек для полного освобождения ресурсов и файлов
        def _force_exit():
            import time, os
            time.sleep(1.5)
            try:
                os._exit(0)
            except Exception:
                pass
        threading.Thread(target=_force_exit, daemon=True, name="PowerMasterUpdateExitWatcher").start()

    def _on_download_error(self, err_msg: str):
        self.status_lbl.configure(text="Ошибка загрузки.")
        messagebox.showerror("Ошибка обновления", err_msg, parent=self.root)
        self.update_btn.configure(state="normal")
        self.later_btn.configure(state="normal")

    def _on_close(self):
        UpdateDialog._instance = None
        try:
            self.root.destroy()
        except Exception:
            pass


def show_update_dialog(updater, release_info, on_complete_callback=None):
    """Глобальная функция запуска окна обновления в безопасном GUI-контексте."""
    if UpdateDialog._instance is not None:
        try:
            if hasattr(UpdateDialog._instance, "root") and UpdateDialog._instance.root.winfo_exists():
                root = getattr(tk, "_default_root", None)
                if root is not None and root.winfo_exists():
                    root.after(0, UpdateDialog._instance.lift_to_front)
                else:
                    UpdateDialog._instance.lift_to_front()
                return None
        except Exception:
            UpdateDialog._instance = None

    root = getattr(tk, "_default_root", None)
    if root is not None:
        try:
            if root.winfo_exists():
                root.after(0, lambda: UpdateDialog(updater, release_info, on_complete_callback))
                return None
        except Exception:
            pass

    def _dialog_thread():
        try:
            dlg = UpdateDialog(updater, release_info, on_complete_callback)
            dlg.root.mainloop()
        except Exception as e:
            logger.error(f"Error in UpdateDialog mainloop: {e}")
        finally:
            UpdateDialog._instance = None
    t = threading.Thread(target=_dialog_thread, daemon=False, name="PowerMasterUpdateGUI")
    t.start()
    return t
