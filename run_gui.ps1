# run_gui.ps1 - Launch Aquila AI GUI
$cudaExe = Join-Path $PSScriptRoot "build\msvc-release-cuda\apps\aquila_gui\aquila_gui.exe"
$releaseExe = Join-Path $PSScriptRoot "build\msvc-release\apps\aquila_gui\aquila_gui.exe"

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  Aquila AI Framework - Launching GUI" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

if (Test-Path $cudaExe) {
    Write-Host "[INFO] Launching GPU-accelerated binary [build\msvc-release-cuda]..." -ForegroundColor Green
    Start-Process -FilePath $cudaExe -ArgumentList $args
} elseif (Test-Path $releaseExe) {
    Write-Host "[INFO] Launching release binary [build\msvc-release]..." -ForegroundColor Yellow
    Start-Process -FilePath $releaseExe -ArgumentList $args
} else {
    Write-Host "[ERROR] aquila_gui.exe not found! Please build with scripts\msvc-dev.cmd first." -ForegroundColor Red
    exit 1
}
