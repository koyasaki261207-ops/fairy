@echo off
title Gemini AutoPilot - Tro ly Dieu khien May tinh Thong minh
color 0B
echo ========================================================
echo        DANG KHOI CHAY GEMINI AUTOPILOT AI...
echo ========================================================
echo.

cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py
) else (
    python main.py
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [LOI] Chuong trinh gap su co hoac da dung lai.
    pause
)
