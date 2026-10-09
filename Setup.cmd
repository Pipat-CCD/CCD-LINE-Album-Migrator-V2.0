@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto install
py -3.12 -m venv .venv
if errorlevel 1 goto failed
:install
".venv\Scripts\python.exe" -m pip install -r requirements-lock.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 goto failed
echo Setup complete. Open Start.cmd and configure ExifTool and Google OAuth.
pause
exit /b 0
:failed
echo Setup failed. Please review the error above.
pause
exit /b 1
