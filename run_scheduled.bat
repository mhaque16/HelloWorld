@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" exit /b 2
".venv\Scripts\python.exe" -X utf8 -m dunkin_compare.agent run
exit /b %ERRORLEVEL%
