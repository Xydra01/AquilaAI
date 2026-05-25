# Pull HauhauCS base + create aquila_heretic on stock Ollama (default port 11434).
# Requires: .\scripts\ollama-serve-stock.ps1 running in another terminal.

param(
    [int]$Port = 11434
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$StockExe = Join-Path $RepoRoot "tools\ollama-stock\ollama.exe"
$Modelfile = Join-Path $RepoRoot "Modelfile.Heretic"
$BaseModel = "hf.co/HauhauCS/Qwen3.5-9B-Uncensored-HauhauCS-Aggressive:Q4_K_M"

if (-not (Test-Path $StockExe)) {
    & (Join-Path $PSScriptRoot "install-ollama-stock.ps1")
}

$env:OLLAMA_HOST = "http://127.0.0.1:$Port"

Write-Host "OLLAMA_HOST = $env:OLLAMA_HOST"
Write-Host "Pulling $BaseModel ..."
& $StockExe pull $BaseModel

Write-Host "Creating aquila_heretic from Modelfile.Heretic ..."
& $StockExe create aquila_heretic -f $Modelfile

Write-Host ""
Write-Host "Smoke test (API)..."
$body = '{"model":"aquila_heretic","prompt":"Reply with exactly: ok","stream":false}'
$resp = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/generate" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 180
Write-Host "Response:" $resp.response

Write-Host ""
Write-Host "Done. Set .env:"
Write-Host "  OLLAMA_BASE_URL=http://127.0.0.1:$Port"
Write-Host "  OLLAMA_MODEL=aquila_heretic"
