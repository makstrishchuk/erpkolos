@echo off
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONUTF8=1
echo START DEBUG MODE...
:: Use python.exe to see server errors

:: IONOS SMTP settings for customer shipping PDF emails (test mode)
set ORDER_EMAIL_TEST_MODE=1
set ORDER_EMAIL_TEST_RECIPIENT=maxim.trischuk@gmail.com
set ORDER_EMAIL_SMTP_HOST=smtp.ionos.de
set ORDER_EMAIL_SMTP_PORT=587
set ORDER_EMAIL_SMTP_SSL=0
set ORDER_EMAIL_SMTP_STARTTLS=1
set ORDER_EMAIL_SMTP_TLS_VERIFY=0
set ORDER_EMAIL_SMTP_USER=rechnung@monolith-bakery.com
set ORDER_EMAIL_SMTP_PASSWORD=a3wk4Nfe777!r
set ORDER_EMAIL_FROM=rechnung@monolith-bakery.com

python server_unified.py
pause
