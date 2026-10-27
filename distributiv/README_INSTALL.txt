================================================================================
          PowerMaster ASUS TUF (v0.2.60-beta) - USER GUIDE & INSTALLATION
          РУКОВОДСТВО ПОЛЬЗОВАТЕЛЯ И ИНСТРУКЦИЯ ПО УСТАНОВКЕ
================================================================================

[RU] РУССКАЯ ВЕРСИЯ
[EN] ENGLISH VERSION (SEE BELOW)

--------------------------------------------------------------------------------
[RU] 1. ПРОСТО О СЛОЖНОМ: ЧТО ДЕЛАЕТ И КАК РАБОТАЕТ ПРОГРАММА
--------------------------------------------------------------------------------
PowerMaster ASUS TUF — это легковесный, быстрый и полностью автономный менеджер
питания, охлаждения и батареи для игровых ноутбуков ASUS TUF (протестировано на
ASUS TUF A15 FA506IU: Ryzen 5 4600H / Ryzen 7 4800H + GTX 1660 Ti, полностью
совместимо с другими моделями TUF и ROG).

Программа создана как чистая альтернатива громоздкому комплексу Armoury Crate и
работает по принципу «настроил и забыл»: потребление ресурсов процессора близко к 0%
(нет постоянного опроса сотен процессов), поэтому ядра AMD Ryzen не просыпаются
впустую и остаются в глубоком аппаратном сне C6.

ОСНОВНЫЕ ВОЗМОЖНОСТИ:

1. 🔋 ЗАЩИТА БАТАРЕИ (Battery Health Guard):
   - Установка аппаратного порога заряда: 60% (максимальный ресурс при работе от розетки),
     80% (универсальный баланс) или 100% (полный заряд перед поездкой).
   - Настройка передаётся напрямую в контроллер материнской платы (EC) через
     драйвер ядра ASUS ACPI (\\.\ATKACPI) и закрепляется в реестре.
   - Умный реактивный сторож (Battery Guard) автоматически повторно применяет выбранный
     порог при старте, после выхода из сна/гибернации и через 3 секунды после
     подключения блока питания, не давая родным службам ASUS сбросить заряд на 100%.

2. ⚡ УМНОЕ ПЕРЕКЛЮЧЕНИЕ ПИТАНИЯ (PowerWatcher):
   - Автоматический режим по умолчанию: программа из коробки работает полностью автоматически
     («⚡ Авто-переключение включено»), самостоятельно регулируя схемы питания по системным триггерам.
   - Стартовое ускорение (Startup Boost): первые 3 минуты после загрузки ноутбука автоматически
     включается режим «Высокая производительность» для максимально быстрого старта Windows и
     автозапуска всех приложений, после чего система плавно переходит в «Сбалансированный» режим.
   - Мгновенное определение игр из ваших папок: укажите папки с играми (например,
     F:\Games, D:\SteamLibrary) в меню «⚙️ Настройки...» -> «Игры и Процессы».
     Как только любая игра из этих папок выходит на передний план (включая игры
     из UWP и Xbox Game Pass), ноутбук мгновенно включает «Высокую производительность»
     с нулевой задержкой и без фонового перебора процессов.
   - Защита от перегрева в рюкзаке: при выключении дисплея или закрытии крышки
     ноутбука PowerMaster немедленно переводит систему в режим энергосбережения,
     поэтому забытая свернутая игра не раскалит ноутбук.
   - Детектор простоя: если мышь и клавиатура не используются более 3 минут (время
     настраивается), система автоматически переходит в режим энергосбережения, а при
     первом движении мыши мгновенно возвращает рабочий профиль.
   - Защита при работе от батареи: при отключении сетевого шнура автоматически
     включается «Экономия энергии».
   - Ручной режим (Manual Override): если вам нужно зафиксировать конкретный план питания,
     просто выберите его вручную в трее или на дашборде. Автоматика зафиксирует выбранный план
     при работе от сети. Вернуться в автоматический режим можно в любой момент кликом по пункту
     «Возобновить авто-режим» в меню трея.

