@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
title CLEAR ONLINE BETS - DANGER

:: ============================================================
::   DANGER: Clear all online injected bet records
::   This is IRREVERSIBLE. Local localStorage is unaffected.
::   Requires manual "YES" confirmation inside the script.
:: ============================================================

cd /d "%~dp0"

echo.
echo  ============================================================
echo    D A N G E R   -   C L E A R   O N L I N E   B E T S
echo  ============================================================
echo.
echo  This script will DELETE ALL online injected bet records.
echo  The operation is irreversible.
echo  (Browser-side localStorage data will NOT be touched.)
echo.

"C:\Users\Jin\AppData\Local\Programs\Python\Python312\python.exe" "%~dp0clear_bets.py"

echo.
echo.
pause
