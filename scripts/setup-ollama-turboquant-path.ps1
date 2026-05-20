# Add portable TurboQuant Ollama to the current user PATH (persistent).
# Usage: .\scripts\setup-ollama-turboquant-path.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$BinDir = Join-Path $RepoRoot "tools\ollama-turboquant"
if (-not (Test-Path (Join-Path $BinDir "ollama.exe"))) {
    Write-Host "Missing $BinDir\ollama.exe - run install-ollama-turboquant.ps1 or install-ollama-turboquant-pr.ps1 first." -ForegroundColor Red
    exit 1
}

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$parts = $userPath -split ';' | Where-Object { $_ -and ($_ -ne $BinDir) }
if ($parts -notcontains $BinDir) {
    $newPath = (@($BinDir) + $parts) -join ';'
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    $env:Path = $BinDir + ';' + $env:Path
    Write-Host "Added to user PATH: $BinDir"
} else {
    Write-Host "Already on user PATH: $BinDir"
}

Write-Host ""
Write-Host "Open a new terminal (or IDE) so PATH refreshes."
Write-Host "Verify: ollama --version  (should match portable build, not tray 0.24.0)"
Write-Host "Serve:  .\scripts\ollama-serve-turboquant-port.ps1"
Write-Host "Aquila: OLLAMA_BASE_URL=http://127.0.0.1:11435  OLLAMA_MODEL=aquila-tq-32k|64k|96k"
