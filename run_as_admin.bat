@echo off
chcp 65001 >nul
title PowerMaster ASUS (Admin Launcher)
cd /d "%~dp0"

echo [PowerMaster] Запуск PowerMaster ASUS TUF с правами Администратора...

if exist "%~dp0dist\PowerMaster_ASUS.exe" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process '%~dp0dist\PowerMaster_ASUS.exe' -Verb RunAs"
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process 'pythonw.exe' -ArgumentList '\"%~dp0main.py\"' -Verb RunAs"
)

exit /b 0