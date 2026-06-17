@echo off
REM === НАСТРОЙКИ ===

REM 1. Полный путь к pythonw.exe (без окна)
set "PYTHON_EXE=C:\Users\MaksTrishchuk\AppData\Local\Programs\Python\Python313\pythonw.exe"

REM 2. Полный путь к скрипту (автоматически берется из папки, где лежит батник)
set "SCRIPT_PATH=%~dp0unified_client.py"

REM === ЗАПУСК ===

REM Запускаем процесс отдельно и передаем ему полный путь к скрипту в кавычках
start "" "%PYTHON_EXE%" "%SCRIPT_PATH%"

exit