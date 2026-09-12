@echo off
title Tamil Nadu School Textbooks Auto-Downloader
cd /d "%~dp0"
echo ==========================================================
echo Starting Tamil Medium Textbooks Auto-Downloader...
echo Opening in your web browser: http://127.0.0.1:5000
echo ==========================================================
start http://127.0.0.1:5000
python web_app.py
pause
