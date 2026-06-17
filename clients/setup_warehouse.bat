@echo off
title WISO GoLabel Warehouse Client - Auto Setup
color 0B
chcp 65001 >nul

echo ╔═══════════════════════════════════════════════════════════════╗
echo ║         WISO GOLABEL СКЛАД - АВТОМАТИЧЕСКАЯ УСТАНОВКА         ║
echo ╔═══════════════════════════════════════════════════════════════╗
echo.

echo [1/5] Проверка Python...
echo.

python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo ⚠️  Python не установлен. Начинаю установку...
    echo.

    set "TEMP_DIR=%TEMP%\wiso_python_setup"
    if not exist "%TEMP_DIR%" mkdir "%TEMP_DIR%"

    if "%PROCESSOR_ARCHITECTURE%"=="AMD64" (
        set "PYTHON_URL=https://www.python.org/ftp/python/3.11.7/python-3.11.7-amd64.exe"
        set "PYTHON_FILE=%TEMP_DIR%\python-3.11.7-amd64.exe"
    ) else (
        set "PYTHON_URL=https://www.python.org/ftp/python/3.11.7/python-3.11.7.exe"
        set "PYTHON_FILE=%TEMP_DIR%\python-3.11.7.exe"
    )

    echo 📥 Скачивание Python 3.11.7...
    echo.

    powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('%PYTHON_URL%', '%PYTHON_FILE%')}"

    if not exist "%PYTHON_FILE%" (
        color 0C
        echo ❌ ОШИБКА: Не удалось скачать Python!
        echo.
        echo Установите Python вручную:
        echo https://www.python.org/downloads/
        echo.
        pause
        exit /b 1
    )

    echo 🔧 Установка Python (2-3 минуты)...
    echo.

    "%PYTHON_FILE%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1

    if %errorLevel% neq 0 (
        color 0C
        echo ❌ ОШИБКА установки Python!
        echo.
        pause
        exit /b 1
    )

    echo ✅ Python установлен
    echo.

    del "%PYTHON_FILE%" >nul 2>&1

    set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts"

    timeout /t 3 /nobreak >nul
) else (
    echo ✅ Python найден
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo    Версия: Python %PYTHON_VERSION%
echo.

REM ═══════════════════════════════════════════════════════════════
REM ПРОВЕРКА PIP
REM ═══════════════════════════════════════════════════════════════

echo [2/5] Проверка pip...
echo.

python -m pip --version >nul 2>&1
if %errorLevel% neq 0 (
    echo ⚠️  Установка pip...
    set "GET_PIP=%TEMP%\get-pip.py"
    powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://bootstrap.pypa.io/get-pip.py', '%GET_PIP%')}"
    python "%GET_PIP%" --user
    del "%GET_PIP%" >nul 2>&1
)

echo ✅ pip: OK
echo.

echo Обновление pip...
python -m pip install --upgrade pip --quiet
echo.

REM ═══════════════════════════════════════════════════════════════
REM УСТАНОВКА ЗАВИСИМОСТЕЙ
REM ═══════════════════════════════════════════════════════════════

echo [3/5] Установка зависимостей...
echo.

cd /d "%~dp0"

if not exist "requirements.txt" (
    color 0C
    echo ❌ ОШИБКА: requirements.txt не найден!
    echo.
    pause
    exit /b 1
)

python -m pip install -r requirements.txt --quiet

if %errorLevel% neq 0 (
    color 0C
    echo ❌ ОШИБКА установки зависимостей!
    echo.
    pause
    exit /b 1
)

echo ✅ Зависимости установлены
echo.

REM ═══════════════════════════════════════════════════════════════
REM ПРОВЕРКА ФАЙЛОВ
REM ═══════════════════════════════════════════════════════════════

echo [4/5] Проверка файлов...
echo.

if not exist "warehouse_client.py" (
    color 0C
    echo ❌ ОШИБКА: warehouse_client.py не найден!
    echo.
    pause
    exit /b 1
)

echo ✅ Файлы найдены
echo.

REM ═══════════════════════════════════════════════════════════════
REM ПРОВЕРКА GOLABEL
REM ═══════════════════════════════════════════════════════════════

echo [5/5] Проверка GoLabel...
echo.

set "GOLABEL_PATH=C:\Program Files (x86)\GoDEX\GoLabel II\GoLabel.exe"

if exist "%GOLABEL_PATH%" (
    echo ✅ GoLabel найден: %GOLABEL_PATH%
) else (
    color 0E
    echo.
    echo ⚠️  ВНИМАНИЕ: GoLabel не найден!
    echo.
    echo Стандартный путь: %GOLABEL_PATH%
    echo.
    echo GoLabel должен быть установлен для печати этикеток!
    echo.
    echo Возможные решения:
    echo 1. Установите GoLabel II
    echo 2. Или укажите правильный путь в warehouse_client.py
    echo.
    pause
)
echo.

REM ═══════════════════════════════════════════════════════════════
REM НАСТРОЙКА
REM ═══════════════════════════════════════════════════════════════

color 0E
echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║                ⚠️  ТРЕБУЕТСЯ НАСТРОЙКА!                       ║
echo ╔═══════════════════════════════════════════════════════════════╗
echo.

REM Настройка IP
set "CURRENT_IP=192.168.178.94"
findstr /C:"SERVER_URL" warehouse_client.py >nul 2>&1
if %errorLevel% equ 0 (
    for /f "tokens=2 delims=/" %%a in ('findstr /C:"ws://" warehouse_client.py') do (
        for /f "tokens=1 delims=:" %%b in ("%%a") do set "CURRENT_IP=%%b"
    )
)

echo 1. IP адрес СЕРВЕРА
echo    Текущий: %CURRENT_IP%
echo.

set /p "NEW_IP=   Введите новый IP (или Enter для пропуска): "

if not "%NEW_IP%"=="" (
    echo.
    echo    🔧 Обновление IP адреса...

    powershell -Command "(Get-Content warehouse_client.py) -replace 'ws://[0-9.]+:', 'ws://%NEW_IP%:' | Set-Content warehouse_client.py.tmp"
    move /y warehouse_client.py.tmp warehouse_client.py >nul 2>&1

    echo    ✅ IP адрес обновлен: %NEW_IP%
    echo.
) else (
    echo    ⏭️  Пропущено
    echo.
)

REM Проверка сетевых путей
echo 2. Путь к шаблонам этикеток
echo.

set "TEMPLATE_PATH=\\server01\data\maks\drucken\etiketten"
findstr /C:"templates_folder" warehouse_client.py >nul 2>&1

echo    Текущий: %TEMPLATE_PATH%
echo.

if exist "%TEMPLATE_PATH%" (
    echo    ✅ Папка доступна
) else (
    color 0C
    echo    ❌ ВНИМАНИЕ: Папка не найдена!
    echo.
    echo    Нужно настроить доступ к сетевой папке:
    echo    1. Откройте warehouse_client.py в блокноте
    echo    2. Найдите 'templates_folder'
    echo    3. Укажите правильный путь к шаблонам
)
echo.

REM ═══════════════════════════════════════════════════════════════
REM СОЗДАНИЕ ЯРЛЫКОВ
REM ═══════════════════════════════════════════════════════════════

echo Создание ярлыков...
echo.

REM Ярлык на рабочем столе
set "DESKTOP=%USERPROFILE%\Desktop"
set "SHORTCUT=%DESKTOP%\WISO Склад.lnk"
set "TARGET=%~dp0start_warehouse.bat"

powershell -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%SHORTCUT%'); $Shortcut.TargetPath = '%TARGET%'; $Shortcut.WorkingDirectory = '%~dp0'; $Shortcut.IconLocation = 'shell32.dll,21'; $Shortcut.Description = 'WISO GoLabel - Клиент Склада'; $Shortcut.Save()"

if exist "%SHORTCUT%" (
    echo ✅ Ярлык создан на рабочем столе
) else (
    echo ⚠️  Не удалось создать ярлык на рабочем столе
)

REM Ярлык в автозагрузке
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "STARTUP_SHORTCUT=%STARTUP%\WISO Склад.lnk"

powershell -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%STARTUP_SHORTCUT%'); $Shortcut.TargetPath = '%TARGET%'; $Shortcut.WorkingDirectory = '%~dp0'; $Shortcut.IconLocation = 'shell32.dll,21'; $Shortcut.Description = 'WISO GoLabel - Клиент Склада'; $Shortcut.Save()"

if exist "%STARTUP_SHORTCUT%" (
    echo ✅ Ярлык добавлен в автозагрузку
) else (
    echo ⚠️  Не удалось добавить в автозагрузку
)
echo.

REM ═══════════════════════════════════════════════════════════════
REM ЗАВЕРШЕНИЕ
REM ═══════════════════════════════════════════════════════════════

color 0A
echo.
echo ╔═══════════════════════════════════════════════════════════════╗
echo ║                   ✅ УСТАНОВКА ЗАВЕРШЕНА!                      ║
echo ╔═══════════════════════════════════════════════════════════════╝
echo.
echo 📋 Что дальше:
echo.
echo 1. Убедитесь, что СЕРВЕР запущен
echo 2. Убедитесь, что GoLabel установлен
echo 3. Убедитесь, что принтер подключен
echo.
echo 4. Запустите ярлык "WISO Склад" на рабочем столе
echo    (или start_warehouse.bat)
echo.
echo 5. В окне программы должно быть "🟢 Подключен"
echo.
echo ⚠️  ВАЖНО - Проверьте настройки:
echo.
echo    Если нужно изменить настройки:
echo    • Откройте warehouse_client.py в блокноте
echo    • Найдите раздел CONFIG
echo    • Измените:
echo      - SERVER_URL (IP сервера)
echo      - exe_path (путь к GoLabel.exe)
echo      - templates_folder (путь к шаблонам)
echo      - box_template_name (имя шаблона коробки)
echo.
echo 📖 Подробно в CONFIG_GUIDE.md
echo.
echo ✨ Программа запускается автоматически при включении компьютера!
echo.
pause
