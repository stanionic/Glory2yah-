@echo off
setlocal enabledelayedexpansion

echo.
echo ============================================================
echo   GLORY2YAHPUB SERVER - STARTING VIA CMD LAUNCHER
echo ============================================================
echo.

cd /d "%~dp0"

set SECRET_KEY=glory2yah_secret_key_2024_secure_token_32chars_long
set ADMIN_PASSWORD=admin123456
set FLASK_ENV=development

echo [INFO] Working directory: %cd%
echo [INFO] Environment variables set.
echo [INFO] Launching Flask app on http://localhost:8080 ...
echo.
echo ============================================================
echo   OPEN YOUR BROWSER TO: http://localhost:8080
echo ============================================================
echo.

py -3 -c "from app import create_app; create_app().run(host='0.0.0.0', port=8080, debug=False, use_reloader=False, threaded=True)"

endlocal
