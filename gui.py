import os
import sys
import threading
import time
from tkinter import filedialog
import customtkinter as ctk
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item

import core

# Настройка внешнего вида CustomTkinter
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


def create_tray_image(connected: bool = False) -> Image.Image:
    """Создает миниатюрную иконку для трея."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    bg = (24, 28, 36)
    accent = (46, 204, 113) if connected else (120, 140, 160)
    draw.ellipse([4, 4, 60, 60], fill=bg, outline=accent, width=4)
    draw.ellipse([20, 20, 44, 44], fill=accent)
    return img


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("ProxyFork - System-wide TUN Proxy")
        self.geometry("520x680")
        self.resizable(False, False)

        icon_path = core.ICON_PATH
        if os.path.exists(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

        self.proxy_mgr = core.ProxyManager()
        self.settings = core.load_settings()
        self.excluded_processes = list(self.settings.get("excluded_processes", []))
        self.is_connected = False
        self.connected_time = None
        self.tray_icon = None
        self.password_visible = False

        self._build_ui()
        self._load_saved_values()
        self._refresh_exclusions_ui()

        # Запуск таймера аптайма
        self._tick_timer()

        # Запуск иконки в трее в фоновом потоке
        self._init_tray()

        # Проверка исходного IP
        threading.Thread(target=self._update_ip_display, daemon=True).start()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        # Главный контейнер
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#14171d")
        self.main_frame.pack(fill="both", expand=True)

        # 1. Заголовок и статус (всегда наверху)
        header_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(16, 8))

        title_label = ctk.CTkLabel(
            header_frame,
            text="ProxyFork",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#ffffff"
        )
        title_label.pack(anchor="w")

        subtitle_label = ctk.CTkLabel(
            header_frame,
            text="Проксирование системы (L3 TUN / Wintun) + Исключения процессов",
            font=ctk.CTkFont(size=12),
            text_color="#8b949e"
        )
        subtitle_label.pack(anchor="w")

        # Плашка статуса
        self.status_badge = ctk.CTkFrame(self.main_frame, fg_color="#1c2128", corner_radius=10)
        self.status_badge.pack(fill="x", padx=20, pady=(0, 10))

        self.status_dot = ctk.CTkLabel(
            self.status_badge,
            text="●",
            font=ctk.CTkFont(size=16),
            text_color="#8b949e"
        )
        self.status_dot.pack(side="left", padx=(12, 6), pady=6)

        self.status_text = ctk.CTkLabel(
            self.status_badge,
            text="Отключено",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#c9d1d9"
        )
        self.status_text.pack(side="left", pady=6)

        self.timer_label = ctk.CTkLabel(
            self.status_badge,
            text="⏱️ 00:00:00",
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            text_color="#8b949e"
        )
        self.timer_label.pack(side="right", padx=(4, 12), pady=6)

        self.proto_badge = ctk.CTkLabel(
            self.status_badge,
            text="SOCKS5 + TUN",
            font=ctk.CTkFont(size=11),
            text_color="#58a6ff"
        )
        self.proto_badge.pack(side="right", padx=(8, 4), pady=6)

        # 2. Вкладки (Подключение / Исключения)
        self.tabview = ctk.CTkTabview(
            self.main_frame,
            fg_color="#1c2128",
            segmented_button_fg_color="#262c36",
            segmented_button_selected_color="#1f6feb",
            segmented_button_selected_hover_color="#388bfd"
        )
        self.tabview.pack(fill="both", expand=True, padx=20, pady=(0, 14))

        self.tab_conn = self.tabview.add("Подключение")
        self.tab_excl = self.tabview.add("Исключения (Bypass)")

        self._build_conn_tab()
        self._build_excl_tab()

    def _build_conn_tab(self):
        # Карточка настроек
        card = ctk.CTkFrame(self.tab_conn, fg_color="#161b22", corner_radius=10)
        card.pack(fill="x", padx=8, pady=(8, 10))

        # Хост и Порт
        hp_frame = ctk.CTkFrame(card, fg_color="transparent")
        hp_frame.pack(fill="x", padx=14, pady=(10, 4))

        h_box = ctk.CTkFrame(hp_frame, fg_color="transparent")
        h_box.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkLabel(h_box, text="Хост / IP:", font=ctk.CTkFont(size=12), text_color="#8b949e").pack(anchor="w")
        self.host_entry = ctk.CTkEntry(h_box, placeholder_text="194.87.x.x или домен", height=32)
        self.host_entry.pack(fill="x", pady=(2, 0))

        p_box = ctk.CTkFrame(hp_frame, fg_color="transparent")
        p_box.pack(side="right")
        ctk.CTkLabel(p_box, text="Порт:", font=ctk.CTkFont(size=12), text_color="#8b949e").pack(anchor="w")
        self.port_entry = ctk.CTkEntry(p_box, placeholder_text="1080", width=85, height=32)
        self.port_entry.pack(pady=(2, 0))

        # Логин
        u_box = ctk.CTkFrame(card, fg_color="transparent")
        u_box.pack(fill="x", padx=14, pady=4)
        ctk.CTkLabel(u_box, text="Логин (если требуется):", font=ctk.CTkFont(size=12), text_color="#8b949e").pack(anchor="w")
        self.user_entry = ctk.CTkEntry(u_box, placeholder_text="username", height=32)
        self.user_entry.pack(fill="x", pady=(2, 0))

        # Пароль
        pw_box = ctk.CTkFrame(card, fg_color="transparent")
        pw_box.pack(fill="x", padx=14, pady=(4, 10))
        ctk.CTkLabel(pw_box, text="Пароль:", font=ctk.CTkFont(size=12), text_color="#8b949e").pack(anchor="w")

        pw_row = ctk.CTkFrame(pw_box, fg_color="transparent")
        pw_row.pack(fill="x", pady=(2, 0))

        self.pass_entry = ctk.CTkEntry(pw_row, placeholder_text="password", show="●", height=32)
        self.pass_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.toggle_pass_btn = ctk.CTkButton(
            pw_row,
            text="👁",
            width=36,
            height=32,
            fg_color="#30363d",
            hover_color="#3c444d",
            command=self._toggle_password_visibility
        )
        self.toggle_pass_btn.pack(side="right")

        # Чекбокс трея
        self.tray_checkbox = ctk.CTkCheckBox(
            self.tab_conn,
            text="Сворачивать в системный трей при закрытии",
            font=ctk.CTkFont(size=12),
            text_color="#c9d1d9"
        )
        self.tray_checkbox.pack(anchor="w", padx=10, pady=(0, 10))

        # Кнопка ПОДКЛЮЧИТЬ
        self.connect_btn = ctk.CTkButton(
            self.tab_conn,
            text="ПОДКЛЮЧИТЬ",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=42,
            corner_radius=8,
            fg_color="#238636",
            hover_color="#2ea043",
            command=self._toggle_connection
        )
        self.connect_btn.pack(fill="x", padx=8, pady=(0, 10))

        # Карточка IP
        ip_card = ctk.CTkFrame(self.tab_conn, fg_color="#161b22", corner_radius=8)
        ip_card.pack(fill="x", padx=8, pady=(0, 8))

        ip_inner = ctk.CTkFrame(ip_card, fg_color="transparent")
        ip_inner.pack(fill="x", padx=12, pady=8)

        ip_left = ctk.CTkFrame(ip_inner, fg_color="transparent")
        ip_left.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            ip_left,
            text="ВНЕШНИЙ IP СИСТЕМЫ",
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color="#8b949e"
        ).pack(anchor="w")

        self.ip_value_label = ctk.CTkLabel(
            ip_left,
            text="Определение...",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#58a6ff"
        )
        self.ip_value_label.pack(anchor="w")

        self.refresh_ip_btn = ctk.CTkButton(
            ip_inner,
            text="🔄",
            width=34,
            height=30,
            fg_color="#30363d",
            hover_color="#3c444d",
            command=lambda: threading.Thread(target=self._update_ip_display, daemon=True).start()
        )
        self.refresh_ip_btn.pack(side="right")

        # Логи
        ctk.CTkLabel(
            self.tab_conn,
            text="Журнал работы",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#8b949e"
        ).pack(anchor="w", padx=10, pady=(2, 2))

        self.log_textbox = ctk.CTkTextbox(
            self.tab_conn,
            height=90,
            font=ctk.CTkFont(family="Consolas", size=10),
            fg_color="#0d1117",
            text_color="#8b949e",
            corner_radius=6
        )
        self.log_textbox.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        self.log_textbox.configure(state="disabled")

    def _build_excl_tab(self):
        # Вкладка Исключения
        desc_label = ctk.CTkLabel(
            self.tab_excl,
            text="Трафик указанных приложений пойдет напрямую (мимо прокси):",
            font=ctk.CTkFont(size=12),
            text_color="#8b949e"
        )
        desc_label.pack(anchor="w", padx=10, pady=(6, 8))

        # Строка ввода
        add_frame = ctk.CTkFrame(self.tab_excl, fg_color="transparent")
        add_frame.pack(fill="x", padx=10, pady=(0, 8))

        self.excl_entry = ctk.CTkEntry(
            add_frame,
            placeholder_text="Имя процесса (напр. telegram.exe)",
            height=34
        )
        self.excl_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.excl_entry.bind("<Return>", lambda e: self._add_manual_exclusion())

        browse_btn = ctk.CTkButton(
            add_frame,
            text="Обзор...",
            width=65,
            height=34,
            fg_color="#30363d",
            hover_color="#3c444d",
            command=self._browse_and_add_exe
        )
        browse_btn.pack(side="left", padx=(0, 6))

        add_btn = ctk.CTkButton(
            add_frame,
            text="+ Добавить",
            width=85,
            height=34,
            fg_color="#1f6feb",
            hover_color="#388bfd",
            command=self._add_manual_exclusion
        )
        add_btn.pack(side="right")

        # Быстрые кнопки добавления популярных приложений
        quick_frame = ctk.CTkFrame(self.tab_excl, fg_color="transparent")
        quick_frame.pack(fill="x", padx=10, pady=(0, 10))

        quick_apps = [
            ("Telegram", "telegram.exe"),
            ("Discord", "discord.exe"),
            ("Steam", "steam.exe"),
            ("Torrent", "qbittorrent.exe")
        ]
        for label, proc in quick_apps:
            btn = ctk.CTkButton(
                quick_frame,
                text=f"+ {label}",
                width=80,
                height=26,
                font=ctk.CTkFont(size=11),
                fg_color="#21262d",
                hover_color="#30363d",
                text_color="#c9d1d9",
                command=lambda p=proc: self._add_exclusion(p)
            )
            btn.pack(side="left", padx=(0, 6))

        # Список добавленных исключений (ScrollableFrame)
        self.excl_scroll = ctk.CTkScrollableFrame(
            self.tab_excl,
            fg_color="#161b22",
            corner_radius=8
        )
        self.excl_scroll.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        # Нижняя панель с кнопкой очистки
        footer_frame = ctk.CTkFrame(self.tab_excl, fg_color="transparent")
        footer_frame.pack(fill="x", padx=10, pady=(0, 4))

        self.excl_count_label = ctk.CTkLabel(
            footer_frame,
            text="Исключений: 0",
            font=ctk.CTkFont(size=12),
            text_color="#8b949e"
        )
        self.excl_count_label.pack(side="left")

        self.apply_excl_btn = ctk.CTkButton(
            footer_frame,
            text="🔄 Применить сейчас",
            width=150,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#1f6feb",
            hover_color="#388bfd",
            command=self._apply_exclusions_live
        )
        self.apply_excl_btn.pack(side="right", padx=(6, 0))

        clear_btn = ctk.CTkButton(
            footer_frame,
            text="Очистить всё",
            width=90,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="#30363d",
            hover_color="#da3633",
            command=self._clear_all_exclusions
        )
        clear_btn.pack(side="right")

    def _browse_and_add_exe(self):
        path = filedialog.askopenfilename(
            title="Выберите исполняемый файл приложения",
            filetypes=[("Исполняемые файлы", "*.exe"), ("Все файлы", "*.*")]
        )
        if path:
            filename = os.path.basename(path)
            self._add_exclusion(filename)

    def _add_manual_exclusion(self):
        val = self.excl_entry.get().strip()
        if val:
            self._add_exclusion(val)
            self.excl_entry.delete(0, "end")

    def _add_exclusion(self, proc_name: str):
        proc_name = proc_name.strip()
        if not proc_name:
            return
        if not proc_name.lower().endswith(".exe"):
            proc_name += ".exe"

        proc_lower = proc_name.lower()
        if proc_lower not in [p.lower() for p in self.excluded_processes]:
            self.excluded_processes.append(proc_name)
            self._save_current_values()
            self._refresh_exclusions_ui()
            self.log(f"Добавлено исключение: {proc_name}")
            if self.is_connected:
                self.log("💡 Нажмите '🔄 Применить сейчас' внизу вкладки для обновления правил.")

    def _remove_exclusion(self, proc_name: str):
        self.excluded_processes = [p for p in self.excluded_processes if p.lower() != proc_name.lower()]
        self._save_current_values()
        self._refresh_exclusions_ui()
        self.log(f"Удалено исключение: {proc_name}")
        if self.is_connected:
            self.log("💡 Нажмите '🔄 Применить сейчас' для применения изменений.")

    def _apply_exclusions_live(self):
        self._save_current_values()
        if not self.is_connected:
            self.log("Исключения сохранены. Они будут активны при следующем подключении.")
            return

        self.log("--- Перезапуск туннеля для применения обновленных исключений ---")
        self.connect_btn.configure(state="disabled", text="ПРИМЕНЕНИЕ...")
        self.apply_excl_btn.configure(state="disabled", text="Применение...")
        self._set_status("connecting", "Обновление правил...")

        def _bg_reload():
            self.proxy_mgr.stop()
            time.sleep(0.4)
            host = self.host_entry.get().strip()
            port = int(self.port_entry.get().strip())
            user = self.user_entry.get().strip()
            pwd = self.pass_entry.get().strip()
            ok, msg = self.proxy_mgr.start(
                host=host,
                port=port,
                username=user,
                password=pwd,
                excluded_processes=self.excluded_processes,
                log_cb=self.log
            )
            if ok:
                self.is_connected = True
                self._set_status("connected", "Подключено (Вся система)")
                self.after(0, lambda: self.connect_btn.configure(
                    state="normal",
                    text="ОТКЛЮЧИТЬ",
                    fg_color="#da3633",
                    hover_color="#b62324"
                ))
                self.after(0, lambda: self.apply_excl_btn.configure(
                    state="normal",
                    text="🔄 Применить сейчас"
                ))
                self.log("Новые исключения успешно применены! Трафик перенаправлен.")
            else:
                self.is_connected = False
                self.connected_time = None
                self._set_status("error", "Ошибка перезапуска")
                self.after(0, lambda: self.connect_btn.configure(
                    state="normal",
                    text="ПОДКЛЮЧИТЬ",
                    fg_color="#238636",
                    hover_color="#2ea043"
                ))
                self.after(0, lambda: self.apply_excl_btn.configure(
                    state="normal",
                    text="🔄 Применить сейчас"
                ))
                self.log(f"Ошибка перезапуска: {msg}")

        threading.Thread(target=_bg_reload, daemon=True).start()

    def _clear_all_exclusions(self):
        if not self.excluded_processes:
            return
        self.excluded_processes.clear()
        self._save_current_values()
        self._refresh_exclusions_ui()
        self.log("Список исключений полностью очищен.")

    def _refresh_exclusions_ui(self):
        for widget in self.excl_scroll.winfo_children():
            widget.destroy()

        count = len(self.excluded_processes)
        self.excl_count_label.configure(text=f"Исключений: {count}")

        if not self.excluded_processes:
            empty_lbl = ctk.CTkLabel(
                self.excl_scroll,
                text="Список пуст — весь трафик ПК проксируется.",
                font=ctk.CTkFont(size=12),
                text_color="#6e7681"
            )
            empty_lbl.pack(pady=30)
            return

        for proc in self.excluded_processes:
            row = ctk.CTkFrame(self.excl_scroll, fg_color="#21262d", corner_radius=6, height=36)
            row.pack(fill="x", pady=2, padx=2)

            name_lbl = ctk.CTkLabel(
                row,
                text=f"  🛡️ {proc}",
                font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
                text_color="#c9d1d9"
            )
            name_lbl.pack(side="left", padx=8, pady=4)

            del_btn = ctk.CTkButton(
                row,
                text="✕",
                width=28,
                height=26,
                font=ctk.CTkFont(size=12, weight="bold"),
                fg_color="transparent",
                hover_color="#da3633",
                text_color="#8b949e",
                command=lambda p=proc: self._remove_exclusion(p)
            )
            del_btn.pack(side="right", padx=6, pady=4)

    def _toggle_password_visibility(self):
        self.password_visible = not self.password_visible
        if self.password_visible:
            self.pass_entry.configure(show="")
            self.toggle_pass_btn.configure(text="🔒")
        else:
            self.pass_entry.configure(show="●")
            self.toggle_pass_btn.configure(text="👁")

    def _load_saved_values(self):
        self.host_entry.insert(0, self.settings.get("host", ""))
        self.port_entry.insert(0, str(self.settings.get("port", "1080")))
        self.user_entry.insert(0, self.settings.get("username", ""))
        self.pass_entry.insert(0, self.settings.get("password", ""))

        if self.settings.get("minimize_to_tray", True):
            self.tray_checkbox.select()
        else:
            self.tray_checkbox.deselect()

    def _save_current_values(self):
        self.settings["host"] = self.host_entry.get().strip()
        self.settings["port"] = self.port_entry.get().strip() or "1080"
        self.settings["username"] = self.user_entry.get().strip()
        self.settings["password"] = self.pass_entry.get().strip()
        self.settings["minimize_to_tray"] = bool(self.tray_checkbox.get())
        self.settings["excluded_processes"] = list(self.excluded_processes)
        core.save_settings(self.settings)

    def log(self, text: str):
        def _append():
            self.log_textbox.configure(state="normal")
            self.log_textbox.insert("end", text + "\n")
            self.log_textbox.see("end")
            self.log_textbox.configure(state="disabled")
        self.after(0, _append)

    def _update_ip_display(self):
        self.after(0, lambda: self.ip_value_label.configure(text="Определение...", text_color="#8b949e"))
        info = core.get_current_ip()
        if info["success"]:
            loc_str = f" ({info['location']})" if info['location'] else ""
            txt = f"{info['ip']}{loc_str}"
            color = "#2ea043" if self.is_connected else "#58a6ff"
            self.after(0, lambda: self.ip_value_label.configure(text=txt, text_color=color))
        else:
            self.after(0, lambda: self.ip_value_label.configure(text="Не удалось получить", text_color="#f85149"))

    def _set_status(self, state: str, text: str):
        color_map = {
            "disconnected": ("#8b949e", "#c9d1d9"),
            "connecting": ("#d29922", "#e3b341"),
            "connected": ("#2ea043", "#3fb950"),
            "error": ("#f85149", "#ff7b72")
        }
        dot_color, text_color = color_map.get(state, ("#8b949e", "#c9d1d9"))

        def _apply():
            self.status_dot.configure(text_color=dot_color)
            self.status_text.configure(text=text, text_color=text_color)
            if self.tray_icon:
                self.tray_icon.icon = create_tray_image(self.is_connected)
        self.after(0, _apply)

    def _toggle_connection(self):
        if self.is_connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        host = self.host_entry.get().strip()
        port_str = self.port_entry.get().strip()
        user = self.user_entry.get().strip()
        passwd = self.pass_entry.get().strip()

        if not host:
            self._set_status("error", "Укажите Хост / IP")
            return

        try:
            port = int(port_str)
        except ValueError:
            self._set_status("error", "Неверный порт")
            return

        self._save_current_values()

        self.connect_btn.configure(state="disabled", text="ПОДКЛЮЧЕНИЕ...")
        self._set_status("connecting", "Подключение TUN...")
        excl_count = len(self.excluded_processes)
        self.log(f"--- Запуск подключения к {host}:{port} (Исключений: {excl_count}) ---")

        def _bg_connect():
            success, msg = self.proxy_mgr.start(
                host=host,
                port=port,
                username=user,
                password=passwd,
                excluded_processes=self.excluded_processes,
                log_cb=self.log
            )
            if success:
                self.is_connected = True
                self.connected_time = time.time()
                self._set_status("connected", "Подключено (Вся система)")
                self.after(0, lambda: self.connect_btn.configure(
                    state="normal",
                    text="ОТКЛЮЧИТЬ",
                    fg_color="#da3633",
                    hover_color="#b62324"
                ))
                self.log("TUN интерфейс активирован. Трафик перенаправлен.")
                self._update_ip_display()
            else:
                self.is_connected = False
                self.connected_time = None
                self._set_status("error", "Ошибка запуска")
                self.after(0, lambda: self.connect_btn.configure(
                    state="normal",
                    text="ПОДКЛЮЧИТЬ",
                    fg_color="#238636",
                    hover_color="#2ea043"
                ))
                self.log(f"Ошибка: {msg}")

        threading.Thread(target=_bg_connect, daemon=True).start()

    def _disconnect(self):
        self.connect_btn.configure(state="disabled", text="ОТКЛЮЧЕНИЕ...")
        self._set_status("connecting", "Отключение TUN...")
        self.log("--- Отключение прокси ---")

        def _bg_disconnect():
            self.proxy_mgr.stop()
            self.is_connected = False
            self.connected_time = None
            self._set_status("disconnected", "Отключено")
            self.after(0, lambda: self.connect_btn.configure(
                state="normal",
                text="ПОДКЛЮЧИТЬ",
                fg_color="#238636",
                hover_color="#2ea043"
            ))
            self.log("TUN интерфейс отключен. Исходные маршруты восстановлены.")
            self._update_ip_display()

        threading.Thread(target=_bg_disconnect, daemon=True).start()

    def _tick_timer(self):
        try:
            if self.is_connected and self.connected_time:
                elapsed = int(time.time() - self.connected_time)
                h = elapsed // 3600
                m = (elapsed % 3600) // 60
                s = elapsed % 60
                time_str = f"⏱️ {h:02d}:{m:02d}:{s:02d}"
                self.timer_label.configure(text=time_str, text_color="#3fb950")
                if self.tray_icon:
                    self.tray_icon.title = f"ProxyFork ({h:02d}:{m:02d}:{s:02d})"
            else:
                self.timer_label.configure(text="⏱️ 00:00:00", text_color="#8b949e")
                if self.tray_icon:
                    self.tray_icon.title = "ProxyFork (Отключено)"
        except Exception:
            pass
        self.after(1000, self._tick_timer)

    def _init_tray(self):
        menu = pystray.Menu(
            item("Показать окно", self._show_window, default=True),
            item("Вкл / Выкл", self._tray_toggle_connection),
            pystray.Menu.SEPARATOR,
            item("Выход", self._quit_app)
        )
        self.tray_icon = pystray.Icon("ProxyFork", create_tray_image(False), "ProxyFork", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _show_window(self, icon=None, item=None):
        self.after(0, self.deiconify)
        self.after(0, self.lift)
        self.after(0, self.focus_force)

    def _tray_toggle_connection(self, icon=None, item=None):
        self.after(0, self._toggle_connection)

    def _on_close(self):
        if self.tray_checkbox.get():
            self.withdraw()
        else:
            self._quit_app()

    def _quit_app(self, icon=None, item=None):
        self._save_current_values()
        if self.proxy_mgr.is_running:
            self.proxy_mgr.stop()
        if self.tray_icon:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.after(0, self.destroy)
