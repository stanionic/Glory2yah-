@echo off
rem Detached launcher for Glory2YahPub (used via Task Scheduler so it survives shell sessions).
cd /d "c:\Users\Ops\OneDrive\Desktop\dev\Glory2YahPub - Copy"
rem Read PORT from .env so local runs match the configured port (defaults to 5000).
set "PORT=5000"
for /f "usebackq tokens=1,* delims==" %%a in (".env") do if /I "%%a"=="PORT" set "PORT=%%b"
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
set FLASK_ENV=development
".venv\Scripts\python.exe" "_run_server.py" >> "logs\run_manual_app.log" 2>> "logs\run_manual_app.err.log"