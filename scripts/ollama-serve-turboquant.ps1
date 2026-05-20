# Start Ollama with TurboQuant KV-cache compression (NVIDIA recommended profile).
# Usage: from repo root:  .\scripts\ollama-serve-turboquant.ps1
# Optional: -Preset tq3k  (K-only TQ if flash attention fails)

param(
    [ValidateSet("tq2", "tq2k", "tq3", "tq3k", "tq4", "tq4k")]
    [string]$Preset = "tq3",
    [int]$Port = 11434
)

# Prefer portable TurboQuant build in repo (see install-ollama-turboquant.ps1)
$PortableOllama = Join-Path (Split-Path $PSScriptRoot -Parent) "tools\ollama-turboquant\ollama.exe"
if (Test-Path $PortableOllama) {
    $env:PATH = "$(Split-Path $PortableOllama -Parent);$env:PATH"
}

$ErrorActionPreference = "Stop"

$env:OLLAMA_NEW_ENGINE = "1"
$env:OLLAMA_KV_CACHE_TYPE = $Preset

# K+V presets require flash attention
if ($Preset -match "^tq[234]$") {
    $env:OLLAMA_FLASH_ATTENTION = "1"
} else {
    Remove-Item Env:OLLAMA_FLASH_ATTENTION -ErrorAction SilentlyContinue
}

Write-Host "TurboQuant Ollama serve"
Write-Host "  OLLAMA_NEW_ENGINE      = $env:OLLAMA_NEW_ENGINE"
Write-Host "  OLLAMA_KV_CACHE_TYPE   = $env:OLLAMA_KV_CACHE_TYPE"
if ($env:OLLAMA_FLASH_ATTENTION) {
    Write-Host "  OLLAMA_FLASH_ATTENTION = $env:OLLAMA_FLASH_ATTENTION"
}
Write-Host ""
Write-Host "Create TurboQuant models (once, other terminal):"
Write-Host "  .\scripts\ollama-create-tq-models.ps1"
Write-Host "Set in .env: OLLAMA_BASE_URL=http://127.0.0.1:$Port  OLLAMA_MODEL=aquila-tq-32k|64k|96k"
Write-Host ""
Write-Host "Rollback: restart ollama serve without this script (no OLLAMA_KV_CACHE_TYPE)."
Write-Host ""
Write-Host "If load fails with 'Unsupported cache type: tq*', you need Ollama built from PR #15505:"
Write-Host "  .\scripts\install-ollama-turboquant-pr.ps1"
Write-Host ""

$env:OLLAMA_HOST = "http://127.0.0.1:$Port"
ollama serve
