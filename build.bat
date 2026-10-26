@echo off
echo ==============================================
echo   Сборка ProxyFork в единый EXE через PyInstaller
echo ==============================================
cd /d "%~dp0"
pyinstaller --noconsole --onefile --icon=icon.ico --name="ProxyFork" --add-data "bin;bin" --add-data "icon.ico;." main.py
echo.
echo Сборка завершена! Исполняемый файл находится в папке dist\ProxyFork.exe
pause