3. 🍃 ЭНЕРГОСБЕРЕЖЕНИЕ WINDOWS В ОДИН КЛИК:
   - Прямой двухсторонний переключатель нативного режима энергосбережения Windows 11
     прямо на Дашборде и в контекстном меню трея — больше не нужно открывать «Параметры Windows».
   - Утихомиривает фоновые службы Windows (индексацию поиска, телеметрию, синхронизацию)
     как при работе от батареи, так и от сети.

4. 🚀 ВШИТАЯ ЛОГИКА ТУРБОБУСТА ПРОЦЕССОРА:
   Вам не нужны сложные ручные ползунки — поведение турбобуста процессора автоматически
   привязано к каждой схеме питания:
   - «Экономия энергии»: турбобуст ПОЛНОСТЬЮ ОТКЛЮЧЕН — процессор работает на базовой
     частоте или ниже, обеспечивая абсолютную тишину и минимальный нагрев.
   - «Сбалансированная»: включен «лайт-буст» (мягкий эффективный режим Efficient Enabled) —
     быстрый отклик в повседневных задачах без резких скачков температуры.
   - «Высокая производительность» (игры): включен полный агрессивный турбобуст для
     максимального FPS в играх.

5. ❄️ АВТОМАТИЧЕСКИЕ ПРОФИЛИ ОХЛАЖДЕНИЯ ASUS:
   Кривые вентиляторов материнской платы автоматически синхронизируются с активной схемой
   электропитания через ASUS ACPI (0x00120075):
   - «Высокая производительность» -> режим вентиляторов Турбо;
   - «Сбалансированная»         -> режим вентиляторов Стандартный;
   - «Экономия энергии»         -> режим вентиляторов Тихий.

6. 📊 ЖИВОЙ ДАШБОРД И АДАПТИВНЫЙ ИНТЕРФЕЙС (Dashboard):
   - Реальная текущая частота ядер CPU в ГГц/МГц (через счётчики ядра Windows PDH),
     нагрузка CPU (%), температура ядер (°C) и обороты кулера CPU (RPM).
   - Мониторинг видеокарты NVIDIA через NVML: загрузка GPU (%), частота ядра (МГц),
     температура (°C) и обороты кулера GPU (RPM), а также использование ОЗУ (ГБ и %).
   - Удобство для зрения: 4 темы оформления («Кибер-тёмная», «OLED Контраст»,
     «Чистая минималистичная», «Светлая»), масштабирование окна 100% / 125% / 150% и 3 размера
     шрифта меню трея («Стандартный», «Крупный», «Большой»).

7. 🔕 ОТКЛЮЧЕНИЕ СЛУЖБ ASUS (В ОКНЕ «НАСТРОЙКИ»):
   - Кнопка в окне «⚙️ Настройки...» (вкладка «Система и Язык»), которое открывается из
     меню системного трея, предназначена для отключения фоновых служб ASUS.
   - В один клик безопасно останавливает и отключает 7 фоновых служб ASUS (ASUSOptimization,
     AsusAppService, ASUSSoftwareManager и др.), не давая им сбрасывать лимит батареи
     с 60% и разгружая систему. При этом драйвер датчиков кулеров (asussaio)
     намеренно сохраняется, поэтому мониторинг оборотов вентиляторов (RPM) продолжает отображаться!

--------------------------------------------------------------------------------
[RU] 2. ВАРИАНТЫ УСТАНОВКИ И ЧАСТЫЕ ВОПРОСЫ
--------------------------------------------------------------------------------
ВАРИАНТ 1: УСТАНОВЩИК (PowerMaster_ASUS_Setup.exe) - РЕКОМЕНДУЕТСЯ
- Запустите PowerMaster_ASUS_Setup.exe двойным кликом мыши.
- Установка не требует прав администратора и выполняется в профиль пользователя
  %LOCALAPPDATA%\PowerMaster_ASUS.
