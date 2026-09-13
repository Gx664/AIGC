$ErrorActionPreference = 'Stop'

# 打包安装器（2026-09 起的流程）
# 要求：仓库根目录下有 .build_venv（带 tkinter 的 Python 3.12 + pyinstaller）
# 首次创建（任选一个带 tkinter 的 Python 3.12）：
#   py -3.12 -m venv .build_venv
#   .build_venv\Scripts\python.exe -m pip install pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple
# 说明：安装器界面为 tkinter；Python 3.13 官方版无 tkinter，勿用。

$proj = $PSScriptRoot
$py = Join-Path $proj '.build_venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $py)) {
    Write-Host "ERROR: build venv not found: $py" -ForegroundColor Red
    Write-Host "Create it first (see comments at top of this script)."
    Read-Host "Press Enter to exit"
    exit 1
}

Push-Location $proj
& $py -m PyInstaller --noconfirm --clean --onefile --noconsole `
    --name "AIGC_Toolkit_Setup" `
    --add-data "$proj\app;app" `
    (Join-Path $proj 'installer\installer.py')
$code = $LASTEXITCODE
Pop-Location

if ($code -eq 0) {
    Write-Host "SUCCESS: $(Join-Path $proj 'dist\AIGC_Toolkit_Setup.exe')" -ForegroundColor Green
} else {
    Write-Host "Packaging FAILED." -ForegroundColor Red
}
Read-Host "Press Enter to close"
