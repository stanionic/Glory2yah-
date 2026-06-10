@echo off
echo ============================================================
echo GLORY2YAHPUB - Starting Application
echo ============================================================
echo.

cd /d "%~dp0"

echo Checking Python...
python --version
if errorlevel 1 (
    echo [ERROR] Python not found!
    pause
    exit /b 1
)

echo.
echo Starting server...
echo.
echo Access at: http://localhost:8080
echo.
echo Press Ctrl+C to stop
echo.

python run.py

if errorlevel 1 (
    echo.
    echo [ERROR] Application failed to start!
    echo Check the error messages above.
    echo.
)

pause
