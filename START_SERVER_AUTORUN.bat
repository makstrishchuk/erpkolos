@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

set "WORKDIR=%SCRIPT_DIR%"
set "PYTHON_EXE=C:\Python314\python.exe"
set "LOGFILE=%WORKDIR%\task_runner.log"
set "LEGACY_BAT=%WORKDIR%\!!!!НАЖИМАТЬ СЮДА!!!!!.bat"

(
  echo ============================================================
  echo [%date% %time%] START_SERVER_AUTORUN.bat started
  echo WORKDIR=%WORKDIR%
  echo PYTHON_EXE=%PYTHON_EXE%
) >> "%LOGFILE%" 2>&1

pushd "%WORKDIR%" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
  echo [%date% %time%] ERROR: Cannot access WORKDIR >> "%LOGFILE%" 2>&1
  exit /b 3
)

echo [%date% %time%] Launching server... >> "%LOGFILE%" 2>&1
if exist "%LEGACY_BAT%" (
  echo [%date% %time%] Using legacy start script: %LEGACY_BAT% >> "%LOGFILE%" 2>&1
  call "%LEGACY_BAT%" >> "%LOGFILE%" 2>&1
) else (
  echo [%date% %time%] WARN: Legacy script not found, fallback to start_server_nogui.py >> "%LOGFILE%" 2>&1
  if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" start_server_nogui.py >> "%LOGFILE%" 2>&1
  ) else (
    echo [%date% %time%] WARN: Python not found at %PYTHON_EXE%, trying PATH python >> "%LOGFILE%" 2>&1
    python start_server_nogui.py >> "%LOGFILE%" 2>&1
  )
)
set "RC=%ERRORLEVEL%"
echo [%date% %time%] Server process exited with code %RC% >> "%LOGFILE%" 2>&1

popd
exit /b %RC%
