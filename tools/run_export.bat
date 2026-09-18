@echo off
rem Scheduled task entry point: export MT5 performance and push to the website.
cd /d "%~dp0.."
python tools\export_performance.py --push
