# Quick check that Ollama is reachable and list installed models.
# TurboQuant is active only when serve was started via ollama-serve-turboquant.*.
# Compare VRAM in Task Manager with/without TQ on the same long prompt.

$base = if ($env:OLLAMA_BASE_URL) { $env:OLLAMA_BASE_URL.TrimEnd("/") } else { "http://127.0.0.1:11434" }

Write-Host "Ollama base: $base"
try {
    $tags = Invoke-RestMethod -Uri "$base/api/tags" -TimeoutSec 5
    $names = $tags.models | ForEach-Object { $_.name }
    Write-Host "Models: $($names -join ', ')"
    foreach ($want in @("aquila", "aquila-tq-32k", "aquila-tq-64k", "aquila-tq-96k")) {
        if ($names -match [regex]::Escape($want)) {
            Write-Host "  [ok] $want"
        } else {
            Write-Host "  [--] $want (not installed - ollama create ...)"
        }
    }
} catch {
    Write-Host "ERROR: Ollama not reachable. Start: .\scripts\ollama-serve-turboquant.ps1" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "TurboQuant env (current shell - serve may use different vars):"
Write-Host "  OLLAMA_KV_CACHE_TYPE   = $(if ($env:OLLAMA_KV_CACHE_TYPE) { $env:OLLAMA_KV_CACHE_TYPE } else { '<unset>' })"
Write-Host "  OLLAMA_NEW_ENGINE      = $(if ($env:OLLAMA_NEW_ENGINE) { $env:OLLAMA_NEW_ENGINE } else { '<unset>' })"
Write-Host "  OLLAMA_FLASH_ATTENTION = $(if ($env:OLLAMA_FLASH_ATTENTION) { $env:OLLAMA_FLASH_ATTENTION } else { '<unset>' })"
Write-Host ""
Write-Host "If TQ is unsupported, upgrade Ollama or build from ollama/ollama PR #15505."
