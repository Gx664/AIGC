@echo off
start "" http://127.0.0.1:8765
"%~dp0dist\AIGC_Dashboard.exe" 8765 0.0.0.0
pause
