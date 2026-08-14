@echo off
chcp 65001 >nul
title AIGC Telemetry Self-Test
set "PY=D:\Tools\Dev\AIGC_Detector\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
echo Running telemetry pipeline self-test (send - wait - verify)...
"%PY%" "%~dp0telemetry_selftest.py"
echo.
pause