- Создаёт ярлык в меню «Пуск» и настраивает тихий автозапуск в системный трей.
- Встроен безопасный автоапдейтер с криптографической проверкой контрольной
  суммы SHA-256 и шифрованием токенов через Windows DPAPI.

ВАРИАНТ 2: ПОРТАТИВНАЯ ВЕРСИЯ (PowerMaster_ASUS_Portable.exe)
- Работает сразу без установки из любой папки или с флешки.
- Все настройки (config.json) и лог-файлы сохраняются рядом с программой.

ЧАСТЫЕ ВОПРОСЫ (FAQ):
* Предупреждение Windows SmartScreen («Система Windows защитила ваш ПК»):
  Поскольку это бесплатный независимый проект без платной сертификации EV,
  нажмите «Подробнее» -> «Выполнить в любом случае».
* Как запускать программу с правами Администратора без постоянных окон UAC?
  Нажмите правой кнопкой мыши по иконке программы в трее -> «🚀 Автозагрузка» ->
  выберите «🛡️ От имени Администратора (без UAC)». Программа один раз запросит
  подтверждение и создаст задачу в Планировщике Windows.


================================================================================
[EN] 1. IN PLAIN ENGLISH: WHAT IT DOES & HOW IT WORKS
================================================================================
PowerMaster ASUS TUF is a lightweight, fast, and self-contained power, cooling,
and battery health manager built for ASUS TUF Gaming laptops (tested on ASUS TUF
A15 FA506IU: Ryzen 5 4600H / Ryzen 7 4800H + GTX 1660 Ti, compatible with other
ASUS TUF and ROG models).

It is a clean, bloat-free replacement for ASUS Armoury Crate designed around a
"set-and-forget" philosophy: near-zero background CPU usage (0% polling overhead)
so AMD Ryzen cores stay in deep C6 hardware sleep.

KEY FEATURES:

1. 🔋 BATTERY HEALTH GUARD:
   - Choose your hardware charge ceiling: 60% (maximum battery lifespan when
     plugged in at a desk), 80% (everyday balance), or 100% (full capacity for travel).
   - Communicates directly with the motherboard Embedded Controller (EC) via the
     ASUS ACPI kernel driver (\\.\ATKACPI) and syncs across registry views.
   - Smart Reactive Battery Guard automatically re-enforces your 60%/80% limit
     on startup, after sleep/hibernation, and 3 seconds after plugging in AC power
     so vendor services can never silently reset your battery to 100%.

2. ⚡ SMART POWER SWITCHING (PowerWatcher):
   - Fully Automated by Default: out of the box, PowerMaster operates in automated mode
     ("⚡ Auto-Switching Enabled"), dynamically adapting power schemes based on system hardware events.
   - Startup Boost: for the first 3 minutes after boot, "High Performance" is engaged automatically
     to accelerate Windows startup and background app loading, after which it smoothly transitions to "Balanced".
   - Instant Game Detection from Your Folders: add your game libraries (e.g.,
     F:\Games, D:\SteamLibrary) in "⚙️ Settings..." -> "Games & Processes".
     Whenever a game from those folders is active in the foreground (including
     UWP / Xbox Game Pass titles), the laptop switches to High Performance in
     milliseconds with zero background process-scanning lag.
   - Backpack & Lid-Close Protection: the moment the screen turns off or the lid
     closes, PowerMaster immediately switches to Power Saver so a minimized game
     never overheats your laptop.
   - Inactivity Sensor (Idle Detection): automatically drops to Power Saver after 3 minutes (configurable)
     of zero mouse/keyboard activity, and restores your active profile as soon as
     you move the mouse.
   - Unplugged Protection: automatically switches to Power Saver on battery power.
   - Manual Override Mode: if you need to lock a specific plan, simply click it in the tray
     menu or dashboard. PowerMaster holds your chosen plan during AC operation without monitor cycle resets.
     You can return to automated mode at any time by selecting "Resume Auto Mode" in the tray menu.

