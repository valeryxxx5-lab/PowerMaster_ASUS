@echo off
chcp 65001 >nul
echo ========================================================
echo   PowerMaster_ASUS - Автономная сборка Standalone .exe
echo   (PyInstaller Build Script - ТЗ-26, Рекомендация 2.4)
echo ========================================================

where pyinstaller >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] PyInstaller не найден в PATH!
    echo Установите: pip install pyinstaller
    pause
    exit /b 1
)

echo [1/2] Запуск сборки по спецификации PowerMaster.spec...
pyinstaller --clean --noconfirm PowerMaster.spec

if %ERRORLEVEL% EQU 0 (
    echo [2/2] Сборка успешно завершена!
    echo Исполняемый файл находится в: dist\PowerMaster_ASUS.exe
) else (
    echo [ERROR] Ошибка сборки PyInstaller!
    exit /b 1
)
