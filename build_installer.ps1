$ErrorActionPreference = 'Stop'
$proj = 'D:\Tools\Dev\AIGC_Detector'
$vp = "$proj\.venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $vp)) {
    Write-Host "ERROR: venv not found. Run sync_to_d.bat first." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Push-Location "$proj\installer"
& $vp -m PyInstaller --noconfirm --clean --onefile --noconsole `
    --name "AIGC_Toolkit_Setup" `
    --add-data "$proj\app;app" `
    installer.py
$code = $LASTEXITCODE
Pop-Location

if ($code -eq 0) {
    Write-Host "SUCCESS: $proj\installer\dist\AIGC_Toolkit_Setup.exe" -ForegroundColor Green
} else {
    Write-Host "Packaging FAILED." -ForegroundColor Red
}
Read-Host "Press Enter to close"
