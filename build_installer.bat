@echo off
setlocal

echo ==============================================
echo Сборка инсталлятора PowerMaster ASUS TUF
echo ==============================================

rem Проверяем, собран ли исполняемый файл
if not exist "dist\PowerMaster_ASUS.exe" (
    echo ОШИБКА: Файл dist\PowerMaster_ASUS.exe не найден!
    echo Пожалуйста, сначала выполните сборку через build_exe.bat
    exit /b 1
)

rem Путь к Inno Setup Compiler (ISCC)
set ISCC=
if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Users\%USERNAME%\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
)

rem Проверка наличия ISCC
if "%ISCC%"=="" (
    echo ОШИБКА: Inno Setup 6 не установлен или ISCC.exe не найден!
    echo Скачайте и установите Inno Setup с сайта: https://jrsoftware.org/isinfo.php
    echo Либо установите через: winget install JRSoftware.InnoSetup
    exit /b 1
)

echo Найден компилятор: "%ISCC%"
echo Запуск компиляции installer.iss...
"%ISCC%" "installer.iss"

if %ERRORLEVEL% equ 0 (
    echo.
    echo ==============================================
    echo Инсталлятор успешно собран!
    echo Исполняемый установочный файл находится в: installer\Output\PowerMaster_ASUS_Setup.exe
    echo ==============================================
) else (
    echo.
    echo ==============================================
    echo ОШИБКА: При сборке инсталлятора произошла ошибка!
    echo ==============================================
)

endlocal
pause
