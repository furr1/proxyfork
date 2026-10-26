@echo off
echo ==============================================
echo   Сборка ProxyFork в единый EXE через PyInstaller
echo ==============================================
cd /d "%~dp0"
pyinstaller --clean -y ProxyFork.spec
echo.
echo Сборка завершена! Исполняемый файл находится в папке dist\ProxyFork.exe
pause
