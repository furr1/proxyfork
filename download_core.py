import os
import io
import shutil
import urllib.request
import zipfile

APP_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(APP_DIR, "bin")
os.makedirs(BIN_DIR, exist_ok=True)

SING_BOX_URL = "https://github.com/SagerNet/sing-box/releases/download/v1.14.4/sing-box-1.14.4-windows-amd64.zip"
WINTUN_URL = "https://www.wintun.net/builds/wintun-0.14.1.zip"


def download_sing_box():
    dest = os.path.join(BIN_DIR, "sing-box.exe")
    if os.path.exists(dest):
        print("[OK] sing-box.exe уже существует.")
        return
    print("Загрузка sing-box 1.14.4 (Windows AMD64)...")
    req = urllib.request.Request(SING_BOX_URL, headers={"User-Agent": "Mozilla/5.0"})
    content = urllib.request.urlopen(req).read()
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for name in z.namelist():
            if name.endswith("sing-box.exe"):
                with z.open(name) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                print(f"[OK] sing-box.exe сохранен в {dest}")
                return


def download_wintun():
    dest = os.path.join(BIN_DIR, "wintun.dll")
    if os.path.exists(dest):
        print("[OK] wintun.dll уже существует.")
        return
    print("Загрузка Wintun driver 0.14.1...")
    req = urllib.request.Request(WINTUN_URL, headers={"User-Agent": "Mozilla/5.0"})
    content = urllib.request.urlopen(req).read()
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for name in z.namelist():
            if name.endswith("bin/amd64/wintun.dll") or name == "wintun/bin/amd64/wintun.dll":
                with z.open(name) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                print(f"[OK] wintun.dll сохранен в {dest}")
                return


if __name__ == "__main__":
    download_sing_box()
    download_wintun()
    print("Все бинарные компоненты готовы к работе!")
