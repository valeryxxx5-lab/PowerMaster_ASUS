# PowerMaster ASUS TUF ⚡🛡️ (v0.2.61-beta)

[![Version](https://img.shields.io/badge/version-0.2.60--beta-blue.svg)](https://github.com/valeryxxx5-lab/PowerMaster_ASUS/releases/latest)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011%20(64--bit)-brightgreen.svg)]()
[![Hardware](https://img.shields.io/badge/hardware-ASUS%20TUF%20%2F%20ROG-orange.svg)]()
[![Tests](https://img.shields.io/badge/tests-165%2F165%20PASSED%20(100%25)-success.svg)]()
[![License](https://img.shields.io/badge/license-MIT-green.svg)]()

> **[🇷🇺 Русский](#-русский-раздел) | [🇬🇧 English](#-english-section)**

---

<a name="-русский-раздел"></a>
## 🇷🇺 Русский раздел

### 📖 О проекте

**PowerMaster ASUS TUF** — это легковесный, быстрый и полностью автономный менеджер питания, охлаждения и батареи для игровых ноутбуков **ASUS TUF Gaming** (протестировано и оптимизировано на **ASUS TUF A15 FA506IU: AMD Ryzen 5 4600H / Ryzen 7 4800H + NVIDIA GeForce GTX 1660 Ti**), а также других моделей серий TUF и ROG.

Программа заменяет тяжеловесный комплекс ASUS Armoury Crate и работает по принципу «настроил и забыл»:
- Потребление ресурсов процессора близко к 0% (нет циклического опроса сотен процессов), поэтому ядра AMD Ryzen не просыпаются впустую и сохраняют глубокий аппаратный сон `C6`;
- Аппаратная защита ресурса аккумулятора с реактивным сторожем (Battery Guard);
- Автоматическое переключение схем питания для игр и при смене питания сеть/батарея;
- Прямое управление нативным энергосбережением Windows в один клик.

---

### ✨ Реальный функционал и возможности

#### 🔋 1. Защита батареи (Battery Health Guard)
- **Установка аппаратного порога заряда:** 60% (максимальный ресурс при работе от розетки), 80% (универсальный баланс) или 100% (полный заряд перед поездкой).
- **Прямая запись в драйвер ядра ACPI:** настройка передаётся напрямую в контроллер материнской платы (EC) через драйвер ядра ASUS ACPI (`\\.\ATKACPI`) и закрепляется в реестре.
- **Умный реактивный сторож (Battery Guard):** с 0% нагрузки на процессор автоматически повторно применяет выбранный порог при старте, после выхода из сна/гибернации и через 3 секунды после подключения блока питания, не давая фоновым процессам вендора сбросить заряд на 100%.

#### ⚡ 2. Умное переключение питания (PowerWatcher)
- **Автоматический режим по умолчанию:** из коробки программа работает полностью в автоматическом режиме («⚡ Авто-переключение включено»), самостоятельно и бесшумно регулируя схемы питания по системным аппаратным событиям.
- **Стартовое ускорение (Startup Boost):** первые 3 минуты после загрузки ноутбука автоматически включается режим «Высокая производительность» для максимально быстрого старта Windows и автозапуска приложений, после чего система плавно переходит в «Сбалансированный» режим.
- **Мгновенное определение игр из ваших папок:** укажите каталоги с играми (например, `F:\Games`, `D:\SteamLibrary`) в меню «⚙️ Настройки...» -> «Игры и Процессы». Как только любая игра из этих папок выходит на передний план (включая UWP и Xbox Game Pass), ноутбук мгновенно включает «Высокую производительность» через быстрый WinAPI `GetForegroundWindow` без фонового перебора процессов.
- **Защита от перегрева в рюкзаке:** при выключении дисплея или закрытии крышки ноутбука PowerMaster немедленно переводит систему в режим энергосбережения, поэтому забытая свернутая игра не раскалит ноутбук.
- **Детектор простоя:** если мышь и клавиатура не используются более 3 минут (время настраивается), система автоматически снижает энергопотребление, а при первом движении мыши мгновенно возвращает рабочий профиль.
- **Защита при работе от батареи:** при отключении сетевого шнура автоматически включается «Экономия энергии».
- **Ручной режим (Manual Override):** если вам требуется зафиксировать конкретную схему электропитания, просто выберите её вручную в трее или на дашборде. Автоматика зафиксирует выбранный план при работе от сети. Вернуться к авто-регулированию можно в любой момент, выбрав пункт «Возобновить авто-режим» в меню трея.

#### 🍃 3. Прямое энергосбережение Windows в один клик
- Прямой двухсторонний переключатель нативного режима энергосбережения Windows 10/11 через системную шину Windows Notification Facility (`WNF_PO_ENERGY_SAVER_STATE`) и `powrprof.dll`.
- Включается и выключается в один клик **на Дашборде или в контекстном меню трея** без вызова тяжелых «Параметров Windows».
- Утихомиривает фоновые службы Windows (индексацию поиска, телеметрию, фоновую оптимизацию) как при работе от батареи, так и от сети.

#### 🚀 4. Вшитая логика Turbo Boost процессора
В программе нет лишних ручных ползунков — поведение турбобуста процессора автоматически привязано к каждой схеме питания:
- 🌿 **Режим «Экономия энергии»:** турбобуст **полностью отключен** (`PERFBOOSTMODE = 0`). Процессор работает строго на базовой частоте (2.9 ГГц на Ryzen 7 4800H), благодаря чему ноутбук остаётся абсолютно холодным и тихим.
- ⚖️ **Режим «Сбалансированная»:** включен **мягкий / лайт-буст** (`Efficient Enabled`, `PERFBOOSTMODE = 3`) — быстрый отклик в повседневных задачах без резких температурных скачков.
- 🎮 **Режим «Высокая производительность» (Игры):** включен **полный агрессивный турбобуст** (`Aggressive`, `PERFBOOSTMODE = 2`) для максимального FPS в играх.

#### ❄️ 5. Автоматические профили системы охлаждения ASUS
Кривые вентиляторов материнской платы автоматически синхронизируются с активной схемой электропитания через ASUS ACPI (`0x00120075`):
- «Высокая производительность» -> режим вентиляторов **Турбо**;
- «Сбалансированная»         -> режим вентиляторов **Стандартный**;
- «Экономия энергии»         -> режим вентиляторов **Тихий**.

#### 📊 6. Живой дашборд и адаптивный интерфейс (Dashboard)
- **Аппаратные датчики реального времени:**
  - Реальная текущая частота ядер CPU в ГГц/МГц (через счётчики ядра Windows PDH, а не статическая базовая частота);
  - Нагрузка CPU (%), температура ядер (°C) и обороты кулера CPU (RPM);
  - Телеметрия видеокарты NVIDIA через NVML: загрузка GPU (%), частота ядра (МГц), температура (°C) и обороты кулера GPU (RPM);
  - Использование оперативной памяти ОЗУ (ГБ и %);
  - Текущий текстовый статус профиля охлаждения (Турбо / Сбалансированный / Тихий).
- **Удобство для зрения и адаптивность:** 4 темы оформления («Кибер-тёмная», «OLED Контраст», «Чистая минималистичная», «Светлая»), масштабирование окна (100% / 125% / 150%) и 3 размера шрифта меню трея («Стандартный», «Крупный», «Большой»).

#### 🔕 7. Отключение служб ASUS (в окне «Настройки»)
- Кнопка в окне **«⚙️ Настройки...»** (вкладка «Система и Язык»), открываемом из системного трея, предназначена для нейтрализации служб ASUS.
- В один клик безопасно останавливает и отключает 7 фоновых служб ASUS (`ASUSOptimization`, `AsusAppService`, `ASUSSoftwareManager` и др.), не давая им сбрасывать лимит батареи и разгружая систему.
- При этом драйвер датчиков кулеров (`asussaio`) намеренно сохраняется, поэтому мониторинг оборотов вентиляторов (RPM) продолжает работать!

#### 🔒 8. Безопасность и надежность
- **Windows DPAPI:** все токены и секреты шифруются через аппаратный Win32 CryptoAPI с привязкой к учётной записи пользователя.
- **Безопасное автообновление:** встроенный апдейтер проверяет контрольную сумму SHA-256 каждого инсталлятора перед запуском.
- **Атомарная запись настроек:** защита от повреждения `config.json` при внезапной перезагрузке или сбое питания.

---

### 📁 Структура файлов проекта

```text
PowerMaster_ASUS/
├── distributiv/            # Готовые пакеты установки и инструкции (папка со ссылками на релизы)
├── main.py                 # Главная точка входа (CLI, Mutex защита, системная маршрутизация)
├── tray_app.py             # Приложение в системном трее (pystray + контекстное меню Tkinter)
├── dashboard.py            # Интерактивный киберпанк-дашборд с живой телеметрией
├── power_watcher.py        # Координатор триггеров питания (O(1) игры из папок, дисплей, сеть)
├── power_plan.py           # WinAPI powrprof.dll обёртка переключения схем электропитания
├── asus_battery.py         # Аппаратный контроль порога заряда (60/80/100%) через ASUS ACPI WMI
├── asus_services.py        # Диагностика и безопасная приостановка фоновых служб ASUS
├── asus_thermal.py         # Синхронизация профилей вентиляторов (Thermal Policy 0x00120075)
├── windows_energy_saver.py # Прямое переключение энергосбережения Windows через Win32 WNF / powrprof
├── config.py               # DPAPI шифрование секретов, атомарная запись, авто-миграция и валидация
├── autostart.py            # Управление автозапуском через реестр HKCU и Windows Task Scheduler
├── settings_dialog.py      # Графическое окно настроек (папки с играми, службы ASUS, темы, язык)
├── update_dialog.py        # Окно проверки и загрузки обновлений
├── updater.py              # Безопасный загрузчик релизов с проверкой контрольной суммы SHA-256
├── icon_generator.py       # Процедурная генерация иконок для трея (High/Balanced/Saver)
├── tray_enhancements.py    # Модуль масштабирования и стилизации контекстного меню трея
├── launcher.pyw            # Запуск без консольного окна через pythonw.exe
├── test_runner.py          # Единая точка запуска тестового сьюта (165 тестов)
├── test_powermaster.py     # Набор тестов логики FSM, батареи, DPAPI и схем питания
├── test_dashboard.py       # Набор тестов телеметрии дашборда и тем оформления
├── test_settings_and_tray.py # Тесты диалога настроек, i18n и интеграции трея
├── test_updater_and_icons.py # Тесты безопасности апдейтера и генерации иконок
├── PowerMaster.spec        # PyInstaller спецификация автономной сборки .exe
├── installer.iss           # Inno Setup скрипт компиляции инсталлятора
├── version_info.txt        # Ресурсный файл версий PE-заголовка (0.2.60.0)
├── config.example.json     # Эталонный шаблон конфигурационного файла
├── build_exe.bat           # Скрипт сборки автономного exe через PyInstaller
├── build_installer.bat     # Скрипт сборки Windows-инсталлятора через Inno Setup
├── run_powermaster.bat     # Скрипт быстрого запуска в трее
├── run_as_admin.bat        # Скрипт запуска с правами Администратора (UAC RunAs)
└── requirements.txt        # Зависимости Python (pystray, pillow, wmi, pywin32, psutil)
```

---

### 💻 Установка и использование

#### Вариант А: Готовый инсталлятор (Рекомендуется)
1. Скачайте **[PowerMaster_ASUS_Setup.exe](https://github.com/valeryxxx5-lab/PowerMaster_ASUS/releases/latest/download/PowerMaster_ASUS_Setup.exe)** со страницы **[Официальных Релизов (Releases)](https://github.com/valeryxxx5-lab/PowerMaster_ASUS/releases/latest)** (или откройте папку [`distributiv/`](distributiv/)).
2. Запустите файл **`PowerMaster_ASUS_Setup.exe`**.
3. Установка выполняется в профиль пользователя `%LOCALAPPDATA%\PowerMaster_ASUS` без необходимости прав администратора. Создаётся ярлык в меню «Пуск» и настраивается тихий автозапуск в трей.

#### Вариант Б: Портативная версия (Portable)
1. Скачайте **[PowerMaster_ASUS_Portable.exe](https://github.com/valeryxxx5-lab/PowerMaster_ASUS/releases/latest/download/PowerMaster_ASUS_Portable.exe)** со страницы **[Официальных Релизов (Releases)](https://github.com/valeryxxx5-lab/PowerMaster_ASUS/releases/latest)** (или откройте папку [`distributiv/`](distributiv/)).
2. Программа работает сразу без установки из любой папки или с флешки.

#### Запуск с правами Администратора без постоянных окон UAC
- Нажмите правой кнопкой мыши по иконке программы в трее -> **«🚀 Автозагрузка»** -> выберите **«🛡️ От имени Администратора (без UAC)»**. Программа один раз запросит подтверждение и создаст задачу в Планировщике Windows.

#### Управление через консоль (CLI)
```bash
# Показать статус питания, батареи и служб
python main.py --status

# Установить лимит заряда батареи (60, 80 или 100%)
python main.py --set-limit 60

# Переключить схему питания
python main.py --set-plan high
python main.py --set-plan balanced
python main.py --set-plan saver

# Проверить статус служб ASUS
python main.py --status-asus-services

# Открыть окно Дашборда
python main.py --dashboard
```

---

<a name="-english-section"></a>
## 🇬🇧 English Section

### 📖 Project Overview

**PowerMaster ASUS TUF** is a lightweight, fast, and self-contained power, cooling, and battery health manager built for **ASUS TUF Gaming** laptops (tested on **ASUS TUF A15 FA506IU: AMD Ryzen 5 4600H / Ryzen 7 4800H + NVIDIA GeForce GTX 1660 Ti**, fully compatible with other ASUS TUF and ROG models).

It is a clean, bloat-free replacement for ASUS Armoury Crate designed around a "set-and-forget" philosophy:
- Near-zero background CPU usage (0% polling overhead) so AMD Ryzen cores stay in deep `C6` hardware sleep;
- Hardware-level battery longevity protection with reactive Battery Guard;
- Automated on-the-fly power scheme switching for games and AC/battery transitions;
- One-click native Windows Energy Saver control.

---

### 🚀 Real Features & Capabilities

#### 🔋 1. Battery Health Guard
- **Hardware Charge Ceilings:** 60% (maximum battery lifespan when plugged in at a desk), 80% (everyday balance), or 100% (full capacity for travel).
- **Direct Kernel ACPI Communication:** writes directly to the motherboard Embedded Controller (EC) via the ASUS ACPI kernel driver (`\\.\ATKACPI`) and syncs across registry views.
- **Smart Reactive Battery Guard:** automatically re-enforces your 60%/80% limit on startup, after sleep/hibernation, and 3 seconds after plugging in AC power so vendor services can never silently reset your battery to 100%.

#### ⚡ 2. Smart Power Switching (PowerWatcher)
- **Fully Automated by Default:** out of the box, PowerMaster operates in automated mode ("⚡ Auto-Switching Enabled"), dynamically adapting power schemes based on system hardware events.
- **Startup Boost:** for the first 3 minutes after boot, "High Performance" is engaged automatically to accelerate Windows startup and background app loading, after which it smoothly transitions to "Balanced".
- **Instant Game Detection from Your Folders:** add your game libraries (e.g., `F:\Games`, `D:\SteamLibrary`) in "⚙️ Settings..." -> "Games & Processes". Whenever a game from those folders is active in the foreground (including UWP / Xbox Game Pass titles), the laptop switches to High Performance in milliseconds with zero background process-scanning lag.
- **Backpack & Lid-Close Protection:** the moment the screen turns off or the lid closes, PowerMaster immediately switches to Power Saver so a minimized game never overheats your laptop.
- **Inactivity Sensor (Idle Detection):** automatically drops to Power Saver after 3 minutes (configurable) of zero mouse/keyboard activity, and restores your active profile as soon as you move the mouse.
- **Unplugged Protection:** automatically switches to Power Saver on battery power.
- **Manual Override Mode:** if you need to lock a specific plan, simply click it in the tray menu or dashboard. PowerMaster holds your chosen plan during AC operation without monitor cycle resets. You can return to automated mode at any time by selecting "Resume Auto Mode" in the tray menu.

#### 🍃 3. One-Click Windows Energy Saver
- Direct two-way toggle for native Windows 11 Energy Saver right on the Dashboard and in the system tray menu — no need to dig through Windows Settings.
- Quiets down background Windows indexing, sync, and telemetry on both battery and AC wall power.

#### 🚀 4. Built-in CPU Turbo Boost Logic
No fiddly manual sliders required — CPU boost is automatically matched to each power scheme:
- 🌿 **Power Saver Plan:** Turbo Boost is **completely disabled** (`PERFBOOSTMODE = 0`) — the CPU stays at or below base clock for silent, cool operation.
- ⚖️ **Balanced Plan:** dynamic **light boost** (`Efficient Enabled`, `PERFBOOSTMODE = 3`) — snappy everyday performance without temperature spikes.
- 🎮 **High Performance Plan (Games):** full **aggressive turbo boost** (`Aggressive`, `PERFBOOSTMODE = 2`) for maximum gaming FPS.

#### ❄️ 5. Automatic ASUS Cooling Profiles
Motherboard fan curves sync automatically with the active power plan via ASUS ACPI (`0x00120075`):
- High Performance -> **Turbo** fan profile;
- Balanced         -> **Standard** fan profile;
- Power Saver      -> **Silent** fan profile.

#### 📊 6. Live Telemetry Dashboard & Accessible UI
- **Real-Time Hardware Metrics:**
  - Real-time CPU core frequency in GHz/MHz (via Windows kernel PDH counters);
  - CPU load (%), core temperature (°C), and CPU fan speed (RPM);
  - NVIDIA GPU monitoring via NVML: GPU load (%), core clock (MHz), temperature (°C), and GPU fan speed (RPM);
  - System RAM memory usage (GB & %);
  - Current cooling status display (textual mode: Turbo / Balanced / Silent).
- **Built for Readability:** 4 visual themes (Cyber Dark, OLED Contrast, Clean Minimalist, Light), 100% / 125% / 150% UI scaling, and 3 tray menu font sizes (Standard, Large, Huge).

#### 🔕 7. One-Click ASUS Services Disabler (in Settings)
- Located in "⚙️ Settings..." -> "System & Language" tab (opened from the system tray menu).
- Stops and disables 7 conflicting background ASUS services (`ASUSOptimization`, `AsusAppService`, `ASUSSoftwareManager`, etc.) via native Win32 SCM to stop battery-limit resets and free up system resources.
- Keeps the `asussaio` sensor driver untouched so CPU/GPU fan RPM readings continue working!

#### 🔒 8. Security & Reliability
- **Windows DPAPI:** encrypts secrets and credentials with user-bound Win32 CryptoAPI.
- **Secure Auto-Update:** cryptographic SHA-256 validation of downloaded setup binaries.
- **Atomic Config Storage:** `NamedTemporaryFile` + `fsync` + `os.replace` eliminates config corruption during sudden power losses.

---

### 💻 Installation & Getting Started

#### Option A: Windows Installer (Recommended)
1. Download **[PowerMaster_ASUS_Setup.exe](https://github.com/valeryxxx5-lab/PowerMaster_ASUS/releases/latest/download/PowerMaster_ASUS_Setup.exe)** from the **[Official Latest Releases](https://github.com/valeryxxx5-lab/PowerMaster_ASUS/releases/latest)** page (or open the [`distributiv/`](distributiv/) directory).
2. Launch **`PowerMaster_ASUS_Setup.exe`**.
3. Installs cleanly into `%LOCALAPPDATA%\PowerMaster_ASUS` without requiring admin rights. Creates a Start Menu shortcut and configures silent tray autostart.

#### Option B: Standalone Portable Executable
1. Download **[PowerMaster_ASUS_Portable.exe](https://github.com/valeryxxx5-lab/PowerMaster_ASUS/releases/latest/download/PowerMaster_ASUS_Portable.exe)** from the **[Official Latest Releases](https://github.com/valeryxxx5-lab/PowerMaster_ASUS/releases/latest)** page (or open the [`distributiv/`](distributiv/) directory).
2. Runs directly without installation from any folder or USB flash drive.

---

## 📄 License
This project is licensed under the **MIT License**.