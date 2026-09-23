@echo off
rem Requires Python 3.10+ with torch / transformers installed.
rem If a .venv exists at the repo root it is used automatically.
set "PY=python"
if exist "%~dp0..\.venv\Scripts\python.exe" set "PY=%~dp0..\.venv\Scripts\python.exe"

echo [1/2] Downloading model (~400MB, via mirror)...
"%PY%" "%~dp0download_simpleai_model.py"
if errorlevel 1 (
  echo DOWNLOAD FAILED - check network and retry
  pause
  exit /b 1
)
echo.
echo [2/2] Running offline self-test of the detection engines...
"%PY%" "%~dp0test_detect.py"
echo.
echo DONE
pause
