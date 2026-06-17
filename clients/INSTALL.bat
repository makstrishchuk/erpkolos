@echo off
chcp 65001 >nul
title WISO GoLabel - Установка
color 0A

echo ════════════════════════════════════════════════════════
echo            WISO GoLabel - Установка
echo ════════════════════════════════════════════════════════
echo.

REM Проверка прав администратора
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ❌ ОШИБКА: Требуются права администратора!
    echo.
    echo Закройте это окно и запустите файл INSTALL.bat
    echo правой кнопкой мыши → "Запуск от имени администратора"
    echo.
    pause
    exit /b 1
)

echo ✓ Права администратора подтверждены
echo.

REM ============================================
REM ПРОВЕРКА PYTHON
REM ============================================
echo [1/4] Проверка Python...
python --version >nul 2>&1
if %errorLevel% equ 0 (
    echo ✓ Python уже установлен
    python --version
) else (
    echo ❌ Python не найден
    echo.
    echo Скачиваю Python 3.11.9...

    REM Скачиваем Python
    powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile '%TEMP%\python_installer.exe'}"

    if not exist "%TEMP%\python_installer.exe" (
        echo ❌ Не удалось скачать Python
        echo.
        echo Скачайте Python вручную с https://www.python.org/downloads/
        pause
        exit /b 1
    )

    echo ✓ Python скачан
    echo.
    echo Устанавливаю Python (подождите 1-2 минуты)...

    REM Устанавливаем Python
    "%TEMP%\python_installer.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0

    REM Ждем завершения установки
    timeout /t 30 /nobreak >nul

    REM Удаляем установщик
    del "%TEMP%\python_installer.exe" >nul 2>&1

    REM Обновляем PATH
    set "PATH=%PATH%;C:\Program Files\Python311;C:\Program Files\Python311\Scripts"

    echo ✓ Python установлен
    echo.
    echo ВАЖНО: Перезапустите компьютер после завершения установки!
    echo.
)
echo.

REM ============================================
REM ПРОВЕРКА PIP
REM ============================================
echo [2/4] Проверка pip...
python -m pip --version >nul 2>&1
if %errorLevel% equ 0 (
    echo ✓ pip найден
) else (
    echo ❌ pip не найден, устанавливаю...
    python -m ensurepip --default-pip
    echo ✓ pip установлен
)
echo.

REM ============================================
REM УСТАНОВКА ЗАВИСИМОСТЕЙ
REM ============================================
echo [3/4] Установка зависимостей...
echo.
echo Устанавливаю необходимые библиотеки...
echo (это может занять 2-3 минуты)
echo.

REM Обновляем pip
python -m pip install --upgrade pip >nul 2>&1

REM Устанавливаем зависимости
python -m pip install websockets >nul 2>&1
if %errorLevel% neq 0 (
    echo ❌ Ошибка установки websockets
) else (
    echo ✓ websockets установлен
)

python -m pip install requests >nul 2>&1
if %errorLevel% neq 0 (
    echo ❌ Ошибка установки requests
) else (
    echo ✓ requests установлен
)

echo.

REM ============================================
REM ПРОВЕРКА ФАЙЛОВ
REM ============================================
echo [4/4] Проверка файлов программы...
echo.

if not exist "unified_client.py" (
    echo ❌ ОШИБКА: Файл unified_client.py не найден!
    echo.
    echo Скопируйте unified_client.py в папку:
    echo %CD%
    echo.
    pause
    exit /b 1
)
echo ✓ unified_client.py найден

if not exist "START_CLIENT.bat" (
    echo ⚠ START_CLIENT.bat не найден, создаю...

    (
        echo @echo off
        echo title WISO GoLabel - Клиент
        echo cd /d "%%~dp0"
        echo python unified_client.py
        echo pause
    ) > START_CLIENT.bat

    echo ✓ START_CLIENT.bat создан
) else (
    echo ✓ START_CLIENT.bat найден
)

echo.
echo ════════════════════════════════════════════════════════
echo            Установка завершена!
echo ════════════════════════════════════════════════════════
echo.
echo Теперь вы можете запустить программу:
echo 1. Дважды кликните на START_CLIENT.bat
echo 2. Или запустите: python unified_client.py
echo.

REM Проверяем, нужна ли перезагрузка
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo ⚠ ВНИМАНИЕ: Перезагрузите компьютер для применения изменений!
    echo.
)

echo Желаете запустить программу сейчас? (Y/N)
set /p launch="Ваш выбор: "
if /i "%launch%"=="Y" (
    echo.
    echo Запускаю клиент...
    start "" cmd /c START_CLIENT.bat
)

echo.
pause
