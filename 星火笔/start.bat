@echo off
rem ============================================================
rem  XingHuoPen (XingHuoBi) launcher.
rem  Starts the desktop UI without a console window (pythonw).
rem  The portable Python env is bundled inside folder env\,
rem  so this whole folder can be zipped and shared as-is.
rem  Requires Windows 10+.
rem ============================================================
cd /d "%~dp0"

if not exist env\pythonw.exe (
    echo [ERROR] env\pythonw.exe not found. The bundled environment is incomplete.
    pause
    exit /b 1
)

start "" env\pythonw.exe src\main.py