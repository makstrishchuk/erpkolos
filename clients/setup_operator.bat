@echo off
title WISO GoLabel Operator Client - Auto Setup
color 0B
chcp 65001 >nul

echo ╔═══════════════════════════════════════════════════════════════╗
echo ║      WISO GOLABEL ОПЕРАТОР - АВТОМАТИЧЕСКАЯ УСТАНОВКА         ║
echo ╔═══════════════════════════════════════════════════════════════╗
echo.

echo [1/4] Проверка Python...
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

    REM Обновляем PATH
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

echo [2/4] Проверка pip...
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

echo [3/4] Установка зависимостей...
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

echo [4/4] Проверка файлов...
echo.

if not exist "operator_client.py" (
    color 0C
    echo ❌ ОШИБКА: operator_client.py не найден!
    echo.
    pause
    exit /b 1
)

echo ✅ Файлы найдены
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
echo Перед запуском нужно указать IP адрес СЕРВЕРА!
echo.

REM Пытаемся получить текущий IP из файла
set "CURRENT_IP=192.168.178.94"
findstr /C:"SERVER_URL" operator_client.py >nul 2>&1
if %errorLevel% equ 0 (
    for /f "tokens=2 delims=/" %%a in ('findstr /C:"ws://" operator_client.py') do (
        for /f "tokens=1 delims=:" %%b in ("%%a") do set "CURRENT_IP=%%b"
    )
)

echo Текущий IP сервера: %CURRENT_IP%
echo.

set /p "NEW_IP=Введите IP адрес СЕРВЕРА (или Enter для пропуска): "

if not "%NEW_IP%"=="" (
    echo.
    echo 🔧 Обновление IP адреса...

    REM Создаем временный файл с новым IP
    powershell -Command "(Get-Content operator_client.py) -replace 'ws://[0-9.]+:', 'ws://%NEW_IP%:' | Set-Content operator_client.py.tmp"

    REM Заменяем файл
    move /y operator_client.py.tmp operator_client.py >nul 2>&1

    echo ✅ IP адрес обновлен: %NEW_IP%
    echo.
) else (
    color 0E
    echo.
    echo ⚠️  IP адрес НЕ изменен!
    echo.
    echo Если сервер находится на другом компьютере:
    echo 1. Откройте operator_client.py в блокноте
    echo 2. Найдите строку SERVER_URL
    echo 3. Замените IP адрес на адрес вашего сервера
    echo.
)

REM ═══════════════════════════════════════════════════════════════
REM СОЗДАНИЕ ЯРЛЫКА
REM ═══════════════════════════════════════════════════════════════

echo Создание ярлыка на рабочем столе...

set "DESKTOP=%USERPROFILE%\Desktop"
set "SHORTCUT=%DESKTOP%\WISO Оператор.lnk"
set "TARGET=%~dp0start_operator.bat"

powershell -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%SHORTCUT%'); $Shortcut.TargetPath = '%TARGET%'; $Shortcut.WorkingDirectory = '%~dp0'; $Shortcut.IconLocation = 'shell32.dll,16'; $Shortcut.Description = 'WISO GoLabel - Клиент Оператора'; $Shortcut.Save()"

if exist "%SHORTCUT%" (
    echo ✅ Ярлык создан на рабочем столе
) else (
    echo ⚠️  Не удалось создать ярлык
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
echo 2. Запустите ярлык "WISO Оператор" на рабочем столе
echo    или start_operator.bat в этой папке
echo.
echo 3. Окно программы должно открыться
echo 4. В правом верхнем углу должно быть "🟢 Подключен"
echo.
echo ⚠️  Если видите "🔴 Отключен":
echo    - Проверьте, что сервер запущен
echo    - Проверьте IP адрес в operator_client.py
echo    - Проверьте, что порт 8080 открыт на сервере
echo.
pause
