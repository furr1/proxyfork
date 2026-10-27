import os
import sys
import json
import ctypes
import subprocess
import threading
import time
import re
import requests

if getattr(sys, 'frozen', False):
    BUNDLE_DIR = sys._MEIPASS
    EXE_DIR = os.path.dirname(sys.executable)
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    EXE_DIR = BUNDLE_DIR

APP_DIR = EXE_DIR

# Поиск директории с бинарниками (внутри бандла или рядом с exe)
BIN_DIR = os.path.join(BUNDLE_DIR, "bin")
if not os.path.exists(BIN_DIR) or not os.path.exists(os.path.join(BIN_DIR, "sing-box.exe")):
    BIN_DIR = os.path.join(EXE_DIR, "bin")

SING_BOX_EXE = os.path.join(BIN_DIR, "sing-box.exe")

# Иконка
ICON_PATH = os.path.join(BUNDLE_DIR, "icon.ico")
if not os.path.exists(ICON_PATH):
    ICON_PATH = os.path.join(EXE_DIR, "icon.ico")

# Директория для хранения настроек в C:\Program Files\ProxyFork
DATA_DIR = r"C:\Program Files\ProxyFork"
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")


def ensure_data_dir():
    """Создает директорию настроек при наличии прав."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except Exception:
        pass


def is_admin() -> bool:
    """Проверяет наличие прав администратора."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def request_admin():
    """Перезапускает текущую программу с запросом UAC в правильной рабочей директории."""
    if getattr(sys, 'frozen', False):
        exe = sys.executable
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
        ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, EXE_DIR, 1)
    else:
        script = os.path.abspath(sys.argv[0])
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, f'"{script}" {params}', EXE_DIR, 1)
    sys.exit(0)


