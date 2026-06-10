@echo off
echo ========================================
echo MANDEMMAPBAW - Deployment Setup
echo ========================================
echo.

REM Check if git is initialized
if not exist ".git" (
    echo Initializing Git repository...
    git init
    git branch -M main
)

echo Creating/checking deployment files...

REM Check for render.yaml
if not exist "render.yaml" (
    echo web: gunicorn app:app > Procfile
)

if not exist ".gitignore" (
    echo .venv/ > .gitignore
    echo venv/ >> .gitignore
    echo __pycache__/ >> .gitignore
    echo *.pyc >> .gitignore
    echo *.db >> .gitignore
    echo .env >> .gitignore
)

echo.
echo [OK] Deployment files ready!
echo.
echo Next steps:
echo.
echo 1. Commit your code:
echo    git add .
echo    git commit -m "Deploy MANDEMMAPBAW"
echo.
echo 2. Push to GitHub:
echo    git remote add origin https://github.com/YOUR_USERNAME/mandemmapbaw.git
echo    git push -u origin main
echo.
echo 3. Deploy on Render.com:
echo    - Go to https://render.com
echo    - Sign in with GitHub
echo    - New Web Service
echo    - Connect your repo
echo    - Click Create
echo.
echo 4. Your app will be live!
echo.
pause
