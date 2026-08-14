@echo off
echo [1/2] Downloading model (~400MB, via mirror)...
"D:\Dev\AIGC_Detector\.venv\Scripts\python.exe" "%~dp0download_simpleai_model.py"
if errorlevel 1 (
  echo DOWNLOAD FAILED - check network and retry
  pause
  exit /b 1
)
echo.
echo [2/2] Running detection effectiveness test...
"D:\Dev\AIGC_Detector\.venv\Scripts\python.exe" "C:\Users\hkjg2\Documents\Codex\2026-08-07\new-chat-2\work\test_detection.py"
echo.
echo DONE - result saved to work\test_results.txt
pause
