@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo.
echo ============================================================
echo   GLORY2YAHPUB - GIT COMMIT + PUSH TO MAIN
echo ============================================================
echo.

git --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Git is not installed or not in PATH.
  echo Download from: https://git-scm.com/download/win
  pause
  exit /b 1
)

echo [1/8] Checking current branch...
for /f "tokens=*" %%i in ('git branch --show-current') do set CUR_BRANCH=%%i
echo       Current branch: !CUR_BRANCH!

echo.
echo [2/8] Ensuring we are on MAIN branch...
if /i "!CUR_BRANCH!"=="main" (
  echo       OK - already on main
) else (
  echo       Switching to main...
  git show-ref --verify --quiet refs/heads/main
  if errorlevel 1 (
    echo       Branch 'main' not found - creating from current...
    git checkout -b main
  ) else (
    git switch main
  )
)

echo.
echo [3/8] Setting remote origin to https://github.com/stanionic/Glory2yah-.git ...
git remote get-url origin >nul 2>&1
if errorlevel 1 (
  echo       Origin missing - adding now...
  git remote add origin https://github.com/stanionic/Glory2yah-.git
) else (
  echo       Updating origin URL...
  git remote set-url origin https://github.com/stanionic/Glory2yah-.git
)
git remote -v

echo.
echo [4/8] Staging ALL changes...
git add -A

echo.
echo       Changes staged:
git --no-pager status --short

echo.
echo [5/8] Checking if anything staged...
git diff --cached --quiet
if errorlevel 1 (
  echo [6/8] Creating commit...
  git commit -m "Update UI modernization, session persistence, admin CRUD, clean start scripts"
  if errorlevel 1 (
    echo [ERROR] Commit failed.
    pause
    exit /b 1
  )
) else (
  echo       Nothing staged to commit - skipping commit step.
)

echo.
echo [7/8] Pushing to origin main (with -u to set upstream)...
git push -u origin main
if errorlevel 1 (
  echo.
  echo [WARNING] Push failed!
  echo * If remote has changes (README/LICENSE etc.), run these commands:
  echo       git pull --rebase origin main
  echo       git push -u origin main
  echo * If auth/password issue: set Personal Access Token in GitHub,
  echo   use GitHub Desktop, or run 'gh auth login'
  pause
  exit /b 1
)

echo.
echo ============================================================
echo   ✅ ALL DONE!
echo ============================================================
echo.
git --no-pager log --oneline -3
echo.
echo 🌐 Your repo: https://github.com/stanionic/Glory2yah-
echo.
pause
endlocal
exit /b 0
