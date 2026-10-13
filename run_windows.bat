@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run setup_windows.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -X utf8 -m dunkin_compare --interactive %*
set "DPC_EXIT_CODE=%ERRORLEVEL%"
echo.
echo Excel reports are in the reports folder. Check each workbook's Store Status sheet.
if not "%DPC_EXIT_CODE%"=="0" echo Some stores were skipped, incomplete, or failed. Review the output above.
pause
exit /b %DPC_EXIT_CODE%
