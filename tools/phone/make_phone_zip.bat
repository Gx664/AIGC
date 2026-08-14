@echo off
rem Creates AIGC_Dashboard_phone.zip for easy transfer to phone
rem Uses the example config (no real key) - fill your own key on the phone
powershell -NoProfile -Command "$c = Join-Path $env:TEMP 'dashboard_config.json'; Copy-Item '%~dp0..\dashboard_config.example.json' $c -Force; Compress-Archive -Path '%~dp0..\dashboard.py',$c,'%~dp0termux_setup.sh' -DestinationPath '%~dp0AIGC_Dashboard_phone.zip' -Force; Remove-Item $c -Force"
echo Created: %~dp0AIGC_Dashboard_phone.zip
pause
