# Build the official installer with the real PostHog key from the LOCAL
# posthog_config.json (not committed). The key is injected into
# installer/installer.py before building and restored afterwards, so the
# source never contains a real secret.
param(
    [string]$VenvPython = 'D:\DevTools\Dev\AIGC_Detector\.venv\Scripts\python.exe'
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$cfgPath = Join-Path $root 'posthog_config.json'
$ipPath  = Join-Path $root 'installer\installer.py'
$spec    = Join-Path $root 'AIGC_Toolkit_Setup.spec'

if (-not (Test-Path $cfgPath)) {
    throw 'posthog_config.json not found (local file, not committed).'
}
if (-not (Test-Path $VenvPython)) {
    throw "venv Python not found: $VenvPython"
}

$cfg = Get-Content $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
$key = $cfg.api_key
if (-not $key) {
    throw 'no api_key in posthog_config.json.'
}

# read original bytes so we can restore exactly after the build
$origBytes = [System.IO.File]::ReadAllBytes($ipPath)
$text = [System.Text.Encoding]::UTF8.GetString($origBytes)
$patched = $text.Replace('POSTHOG_API_KEY = ""', ('POSTHOG_API_KEY = "' + $key + '"'))
$patched = $patched.Replace('POSTHOG_HOST = "https://us.i.posthog.com"', ('POSTHOG_HOST = "' + $cfg.host + '"'))
if ($patched -eq $text) {
    throw 'inject marker not found in installer.py (POSTHOG_API_KEY = "")'
}

try {
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($ipPath, $patched, $utf8NoBom)
    Write-Host 'Key injected. Building installer...'
    Push-Location $root
    & $VenvPython -m PyInstaller --noconfirm --clean $spec
    $code = $LASTEXITCODE
    Pop-Location
    if ($code -ne 0) { throw "PyInstaller build failed (exit $code)" }
    Write-Host "OK: $(Join-Path $root 'dist\AIGC_Toolkit_Setup.exe')"
}
finally {
    [System.IO.File]::WriteAllBytes($ipPath, $origBytes)
    Write-Host 'installer.py restored to placeholder.'
}
