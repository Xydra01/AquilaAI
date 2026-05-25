# Stock Ollama on port 11434 (default Aquila / HauhauCS path).
# Install first: .\scripts\install-ollama-stock.ps1
# TurboQuant (optional): .\scripts\ollama-serve-turboquant-port.ps1  → 11435

param(
    [int]$Port = 11434
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$StockExe = Join-Path $RepoRoot "tools\ollama-stock\ollama.exe"

if (-not (Test-Path $StockExe)) {
    Write-Host 'tools\ollama-stock\ollama.exe not found - running install...' -ForegroundColor Yellow
    & (Join-Path $PSScriptRoot "install-ollama-stock.ps1")
}

Remove-Item Env:OLLAMA_KV_CACHE_TYPE -ErrorAction SilentlyContinue
Remove-Item Env:OLLAMA_NEW_ENGINE -ErrorAction SilentlyContinue
Remove-Item Env:OLLAMA_FLASH_ATTENTION -ErrorAction SilentlyContinue

$env:OLLAMA_HOST = "127.0.0.1:$Port"
Write-Host "Stock Ollama serve on $env:OLLAMA_HOST"
Write-Host "  Binary: $StockExe"
& $StockExe --version
Write-Host ""
Write-Host "Aquila .env: OLLAMA_BASE_URL=http://127.0.0.1:$Port"
Write-Host 'TurboQuant (other terminal): .\scripts\ollama-serve-turboquant-port.ps1'
Write-Host ""
& $StockExe serve
