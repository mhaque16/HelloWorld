@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup_windows.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -X utf8 -m dunkin_compare --demo
set "DPC_EXIT_CODE=%ERRORLEVEL%"
echo Demo uses invented prices. Find the DEMO workbook in reports.
pause
exit /b %DPC_EXIT_CODE%
