# run_gui.ps1 - Launch Aquila AI GUI
$cudaExe = Join-Path $PSScriptRoot "build\msvc-release-cuda\apps\aquila_gui\aquila_gui.exe"
$releaseExe = Join-Path $PSScriptRoot "build\msvc-release\apps\aquila_gui\aquila_gui.exe"

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "  Aquila AI Framework - Launching GUI" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

$targetExe = if (Test-Path $cudaExe) { $cudaExe } elseif (Test-Path $releaseExe) { $releaseExe } else { $null }

if (-not $targetExe) {
    Write-Host "[ERROR] aquila_gui.exe not found! Please build with scripts\msvc-dev.cmd first." -ForegroundColor Red
    exit 1
}

if ($targetExe -eq $cudaExe) {
    Write-Host "[INFO] Launching GPU-accelerated binary [build\msvc-release-cuda]..." -ForegroundColor Green
} else {
    Write-Host "[INFO] Launching release binary [build\msvc-release]..." -ForegroundColor Yellow
}

if ($args.Count -gt 0) {
    Start-Process -FilePath $targetExe -WorkingDirectory $PSScriptRoot -ArgumentList $args
} else {
    Start-Process -FilePath $targetExe -WorkingDirectory $PSScriptRoot
}
