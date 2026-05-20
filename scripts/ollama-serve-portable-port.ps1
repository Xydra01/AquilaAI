# Portable Ollama on 11435 without TurboQuant (works with rc17 until PR #15505 build is ready).
# Aquila: OLLAMA_BASE_URL=http://127.0.0.1:11435  OLLAMA_MODEL=aquila-tq-64k
# For TurboQuant after PR build: .\scripts\ollama-serve-turboquant-port.ps1

$PortableOllama = Join-Path (Split-Path $PSScriptRoot -Parent) "tools\ollama-turboquant\ollama.exe"
if (Test-Path $PortableOllama) {
    $env:PATH = (Split-Path $PortableOllama -Parent) + ';' + $env:PATH
}
$ErrorActionPreference = "Stop"
Remove-Item Env:OLLAMA_KV_CACHE_TYPE -ErrorAction SilentlyContinue
Remove-Item Env:OLLAMA_NEW_ENGINE -ErrorAction SilentlyContinue
Remove-Item Env:OLLAMA_FLASH_ATTENTION -ErrorAction SilentlyContinue
$env:OLLAMA_HOST = "http://127.0.0.1:11435"
Write-Host "Portable Ollama serve (no TurboQuant) on $env:OLLAMA_HOST"
ollama serve
