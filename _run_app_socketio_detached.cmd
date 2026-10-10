@echo off
rem Detached launcher for Glory2YahPub that serves HTTP **and** WebSocket/Socket.IO.
rem Konferans (media zoom/scroll + live pen relays) needs websockets, so this runs
rem _start_server_local.py (socketio.run) instead of _run_server.py (plain app.run).
cd /d "c:\Users\Ops\OneDrive\Desktop\dev\Glory2YahPub - Copy"
rem Read PORT from .env so local runs match the configured port (defaults to 8080).
set "PORT=8080"
for /f "usebackq tokens=1,* delims==" %%a in (".env") do if /I "%%a"==PORT set "PORT=%%b"
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
set FLASK_ENV=development
".venv\Scripts\python.exe" "_start_server_local.py" >> "logs\run_socketio_app.log" 2>> "logs\run_socketio_app.err.log"
