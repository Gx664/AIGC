$ErrorActionPreference = 'Stop'

# [2026-09-13] 已过时（DEPRECATED）：本脚本面向旧开发目录
# (<D:\?>\Dev\Python312 / Dev\AIGC_Detector)，该目录已不存在。
# 当前仓库即开发目录（D:\AIGC\outputs\AIGC_Toolkit），无需同步。
# 保留仅作历史参考，直接运行会报错退出。

$src = Join-Path $PSScriptRoot 'AIGC_Toolkit'

# Resolve dev root dynamically (folder renamed across machines; avoid non-ASCII literals)
$devRoot = Get-ChildItem 'D:\' -Directory | Where-Object {
    Test-Path (Join-Path $_.FullName 'Dev\Python312\python.exe')
} | Select-Object -First 1
if (-not $devRoot) {
    Write-Host "ERROR: cannot locate dev root (expected <D:\?>\Dev\Python312)." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
$dst = Join-Path $devRoot.FullName 'Dev\AIGC_Detector'

if (-not (Test-Path -LiteralPath $src)) {
    Write-Host "ERROR: source not found: $src" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

New-Item -ItemType Directory -Force -Path $dst | Out-Null
robocopy $src $dst /E /XD __pycache__ .git build dist /NFL /NDL /NJH /NJS /R:1 /W:1 | Out-Null
$code = $LASTEXITCODE
if ($code -le 7) {
    Write-Host "OK: synced to $dst" -ForegroundColor Green
} else {
    Write-Host "robocopy failed with code $code" -ForegroundColor Red
}
Read-Host "Press Enter to close"
