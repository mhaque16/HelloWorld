@echo off
setlocal
cd /d "%~dp0"
set "DPC_PYTHON=py -3"
py -3 --version >nul 2>&1
if errorlevel 1 set "DPC_PYTHON=python"
%DPC_PYTHON% -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)"
if errorlevel 1 (
  echo Install Python 3.12 or newer from python.org and enable Add Python to PATH.
  pause
  exit /b 1
)
%DPC_PYTHON% -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 (
  echo Chromium download failed. The app can also use installed Microsoft Edge or Chrome.
  echo If neither is available, fix the download and rerun setup.
)
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 goto failed
echo Setup complete. Double-click open_agent.bat to open the desktop app.
pause
exit /b 0
:failed
echo Setup failed. Review the error above, fix it, and run setup_windows.bat again.
pause
exit /b 1
