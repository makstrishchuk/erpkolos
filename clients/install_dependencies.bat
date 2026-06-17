@echo off
title Install Client Dependencies
color 0B

echo ========================================
echo   Installing Client Dependencies
echo ========================================
echo.

cd /d %~dp0

pip install --upgrade pip
pip install -r requirements.txt

if errorlevel 1 (
    color 0C
    echo.
    echo ========================================
    echo   ERROR: Installation failed!
    echo ========================================
    pause
    exit /b 1
)

color 0A
echo.
echo ========================================
echo   SUCCESS: All dependencies installed!
echo ========================================
pause
