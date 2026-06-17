@echo off
cd /d "\\server01\DATA\Maks\wiso_golabel"
echo ====================================
echo Starting WISO GoLabel Admin Client
echo ====================================
echo.
echo Working directory: %CD%
echo Server: localhost:8080
echo Client: unified_client.py
echo.
echo Launching...
python clients\unified_client.py 2>&1
echo.
echo ====================================
echo Client closed!
====================================
pause
