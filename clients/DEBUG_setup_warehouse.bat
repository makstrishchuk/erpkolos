@echo off
REM This is a DEBUG version - it will pause on every step so you can see errors
title WISO GoLabel Warehouse - DEBUG Setup
color 0E

echo ===============================================
echo   DEBUG MODE - WAREHOUSE SETUP
echo ===============================================
echo.
echo This version will PAUSE after each step
echo so you can see any errors.
echo.
pause

echo.
echo ===============================================
echo [TEST 1] Checking if batch file works
echo ===============================================
echo.
echo If you see this - batch file is running!
echo.
pause

echo.
echo ===============================================
echo [TEST 2] Checking PowerShell
echo ===============================================
echo.
powershell -Command "Write-Host 'PowerShell works!'"
if %errorLevel% neq 0 (
    echo ERROR: PowerShell failed!
    pause
    exit /b 1
)
echo.
pause

echo.
echo ===============================================
echo [TEST 3] Checking Python
echo ===============================================
echo.
python --version
if %errorLevel% neq 0 (
    echo.
    echo Python is NOT installed!
    echo This is OK - we will install it.
    echo.
) else (
    echo.
    echo Python IS installed!
    echo.
)
pause

echo.
echo ===============================================
echo [TEST 4] Checking current directory
echo ===============================================
echo.
echo Current directory:
cd
echo.
echo Files in this directory:
dir /b *.bat *.py *.txt
echo.
pause

echo.
echo ===============================================
echo [TEST 5] Checking internet connection
echo ===============================================
echo.
echo Testing connection to python.org...
ping -n 2 www.python.org
if %errorLevel% neq 0 (
    echo.
    echo WARNING: Cannot reach python.org
    echo Check internet connection!
    echo.
) else (
    echo.
    echo Internet connection OK!
    echo.
)
pause

echo.
echo ===============================================
echo   DIAGNOSTIC COMPLETE
echo ===============================================
echo.
echo Please take a screenshot of this window
echo and send it for analysis.
echo.
echo What to check:
echo 1. Did all tests pass?
echo 2. Is Python installed?
echo 3. Are the files in correct directory?
echo 4. Is internet working?
echo.
pause

echo.
echo Do you want to continue with full installation? (Y/N)
set /p CONTINUE=Enter Y to continue:

if /i "%CONTINUE%"=="Y" (
    echo.
    echo Starting full installation...
    echo.
    call FIXED_setup_warehouse.bat
) else (
    echo.
    echo Installation cancelled.
    echo.
)

pause
