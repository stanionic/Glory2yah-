@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
set FLASK_ENV=development
python -u _run_local.py > logs\_app_stdout_live.txt 2> logs\_app_stderr_live.txt
echo EXIT_CODE=%ERRORLEVEL% >> logs\_app_stdout_live.txt
