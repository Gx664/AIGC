$ErrorActionPreference = 'Stop'

# Resolve dev root dynamically (folder was renamed across machines; avoid non-ASCII literals)
$devRoot = Get-ChildItem 'D:\' -Directory | Where-Object {
    Test-Path (Join-Path $_.FullName 'Dev\Python312\python.exe')
} | Select-Object -First 1
if (-not $devRoot) {
    Write-Host "ERROR: cannot locate dev root (expected <D:\?>\Dev\Python312)." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
$proj = Join-Path $devRoot.FullName 'Dev\AIGC_Detector'
$vp = Join-Path $proj '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $vp)) {
    Write-Host "ERROR: venv not found: $vp (run sync_to_d.bat first)" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Push-Location (Join-Path $proj 'installer')
& $vp -m PyInstaller --noconfirm --clean --onefile --noconsole `
    --name "AIGC_Toolkit_Setup" `
    --add-data "$proj\app;app" `
    installer.py
$code = $LASTEXITCODE
Pop-Location

if ($code -eq 0) {
    Write-Host "SUCCESS: $(Join-Path $proj 'installer\dist\AIGC_Toolkit_Setup.exe')" -ForegroundColor Green
} else {
    Write-Host "Packaging FAILED." -ForegroundColor Red
}
Read-Host "Press Enter to close"
