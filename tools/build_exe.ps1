# Build the three shipping executables (restored 2026-09-24).
#
#   1) dist\uninstaller.exe         <- installer\uninstaller.py (standalone uninstaller)
#   2) app\first_run_gui.exe        <- app\first_run.py      (first-run bootstrapper)
#   3) dist\AIGC_Toolkit_Setup.exe  <- installer\installer.py (installer; embeds app\ and 1+2)
#
# ORDER MATTERS. The installer packages files as data (`--add-data`), so the
# uninstaller and the bootstrapper must be rebuilt FIRST. Build the installer
# first and the copies inside it are stale, so users install old code
# (hit on 2026-09-24: the shipped bootstrapper still pulled the wrong `docx`
# package, and the installer had no engines_calibration.json at all).
#
# Both GUIs are tkinter, so the interpreter needs tkinter AND pyinstaller.
# The original author's script (build_installer.ps1, dropped from the repo)
# used a local .build_venv; we fall back to the conda pytorch env.
#
# Comments are English on purpose: PowerShell 5.1 reads BOM-less files as GBK
# and chokes on Chinese comments.
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_exe.ps1

$ErrorActionPreference = 'Stop'

$proj = Split-Path -Parent $PSScriptRoot

$candidates = @(
    (Join-Path $proj '.build_venv\Scripts\python.exe'),
    'C:\ProgramData\miniconda3\envs\pytorch\python.exe'
)
$py = $null
foreach ($c in $candidates) {
    if (Test-Path -LiteralPath $c) { $py = $c; break }
}
if (-not $py) {
    Write-Host "ERROR: no build interpreter found (need tkinter + pyinstaller)." -ForegroundColor Red
    Write-Host "Tried: $($candidates -join ' ; ')"
    exit 1
}

& $py -c "import tkinter, PyInstaller, sys; print('build python:', sys.executable); print('tk', tkinter.TkVersion, '/ pyinstaller', PyInstaller.__version__)"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: interpreter lacks tkinter or pyinstaller." -ForegroundColor Red
    exit 1
}

$work = Join-Path $proj 'build'
$appdir = Join-Path $proj 'app'

Push-Location $proj
try {
    Write-Host "`n=== [1/3] dist\uninstaller.exe ===" -ForegroundColor Cyan
    & $py -m PyInstaller --noconfirm --clean --onefile --noconsole `
        --name 'uninstaller' `
        --icon (Join-Path $appdir 'assets\icon.ico') `
        --distpath (Join-Path $proj 'dist') `
        --workpath (Join-Path $work 'uninstaller') `
        --specpath $work `
        (Join-Path $proj 'installer\uninstaller.py')
    if ($LASTEXITCODE -ne 0) { throw 'uninstaller build failed' }

    Write-Host "`n=== [2/3] app\first_run_gui.exe ===" -ForegroundColor Cyan
    & $py -m PyInstaller --noconfirm --clean --onefile --noconsole `
        --name 'first_run_gui' `
        --icon (Join-Path $appdir 'assets\icon.ico') `
        --add-data "$(Join-Path $appdir 'core');core" `
        --add-data "$(Join-Path $appdir 'assets\icon.ico');app/assets" `
        --distpath $appdir `
        --workpath (Join-Path $work 'first_run') `
        --specpath $work `
        (Join-Path $appdir 'first_run.py')
    if ($LASTEXITCODE -ne 0) { throw 'first_run_gui build failed' }

    Write-Host "`n=== [3/3] dist\AIGC_Toolkit_Setup.exe ===" -ForegroundColor Cyan
    & $py -m PyInstaller --noconfirm --clean --onefile --noconsole `
        --name 'AIGC_Toolkit_Setup' `
        --icon (Join-Path $appdir 'assets\icon.ico') `
        --add-data "$appdir;app" `
        --add-data "$(Join-Path $proj 'dist\uninstaller.exe');." `
        --distpath (Join-Path $proj 'dist') `
        --workpath (Join-Path $work 'installer') `
        --specpath $work `
        (Join-Path $proj 'installer\installer.py')
    if ($LASTEXITCODE -ne 0) { throw 'installer build failed' }
}
finally {
    Pop-Location
}

Write-Host "`n=== artifacts ===" -ForegroundColor Green
Get-Item (Join-Path $proj 'dist\uninstaller.exe'),
         (Join-Path $appdir 'first_run_gui.exe'),
         (Join-Path $proj 'dist\AIGC_Toolkit_Setup.exe') |
    Select-Object Name, Length, LastWriteTime | Format-Table -AutoSize

# Leave the tree clean. uninstaller.exe was only an input for the installer's
# --add-data (it is copied into the install folder at install time), and build\
# is PyInstaller scratch. Neither is tracked by git, so keeping them around
# just makes the working tree look like it has leftovers.
Remove-Item (Join-Path $proj 'dist\uninstaller.exe') -Force -ErrorAction SilentlyContinue
Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "cleaned: dist\uninstaller.exe and build\ removed (the next build recreates both)" -ForegroundColor DarkGray
