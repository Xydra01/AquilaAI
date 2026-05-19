# DEPRECATED for Windows TurboQuant: rc17 cannot run tq* on GPU (llama-server rejects cache type).
# Use install-ollama-turboquant-pr.ps1 instead.
#
# This script only downloads stock v0.30.0-rc17 if you need a non-TQ portable binary for experiments.
#
# Usage (repo root, PowerShell):
#   .\scripts\install-ollama-turboquant.ps1
#   $env:PATH = "$PWD\tools\ollama-turboquant;$env:PATH"
#   .\scripts\ollama-serve-turboquant.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (Test-Path (Join-Path $PSScriptRoot "..\Modelfile")) {
    $RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
}

$Version = "v0.30.0-rc17"
$InstallDir = Join-Path $RepoRoot "tools\ollama-turboquant"
$ZipUrl = "https://github.com/ollama/ollama/releases/download/$Version/ollama-windows-amd64.zip"
$ZipPath = Join-Path $env:TEMP "ollama-windows-amd64.zip"

Write-Host "Installing Ollama $Version to $InstallDir"

if (Test-Path $InstallDir) {
    Write-Host "Removing previous $InstallDir"
    Remove-Item -Recurse -Force $InstallDir
}
New-Item -ItemType Directory -Path $InstallDir | Out-Null

Write-Host "Downloading $ZipUrl ..."
Invoke-WebRequest -Uri $ZipUrl -OutFile $ZipPath -UseBasicParsing
Expand-Archive -Path $ZipPath -DestinationPath $InstallDir -Force
Remove-Item $ZipPath -ErrorAction SilentlyContinue

$OllamaExe = Join-Path $InstallDir "ollama.exe"
if (-not (Test-Path $OllamaExe)) {
    throw "ollama.exe not found after extract"
}

$bin = [System.IO.File]::ReadAllBytes($OllamaExe)
$hasTq3 = [System.Text.Encoding]::ASCII.GetString($bin).Contains("tq3")
$hasTq2 = [System.Text.Encoding]::ASCII.GetString($bin).Contains("tq2")

Write-Host ""
Write-Host "Installed: $OllamaExe"
& $OllamaExe --version
Write-Host "Binary includes preset string 'tq2': $hasTq2"
Write-Host "Binary includes preset string 'tq3': $hasTq3"
Write-Host ""
if (-not $hasTq3) {
    Write-Host "NOTE: tq3/tq3k need Ollama built from PR #15505 (see scripts/install-ollama-turboquant-pr.ps1)." -ForegroundColor Yellow
    Write-Host "You can still try OLLAMA_KV_CACHE_TYPE=tq2 with this build." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Stop system Ollama (tray icon or: taskkill /IM ollama.exe /F)"
Write-Host "  2. `$env:PATH = `"$InstallDir;`$env:PATH`""
Write-Host "  3. .\scripts\ollama-serve-turboquant.ps1"
Write-Host "  4. ollama create aquila-tq-64k -f Modelfile.tq-64k"