def load_settings() -> dict:
    r"""Загружает сохраненные настройки прокси из C:\Program Files\ProxyFork (с миграцией)."""
    default_settings = {
        "host": "",
        "port": "1080",
        "username": "",
        "password": "",
        "auto_connect": False,
        "minimize_to_tray": True,
        "excluded_processes": []
    }

    ensure_data_dir()

    # Если в C:\Program Files\ProxyFork файла еще нет, проверяем резервные места
    if not os.path.exists(SETTINGS_PATH):
        candidates = [
            os.path.join(os.environ.get("APPDATA", ""), "ProxyFork", "settings.json"),
            os.path.join(EXE_DIR, "settings.json"),
            os.path.join(EXE_DIR, "dist", "settings.json")
        ]
        for c in candidates:
            if c and os.path.exists(c):
                try:
                    with open(c, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        default_settings.update(data)
                    save_settings(default_settings)
                    break
                except Exception:
                    pass

    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_settings.update(data)
        except Exception:
            pass
    return default_settings


def save_settings(settings: dict):
    r"""Сохраняет настройки в JSON в C:\Program Files\ProxyFork."""
    ensure_data_dir()
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving settings: {e}")


def generate_sing_box_config(host: str, port: int, username: str = "", password: str = "", excluded_processes: list = None) -> dict:
    """Генерирует конфигурацию sing-box 1.14 для TUN режима со всеми приложениями, UDP и списком исключений."""
    
    socks_outbound = {
        "type": "socks",
        "tag": "proxy-out",
        "server": host.strip(),
        "server_port": int(port),
        "tcp_keep_alive": "15s"
    }
    if username.strip():
        socks_outbound["username"] = username.strip()
    if password.strip():
        socks_outbound["password"] = password.strip()

    # Формируем правила маршрутизации
    route_rules = [
        {
            # Перехват всех DNS-запросов (порт 53) и обработка встроенным DNS
            "port": 53,
            "action": "hijack-dns"
        },
        {
            # Отклоняем IPv6, так как прокси поддерживает только IPv4
            # (предотвращает зависание Telegram и браузеров, которые пытаются идти через IPv6)
            "ip_version": 6,
            "action": "reject"
        },
        {
            # Отклоняем QUIC (UDP 443) в браузерах, чтобы они мгновенно переключались на быстрый TCP
            # без 3-5 секундных таймаутов на прокси
            "network": "udp",
            "port": [443],
            "action": "reject"
        }
    ]

    # Добавляем список процессов-исключений (идут напрямую)
    if excluded_processes:
        cleaned_procs = []
        cleaned_paths = []
        regex_patterns = []
        for p in excluded_processes:
            p = str(p).strip()
            if not p:
                continue

            lower_p = p.lower()
            # Автоматически расширяем связанные процессы для популярных инструментов
            if "happ" in lower_p:
                for sub in ("happ.exe", "happd.exe", "xray.exe"):
                    for cand in (sub, sub.lower(), sub.capitalize(), sub.upper()):
                        if cand not in cleaned_procs:
                            cleaned_procs.append(cand)
                regex_patterns.append("(?i).*(?:happ|xray).*")
            elif "telegram" in lower_p:
                for sub in ("telegram.exe", "tgwsproxy_windows.exe", "tgwsproxy.exe"):
                    for cand in (sub, sub.lower(), sub.capitalize()):
                        if cand not in cleaned_procs:
                            cleaned_procs.append(cand)
                regex_patterns.append("(?i).*(?:telegram|tgwsproxy).*")

            if "\\" in p or "/" in p:
                cleaned_paths.append(p)
                base = os.path.basename(p)
                for cand in (base, base.lower(), base.capitalize()):
                    if cand and cand not in cleaned_procs:
                        cleaned_procs.append(cand)
            else:
                raw_name = p
                if not raw_name.lower().endswith(".exe"):
                    raw_name += ".exe"
                for cand in (raw_name, raw_name.lower(), raw_name.capitalize()):
                    if cand not in cleaned_procs:
                        cleaned_procs.append(cand)
                stem = re.escape(os.path.splitext(raw_name)[0])
                regex_patterns.append(f"(?i).*{stem}.*")

        if cleaned_procs:
            route_rules.append({
                "process_name": cleaned_procs,
                "outbound": "direct"
            })
        if cleaned_paths:
            route_rules.append({
                "process_path": cleaned_paths,
                "outbound": "direct"
            })
        if regex_patterns:
            route_rules.append({
                "process_path_regex": regex_patterns,
                "outbound": "direct"
            })

    # Локальные/приватные IP сети идут напрямую
    route_rules.append({
        "ip_is_private": True,
        "outbound": "direct"
    })

    config = {
        "log": {
            "level": "info",
            "timestamp": True
        },
        "dns": {
            "servers": [
                {
                    "tag": "dns-remote",
                    "type": "tcp",
                    "server": "1.1.1.1",
                    "server_port": 53,
                    "detour": "proxy-out"
                },
                {
                    "tag": "dns-backup",
                    "type": "tcp",
                    "server": "8.8.8.8",
                    "server_port": 53,
                    "detour": "proxy-out"
                },
                {
                    "tag": "dns-direct",
                    "type": "local",
                    "detour": "direct"
                }
            ],
            "final": "dns-remote",
            "strategy": "ipv4_only"
        },
        "inbounds": [
            {
                "type": "tun",
                "tag": "tun-in",
                "interface_name": "tun0",
                "address": ["172.28.0.1/30"],
                "mtu": 1500,
                "auto_route": True,
                "strict_route": False,
                "stack": "mixed",
                "endpoint_independent_nat": True
            }
        ],
        "outbounds": [
            socks_outbound,
            {
                "type": "direct",
                "tag": "direct"
            }
        ],
        "route": {
            "default_domain_resolver": "dns-direct",
            "rules": route_rules,
            "auto_detect_interface": True,
            "final": "proxy-out"
        },
        "experimental": {
            "cache_file": {
                "enabled": True,
                "path": os.path.join(DATA_DIR, "cache.db")
            }
        }
    }
    return config


class ProxyManager:
    """Менеджер процесса sing-box."""
    def __init__(self):
        self.process: subprocess.Popen | None = None
        self.is_running = False
        self.log_callback = None
        self._reader_thread = None

    def start(self, host: str, port: int, username: str = "", password: str = "", excluded_processes: list = None, log_cb=None) -> tuple[bool, str]:
        if self.is_running:
            return True, "Уже запущено"

        if not os.path.exists(SING_BOX_EXE):
            return False, f"Файл sing-box.exe не найден по пути: {SING_BOX_EXE}"

        self.log_callback = log_cb

        # Гарантируем отсутствие зависших экземпляров перед стартом
        try:
            subprocess.run(["taskkill", "/F", "/IM", "sing-box.exe"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(0.3)
        except Exception:
            pass

        # Проверка на наличие других активных L3 TUN/VPN адаптеров (Happ, Xray, WireGuard, Outline и др.)
        try:
            ps_chk = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-NetAdapter | Where-Object Status -eq Up | Select-Object -ExpandProperty Name"],
                capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            up_adapters = [a.strip().lower() for a in ps_chk.stdout.splitlines() if a.strip()]
            conflicts = [a for a in up_adapters if any(k in a for k in ["happ", "xray", "sing-tun", "wireguard", "outline"])]
            if conflicts and log_cb:
                log_cb(f"⚠️ ВНИМАНИЕ: Обнаружен другой активный VPN адаптер: {', '.join(conflicts)}!")
                log_cb("⚠️ Два системных TUN-прокси не могут работать одновременно. Пожалуйста, отключите другой VPN перед запуском!")
        except Exception:
            pass

        try:
            config = generate_sing_box_config(host, port, username, password, excluded_processes)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            # Проверка конфига перед запуском (в полностью скрытом режиме без всплывающего окна)
            check_res = subprocess.run(
                [SING_BOX_EXE, "check", "-c", CONFIG_PATH],
                capture_output=True,
                text=True,
                cwd=BIN_DIR,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if check_res.returncode != 0:
                err_msg = check_res.stderr.strip() or check_res.stdout.strip()
                return False, f"Ошибка конфигурации: {err_msg}"

            # Запуск sing-box в скрытом фоновом процессе
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            self.process = subprocess.Popen(
                [SING_BOX_EXE, "run", "-c", CONFIG_PATH],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=BIN_DIR,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self.is_running = True

            # Поток чтения логов
            self._reader_thread = threading.Thread(target=self._read_logs, daemon=True)
            self._reader_thread.start()

            # Даем секунду на проверку, не упал ли сразу
            time.sleep(1.0)
            if self.process.poll() is not None:
                self.is_running = False
                return False, "Процесс завершился с ошибкой сразу после старта"

            return True, "Подключение успешно установлено"

        except Exception as e:
            self.is_running = False
            return False, f"Ошибка запуска: {str(e)}"

    def _read_logs(self):
        try:
            if self.process and self.process.stdout:
                for line in iter(self.process.stdout.readline, ""):
                    if not line:
                        break
                    clean_line = line.strip()
                    if clean_line and self.log_callback:
                        self.log_callback(clean_line)
        except Exception:
            pass
        finally:
            self.is_running = False

    def stop(self) -> tuple[bool, str]:
        if not self.process:
            self.is_running = False
            return True, "Не запущено"

        try:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        except Exception as e:
            print(f"Error terminating process: {e}")
        finally:
            self.process = None
            self.is_running = False

        # Очистка возможных зависших sing-box процессов
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "sing-box.exe"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        except Exception:
            pass

        # Небольшая пауза для гарантированного освобождения Wintun адаптера системой
        time.sleep(0.5)

        return True, "Отключено"


def get_current_ip() -> dict:
    """Получает внешний IP и информацию о стране."""
    services = [
        "https://api.ipify.org?format=json",
        "https://ipapi.co/json/",
        "https://ifconfig.me/all.json"
    ]
    for url in services:
        try:
            resp = requests.get(url, timeout=3.5)
            if resp.status_code == 200:
                data = resp.json()
                ip = data.get("ip") or data.get("ip_addr")
                country = data.get("country_name") or data.get("country") or ""
                city = data.get("city") or ""
                loc = f"{city}, {country}".strip(", ")
                return {"success": True, "ip": ip, "location": loc}
        except Exception:
            continue
    return {"success": False, "ip": "Не определен", "location": ""}
