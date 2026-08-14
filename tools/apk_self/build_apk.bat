@echo off
rem AIGC 数据看板 APK 打包脚本（调用 build_apk.ps1）
rem 用法: 先编辑 assets/posthog_key.txt 填入你的密钥，再双击本文件
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_apk.ps1" %*
pause
