@echo off
title Tamil Nadu School Textbooks Downloader (Tamil Medium Only)
cd /d "%~dp0"
echo ===================================================
echo Starting Tamil Medium Textbooks Downloader GUI...
echo ===================================================
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo An error occurred. Press any key to exit.
    pause >nul
)
