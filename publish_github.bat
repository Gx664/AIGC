@echo off
title Publish to GitHub
rem Resolve portable git dynamically (dev root folder was renamed across machines)
set "GIT="
for /d %%D in ("D:\*") do (
    if exist "%%~fD\Dev\Git\cmd\git.exe" set "GIT=%%~fD\Dev\Git\cmd\git.exe"
)
if "%GIT%"=="" set "GIT=D:\DevTools\Dev\Git\cmd\git.exe"
if not exist "%GIT%" set "GIT=git"
echo Using git: %GIT%
echo ============================================
echo  AIGC Detector Toolkit - Publish to GitHub
echo ============================================
echo.
echo Step 1: Make sure your VPN is connected (GitHub needs it in CN).
echo Step 2: Default repo is preconfigured below; press Enter to accept
echo         it, or paste another repo URL.
echo.
set "REPO_URL=https://github.com/Gx664/AIGC.git"
set /p REPO_URL=Enter GitHub repo URL [%REPO_URL%]: 
if "%REPO_URL%"=="" (
    echo No URL entered. Cancelled.
    pause
    exit /b 1
)
echo.
echo Configuring remote...
"%GIT%" remote remove origin 2>nul
"%GIT%" remote add origin "%REPO_URL%"
"%GIT%" config credential.helper manager
"%GIT%" config http.postBuffer 524288000
"%GIT%" config http.version HTTP/1.1
echo Pushing (GitHub login window will pop up on first push)...
"%GIT%" push -u origin main
if not errorlevel 1 goto published
echo.
echo Push rejected: the remote repo has an initial commit (e.g. README).
echo Or the network dropped mid-push. Type y to retry with force push, or n to cancel:
set /p FORCE=Force push? [y/n]: 
if /i "%FORCE%"=="y" goto forcepush
echo Cancelled.
pause
exit /b 1
:forcepush
set ATTEMPT=0
:retry
set /a ATTEMPT+=1
echo Pushing (attempt %ATTEMPT% of 3)...
"%GIT%" push -u origin main --force
if not errorlevel 1 goto published
if %ATTEMPT% geq 3 goto failed
echo Connection dropped, retrying in 3 seconds...
timeout /t 3 /nobreak >nul
goto retry
:failed
echo.
echo Push failed after 3 attempts: check VPN connection and try again.
pause
exit /b 1
:published
echo.
echo Published! Open in browser: %REPO_URL:.git=%
echo.
pause
