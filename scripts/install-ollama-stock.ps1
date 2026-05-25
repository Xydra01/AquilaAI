# Install portable stock Ollama (Qwen 3.5 / community GGUF support) to tools\ollama-stock.
# Does NOT touch tools\ollama-turboquant (TurboQuant PR build).
#
# Usage (repo root):
#   .\scripts\install-ollama-stock.ps1
#   .\scripts\ollama-serve-stock.ps1

param(
    [string]$Version = "v0.30.0-rc23"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$InstallDir = Join-Path $RepoRoot "tools\ollama-stock"
$ZipUrl = "https://github.com/ollama/ollama/releases/download/$Version/ollama-windows-amd64.zip"
$ZipPath = Join-Path $env:TEMP "ollama-stock-windows-amd64.zip"

Write-Host "Installing stock Ollama $Version to $InstallDir"

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

Write-Host ""
Write-Host "Installed: $OllamaExe"
& $OllamaExe --version
Write-Host ""
Write-Host "Next:"
Write-Host "  1. Quit system-tray Ollama (old 0.24.x on 11434) if running"
Write-Host "  2. .\scripts\ollama-serve-stock.ps1"
Write-Host "  3. .\scripts\ollama-create-heretic.ps1"
Write-Host "  4. .env: OLLAMA_BASE_URL=http://127.0.0.1:11434  OLLAMA_MODEL=aquila_heretic"
