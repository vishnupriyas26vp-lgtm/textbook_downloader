@echo off
title Tamil Nadu School Textbooks Downloader - CLI Mode
cd /d "%~dp0"
echo ========================================================
echo  Tamil Nadu School Textbooks Downloader (CLI Mode)
echo  STRICT REQUIREMENT: TAMIL MEDIUM ONLY
echo ========================================================
echo.
echo Select an option:
echo  [1] Scan Class 8 Tamil Medium books (Preview only)
echo  [2] Download Class 8 Tamil Medium books (Term 1)
echo  [3] Download Class 8 Tamil Medium books (All Terms)
echo  [4] Download Class 8, 9, 10 Tamil Medium books
echo  [5] Download ALL Classes (8, 9, 10, 11, 12)
echo.
set /p choice="Enter your choice (1-5): "

if "%choice%"=="1" python main.py --cli --classes 8 --term "Term 1" --scan-only
if "%choice%"=="2" python main.py --cli --classes 8 --term "Term 1" -y
if "%choice%"=="3" python main.py --cli --classes 8 --term "All Terms" -y
if "%choice%"=="4" python main.py --cli --classes 8,9,10 -y
if "%choice%"=="5" python main.py --cli --classes all -y

echo.
echo Press any key to close this window...
pause >nul
