# TurboQuant Ollama on port 11435 (stock default is ollama-serve-stock.ps1 on 11434).
# Aquila: OLLAMA_BASE_URL=http://127.0.0.1:11435  OLLAMA_MODEL=aquila-tq-64k
# See docs/ollama-dual-setup.md
& "$PSScriptRoot\ollama-serve-turboquant.ps1" -Port 11435 @args
