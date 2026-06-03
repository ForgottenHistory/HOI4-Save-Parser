@echo off
echo ==========================================
echo HOI4 LIVE GAME DATA PARSER
echo ==========================================
echo This script will parse your latest HOI4 autosave every 5 minutes
echo Press Ctrl+C to stop
echo.

cd /d "%~dp0"

:loop
echo [%time%] Checking for latest autosave...
python scripts\parse_latest_autosave.py

if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Failed to parse autosave
) else (
    echo [SUCCESS] Game data updated!
)

echo.
echo Waiting 5 minutes before next check...
echo Press Ctrl+C to stop, or close this window.
echo.

timeout /t 300 /nobreak > nul
goto loop