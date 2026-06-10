@echo off
echo ============================================================
echo GLORY2YAHPUB - Starting Application
echo ============================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH
    echo Please install Python 3.8+ from python.org
    pause
    exit /b 1
)

echo [OK] Python found
echo.

REM Start the application
echo Starting Glory2YahPub...
echo.
echo Access the app at:
echo   - Local:   http://localhost:8080
echo   - Network: http://YOUR_IP:8080
echo.
echo Press Ctrl+C to stop the server
echo.

python run.py

pause
