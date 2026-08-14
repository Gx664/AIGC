@echo off
echo Running telemetry pipeline self-test (send - wait - verify)...
"D:\AIGC_Detector\.venv\Scripts\python.exe" "C:\Users\user\Documents\Codex\2026-08-07\new-chat-2\work\test_telemetry.py"
echo.
echo Result also saved to work\test_telemetry_result.txt
pause
