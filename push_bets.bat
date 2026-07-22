@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
title Push Bets

:: ============================================================
::   One-click bet records push script
::   Usage 1: Double-click -> auto-locate latest Downloads\bet_*.json
::   Usage 2: Drag JSON onto this .bat -> use specified file
:: ============================================================

cd /d "%~dp0"

if "%~1"=="" (
    echo [AUTO] Finding latest bet record JSON from Downloads ...
    echo.
    "C:\Users\Jin\AppData\Local\Programs\Python\Python312\python.exe" "%~dp0push_bets.py"
) else (
    echo [FILE] %~1
    echo.
    "C:\Users\Jin\AppData\Local\Programs\Python\Python312\python.exe" "%~dp0push_bets.py" "%~1"
)

echo.
echo.
pause
