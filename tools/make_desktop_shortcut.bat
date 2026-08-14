@echo off
rem Creates a desktop shortcut to AIGC_Dashboard.exe (run once)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws=New-Object -ComObject WScript.Shell; $desktop=[Environment]::GetFolderPath('Desktop'); $s=$ws.CreateShortcut($desktop+'\AIGC_Dashboard.lnk'); $s.TargetPath='%~dp0dist\AIGC_Dashboard.exe'; $s.WorkingDirectory='%~dp0dist'; $s.Description='AI 检测工具箱数据看板'; $s.Save()"
echo Desktop shortcut created: AIGC_Dashboard.lnk
pause