3. 🍃 ONE-CLICK WINDOWS ENERGY SAVER:
   - Direct two-way toggle for native Windows 11 Energy Saver right on the
     Dashboard and in the system tray menu — no need to dig through Windows Settings.
   - Quiets down background Windows indexing, sync, and telemetry on both battery
     and AC wall power.

4. 🚀 BUILT-IN CPU TURBO BOOST LOGIC:
   No fiddly manual sliders required — CPU boost is automatically matched to each
   power scheme:
   - Power Saver: Turbo Boost is COMPLETELY DISABLED — the CPU stays at or below
     base clock for silent, cool operation.
   - Balanced: dynamic "light boost" (Efficient Enabled) — snappy everyday
     performance without temperature spikes.
   - High Performance (Gaming): full Aggressive Turbo Boost for maximum gaming FPS.

5. ❄️ AUTOMATIC ASUS COOLING PROFILES:
   Motherboard fan curves sync automatically with the active power plan via ASUS
   ACPI (0x00120075):
   - High Performance -> Turbo fan profile;
   - Balanced         -> Standard fan profile;
   - Power Saver      -> Silent fan profile.

6. 📊 LIVE TELEMETRY DASHBOARD & ACCESSIBLE UI:
   - Real-time CPU core frequency in GHz/MHz (via Windows kernel PDH counters),
     CPU load (%), core temperature (°C), and CPU fan speed (RPM).
   - NVIDIA GPU monitoring via NVML: GPU load (%), core clock (MHz), temperature
     (°C), GPU fan speed (RPM), plus system RAM usage (GB & %).
   - Built for readability: 4 visual themes (Cyber Dark, OLED Contrast, Clean
     Minimalist, Light), 100% / 125% / 150% UI scaling, and 3 tray menu font sizes
     (Standard, Large, Huge).

7. 🔕 ONE-CLICK ASUS SERVICES DISABLER (IN SETTINGS):
   - Located in "⚙️ Settings..." -> "System & Language" tab (opened from the
     system tray menu).
   - Stops and disables 7 conflicting background ASUS services (ASUSOptimization,
     AsusAppService, ASUSSoftwareManager, etc.) via native Win32 SCM to stop
     battery-limit resets and free up system resources — while keeping the
     asussaio sensor driver untouched so CPU/GPU fan RPM readings continue working!

--------------------------------------------------------------------------------
[EN] 2. INSTALLATION OPTIONS & FAQ
--------------------------------------------------------------------------------
OPTION 1: INSTALLER (PowerMaster_ASUS_Setup.exe) - RECOMMENDED
- Double-click PowerMaster_ASUS_Setup.exe.
- Installs cleanly into %LOCALAPPDATA%\PowerMaster_ASUS without requiring admin rights.
- Creates a Start Menu shortcut and optional silent tray autostart on login.
- Includes a built-in GitHub updater with cryptographic SHA-256 verification and
  Windows DPAPI secret encryption.

OPTION 2: PORTABLE VERSION (PowerMaster_ASUS_Portable.exe)
- Run directly from any folder or USB drive with zero installation.
- Stores config.json and logs right next to the executable.

FAQ:
* Windows SmartScreen prompt ("Windows protected your PC"):
  Because this is a free open-source tool without a paid commercial EV certificate,
  click "More info" -> "Run anyway".
* How do I run with Administrator rights at startup without UAC prompts?
  Right-click the tray icon -> "🚀 Autostart" -> select "🛡️ Run as Administrator
  (No UAC)". Confirm UAC once, and Windows Task Scheduler will launch it elevated
  automatically on every login.

================================================================================
SHA-256 INTEGRITY CHECKSUMS (v0.2.60-beta):
- PowerMaster_ASUS_Setup.exe:
  1e5eca86e38db3c8faf5dcf4013a0f7973a8b455effc1e3363ba72a8b5974722
- PowerMaster_ASUS_Portable.exe:
  3ad69a66a7bc982314fa7938d2067149760d67756a9f587e23a7d716fbad37f0
================================================================================