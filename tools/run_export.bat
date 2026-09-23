@echo off
rem Scheduled task entry point: export MT5 performance and push to the website.
rem Logs to tools\export.log (last run only).
cd /d "%~dp0.."
set PYTHON=%LOCALAPPDATA%\Programs\Python\Python312\python.exe
if not exist "%PYTHON%" set PYTHON=python
"%PYTHON%" tools\export_performance.py --push > tools\export.log 2>&1
