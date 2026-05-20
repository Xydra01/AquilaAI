# Create all Aquila TurboQuant Modelfiles against the server on OLLAMA_HOST (default 11435).
# Usage (repo root):
#   .\scripts\ollama-serve-turboquant-port.ps1   # separate window
#   .\scripts\ollama-create-tq-models.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Ollama = Join-Path $RepoRoot "tools\ollama-turboquant\ollama.exe"
if (-not (Test-Path $Ollama)) {
    Write-Host "Missing $Ollama — run .\scripts\install-ollama-turboquant-pr.ps1 first." -ForegroundColor Red
    exit 1
}

if (-not $env:OLLAMA_HOST) {
    $env:OLLAMA_HOST = "http://127.0.0.1:11435"
}
Write-Host "OLLAMA_HOST = $env:OLLAMA_HOST"
Write-Host ""

Push-Location $RepoRoot
try {
    foreach ($pair in @(
            @("aquila-tq-32k", "Modelfile.tq-32k"),
            @("aquila-tq-64k", "Modelfile.tq-64k"),
            @("aquila-tq-96k", "Modelfile.tq-96k")
        )) {
        $name, $file = $pair
        $path = Join-Path $RepoRoot $file
        if (-not (Test-Path $path)) {
            Write-Host "Skip $name — missing $file" -ForegroundColor Yellow
            continue
        }
        Write-Host "Creating $name from $file ..."
        & $Ollama create $name -f $path
        if ($LASTEXITCODE -ne 0) { throw "ollama create $name failed" }
    }
    Write-Host ""
    Write-Host "Done. Suggested .env:"
    Write-Host "  OLLAMA_BASE_URL=$($env:OLLAMA_HOST)"
    Write-Host "  OLLAMA_MODEL=aquila-tq-32k   # light tasks"
    Write-Host "  OLLAMA_MODEL=aquila-tq-64k   # default extended"
    Write-Host "  OLLAMA_MODEL=aquila-tq-96k   # max context"
} finally {
    Pop-Location
}
