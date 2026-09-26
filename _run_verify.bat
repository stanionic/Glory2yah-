@echo off
cd /d "%~dp0"
python _verify_notif.py > _notif_stdout.txt 2>&1
echo EXIT_CODE=%ERRORLEVEL% >> _notif_stdout.txt
