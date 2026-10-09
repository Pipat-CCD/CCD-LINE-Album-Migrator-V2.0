@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" goto missing
".venv\Scripts\python.exe" main.py
if errorlevel 1 pause
exit /b
:missing
echo Please run Setup.cmd first.
pause
exit /b 1
