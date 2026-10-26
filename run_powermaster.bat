@echo off
chcp 65001 >nul
title PowerMaster ASUS Launcher
cd /d "%~dp0"

echo [PowerMaster] Запуск в фоновом режиме (системный трей)...
start "" pythonw.exe "%~dp0launcher.pyw"
exit /b 0
