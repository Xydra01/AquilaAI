# Aquila pytest health check — tiered test runs before release or heavy changes.
# Usage:
#   .\scripts\aquila-health-check.ps1 quick
#   .\scripts\aquila-health-check.ps1 smoke
#   .\scripts\aquila-health-check.ps1 full
#   .\scripts\aquila-health-check.ps1 heretic
#   .\scripts\aquila-health-check.ps1 full -Eject

param(
    [Parameter(Position = 0)]
    [ValidateSet("quick", "smoke", "full", "heretic")]
    [string]$Tier = "quick",

    [switch]$Eject
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$AgentDir = Join-Path $RepoRoot "agent"
$VenvPython = Join-Path $RepoRoot "ai-agent-env\Scripts\python.exe"

if (Test-Path $VenvPython) {
    $Python = $VenvPython
    Write-Host "Using venv: $Python"
} else {
    $Python = "python"
    Write-Host "Using system python (no ai-agent-env found)"
}

function Invoke-Pytest {
    param([string[]]$Args)
    Push-Location $AgentDir
    try {
        & $Python -m pytest @Args
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Pop-Location
    }
}

function Eject-OllamaModels {
    $base = if ($env:OLLAMA_BASE_URL) { $env:OLLAMA_BASE_URL.TrimEnd("/") } else { "http://127.0.0.1:11434" }
    $model = if ($env:OLLAMA_MODEL) { $env:OLLAMA_MODEL } else { "aquila" }
    Write-Host "Ejecting loaded models on $base (model hint: $model)..."
    try {
        $body = @{ model = $model; keep_alive = 0 } | ConvertTo-Json
        Invoke-RestMethod -Uri "$base/api/generate" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 30 | Out-Null
        Write-Host "  keep_alive=0 sent."
    } catch {
        Write-Host "  Warning: eject request failed ($($_.Exception.Message))"
    }
}

$durations = @{
    quick   = "~2-5 min (no Ollama / GPU)"
    smoke   = "~3-7 min (Ollama smoke tests)"
    full    = "~12 min (all tests; heretic skipped unless OLLAMA_MODEL contains 'heretic')"
    heretic = "~2-5 min (stock Ollama :11434 + aquila_heretic)"
}

Write-Host ""
Write-Host "=== Aquila health check: $Tier ===" -ForegroundColor Cyan
Write-Host "Expected duration: $($durations[$Tier])"
Write-Host ""

switch ($Tier) {
    "quick" {
        Invoke-Pytest @("tests/", "-m", "not live", "-q", "--tb=short")
    }
    "smoke" {
        Invoke-Pytest @("tests/", "-m", "not live", "-q", "--tb=short")
        Invoke-Pytest @(
            "tests/test_live_ollama.py",
            "tests/test_live_context_smoke.py",
            "-m", "live",
            "-v", "--tb=short"
        )
    }
    "full" {
        Invoke-Pytest @("tests/", "-v", "--tb=short")
    }
    "heretic" {
        if (-not $env:OLLAMA_BASE_URL) { $env:OLLAMA_BASE_URL = "http://127.0.0.1:11434" }
        if (-not $env:OLLAMA_MODEL) { $env:OLLAMA_MODEL = "aquila_heretic" }
        Write-Host "OLLAMA_BASE_URL=$($env:OLLAMA_BASE_URL)"
        Write-Host "OLLAMA_MODEL=$($env:OLLAMA_MODEL)"
        Invoke-Pytest @("tests/", "-m", "heretic", "-v", "--tb=short")
    }
}

if ($Eject -and $Tier -in @("smoke", "full", "heretic")) {
    Eject-OllamaModels
}

Write-Host ""
Write-Host "=== $Tier health check passed ===" -ForegroundColor Green
