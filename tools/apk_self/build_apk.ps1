# AIGC Dashboard APK build script (self-packaged shell)
# Usage: powershell -ExecutionPolicy Bypass -File build_apk.ps1 [-OutName AIGC_Dashboard_allinone.apk]
# Before building, put your own PostHog personal_api_key into assets/posthog_key.txt.
param(
    [string]$OutName = "AIGC_Dashboard_allinone.apk"
)

$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot

# ---- toolchain paths (adjust for your machine) ----
$jdkBin     = 'D:\DevTools\tools\jdk-17.0.2\bin'
$buildTools = 'D:\WorkBuddy-old-sessions-backup-20260728-1521\2026-06-13-16-11-14\android-tools\build-tools\34.0.0'
$androidJar = 'D:\WorkBuddy-old-sessions-backup-20260728-1521\2026-06-13-16-11-14\android-tools\platforms\android-34\android.jar'
$keystore   = Join-Path $here '..\apk_build\debug.keystore'
$ksPass     = 'android'

$classesDir = Join-Path $here 'classes'
$dexDir     = Join-Path $here 'dex'
$srcDir     = Join-Path $here 'src\com\aigc\dashboard'
$assetsDir  = Join-Path $here 'assets'
$rawApk     = Join-Path $here 'raw.apk'
$alignedApk = Join-Path $here 'aligned.apk'
$outApk     = Join-Path $here $OutName

# 1. clean old build outputs
if (Test-Path $classesDir) { Remove-Item $classesDir -Recurse -Force }
if (Test-Path $dexDir) { Remove-Item $dexDir -Recurse -Force }
New-Item -ItemType Directory -Path $classesDir, $dexDir -Force | Out-Null

# 2. javac
& "$jdkBin\javac.exe" -encoding UTF-8 -source 8 -target 8 -bootclasspath $androidJar `
    -d $classesDir (Join-Path $srcDir 'LocalServer.java'), (Join-Path $srcDir 'MainActivity.java')
if ($LASTEXITCODE -ne 0) { throw "javac failed" }

# 3. d8 to dex
$env:JAVA_HOME = $jdkBin
$env:Path = "$jdkBin;$env:Path"
$classFiles = Get-ChildItem $classesDir -Recurse -Filter *.class | ForEach-Object { $_.FullName }
& "$buildTools\d8.bat" --release --min-api 21 --output $dexDir $classFiles
if ($LASTEXITCODE -ne 0) { throw "d8 failed" }

# 4. assemble new APK from base.apk template (replace dex / dashboard.html, add posthog_key.txt)
Copy-Item (Join-Path $here 'base.apk') $rawApk -Force
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::Open($rawApk, 'Update')
foreach ($name in @('classes.dex', 'assets/dashboard.html')) {
    $e = $zip.GetEntry($name)
    if ($e) { $e.Delete() }
}
$map = @{
    'classes.dex'          = (Join-Path $dexDir 'classes.dex')
    'assets/dashboard.html' = (Join-Path $assetsDir 'dashboard.html')
    'assets/posthog_key.txt' = (Join-Path $assetsDir 'posthog_key.txt')
}
foreach ($name in $map.Keys) {
    $ne = $zip.CreateEntry($name, [System.IO.Compression.CompressionLevel]::Optimal)
    $os = $ne.Open()
    $bytes = [System.IO.File]::ReadAllBytes($map[$name])
    $os.Write($bytes, 0, $bytes.Length)
    $os.Dispose()
}
$zip.Dispose()

# 5. zipalign + sign
& "$buildTools\zipalign.exe" -f 4 $rawApk $alignedApk
if ($LASTEXITCODE -ne 0) { throw "zipalign failed" }
& "$buildTools\apksigner.bat" sign --ks $keystore --ks-pass pass:$ksPass --out $outApk $alignedApk
if ($LASTEXITCODE -ne 0) { throw "apksigner failed" }
& "$buildTools\apksigner.bat" verify --print-certs $outApk

# 6. cleanup temp files
Remove-Item $rawApk, $alignedApk -Force -ErrorAction SilentlyContinue
Write-Host "OK: $outApk"
