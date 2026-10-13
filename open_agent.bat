@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo First run setup_windows.bat. Then open this app again.
  pause
  exit /b 1
)
start "Dunkin Price Agent" ".venv\Scripts\pythonw.exe" -X utf8 -m dunkin_compare.desktop
