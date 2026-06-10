@echo off
REM MANDEMMAPBAW - Push to GitHub Script (Windows)
REM Repository: https://github.com/stanionic/mandemmapbaw

echo ========================================================================
echo MANDEMMAPBAW - Push to GitHub (main branch)
echo ========================================================================
echo.

REM Check if we're in the right directory
if not exist "app.py" (
    echo [X] Error: app.py not found.
    echo     Are you in the mandemmapbaw-repo directory?
    pause
    exit /b 1
)

echo [OK] In correct directory
echo.

REM Check git status
echo Current Git Status:
echo ----------------------------------------------------------------------
git status
echo.

REM Check current branch
for /f "delims=" %%i in ('git branch --show-current') do set CURRENT_BRANCH=%%i
echo Current branch: %CURRENT_BRANCH%

if not "%CURRENT_BRANCH%"=="main" (
    echo.
    set /p RENAME="Rename branch to 'main'? (y/n): "
    if /i "%RENAME%"=="y" (
        git branch -M main
        echo [OK] Branch renamed to 'main'
        set CURRENT_BRANCH=main
    )
)

echo.
echo ----------------------------------------------------------------------
echo Preparing to push to GitHub
echo ----------------------------------------------------------------------
echo.

REM Check if remote exists
git remote get-url origin >nul 2>nul
if errorlevel 1 (
    echo Adding remote origin...
    git remote add origin https://github.com/stanionic/mandemmapbaw.git
    echo [OK] Remote added
) else (
    echo [OK] Remote already configured
)

echo.
echo ----------------------------------------------------------------------
echo Ready to Push!
echo ----------------------------------------------------------------------
echo.
echo Repository: https://github.com/stanionic/mandemmapbaw
echo Branch: %CURRENT_BRANCH% -^> main
echo.
echo Recent commits:
git log --oneline -5
echo.
echo Push Options:
echo 1. Normal push (recommended)
echo 2. Force push (overwrites remote)
echo 3. Cancel
echo.
set /p PUSH_OPTION="Choose option (1/2/3): "

if "%PUSH_OPTION%"=="1" goto NORMAL_PUSH
if "%PUSH_OPTION%"=="2" goto FORCE_PUSH
if "%PUSH_OPTION%"=="3" goto CANCEL
goto INVALID

:NORMAL_PUSH
echo.
echo Pushing to GitHub...
echo.

git push -u origin main

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================================================
    echo [OK] PUSH SUCCESSFUL!
    echo ========================================================================
    echo.
    echo Your code is now on GitHub:
    echo https://github.com/stanionic/mandemmapbaw
    echo.
) else (
    echo.
    echo [X] Push failed!
    echo.
    echo Common solutions:
    echo 1. If authentication failed: Use Personal Access Token
    echo 2. If repo not empty: git pull origin main --allow-unrelated-histories
    echo 3. If still failing: Run script again and choose option 2 (force push)
    echo.
)
goto END

:FORCE_PUSH
echo.
echo WARNING: Force push will OVERWRITE remote repository!
echo.
set /p CONFIRM="Are you ABSOLUTELY SURE? Type 'YES' to confirm: "

if "%CONFIRM%"=="YES" (
    echo.
    echo Force pushing to GitHub...
    echo.
    
    git push -u origin main --force
    
    if %ERRORLEVEL% EQU 0 (
        echo.
        echo ========================================================================
        echo [OK] FORCE PUSH SUCCESSFUL!
        echo ========================================================================
        echo.
        echo Remote repository overwritten:
        echo https://github.com/stanionic/mandemmapbaw
        echo.
    ) else (
        echo.
        echo [X] Force push failed!
        echo Check authentication and permissions.
        echo.
    )
) else (
    echo [X] Force push cancelled
)
goto END

:CANCEL
echo [X] Push cancelled by user
goto END

:INVALID
echo [X] Invalid option
goto END

:END
echo.
echo ========================================================================
echo Done!
echo ========================================================================
echo.
pause
