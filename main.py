import sys
import os
import core
from gui import App

def main():
    # Проверяем права администратора (необходимы для создания TUN интерфейса Wintun)
    if "--no-admin" not in sys.argv:
        if not core.is_admin():
            print("Требуются права администратора для создания TUN адаптера. Запрашиваем UAC...")
            core.request_admin()
            return

    # Запуск интерфейса
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()
