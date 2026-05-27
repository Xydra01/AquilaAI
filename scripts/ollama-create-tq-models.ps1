# Create all Aquila TurboQuant Modelfiles against the server on OLLAMA_HOST (default 11435).
# Usage (repo root):
#   .\scripts\ollama-serve-turboquant-port.ps1   # separate window — must be running first
#   .\scripts\ollama-create-tq-models.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$OllamaDir = Join-Path $RepoRoot "tools\ollama-turboquant"
$Ollama = Join-Path $OllamaDir "ollama.exe"
if (-not (Test-Path $Ollama)) {
    Write-Host "Missing $Ollama - run .\scripts\install-ollama-turboquant-pr.ps1 first." -ForegroundColor Red
    exit 1
}

if (-not $env:OLLAMA_HOST) {
    $env:OLLAMA_HOST = "http://127.0.0.1:11435"
}
$hostUrl = $env:OLLAMA_HOST.Trim().TrimEnd("/")
if ($hostUrl -notmatch "^https?://") {
    $hostUrl = "http://$hostUrl"
}
$apiBase = $hostUrl

Write-Host "OLLAMA_HOST = $hostUrl"
Write-Host ""

function Test-OllamaServer {
    param([string]$Base)
    try {
        $null = Invoke-RestMethod -Uri "$Base/api/tags" -Method Get -TimeoutSec 5
        return $true
    } catch {
        return $false
    }
}

function Invoke-OllamaCreateApi {
    param(
        [string]$Base,
        [string]$Name,
        [string]$ModelfilePath
    )
    $modelfile = Get-Content -Path $ModelfilePath -Raw -Encoding UTF8
    $body = @{ name = $Name; modelfile = $modelfile } | ConvertTo-Json -Compress
    $resp = Invoke-WebRequest -Uri "$Base/api/create" -Method Post -Body $body `
        -ContentType "application/json; charset=utf-8" -UseBasicParsing -TimeoutSec 7200
    $lines = ($resp.Content -split "`n") | Where-Object { $_.Trim() -ne "" }
    foreach ($line in $lines) {
        try {
            $obj = $line | ConvertFrom-Json
            if ($obj.error) {
                throw $obj.error
            }
            if ($obj.status) {
                Write-Host "  $($obj.status)"
            }
        } catch {
            if ($_.Exception.Message -notmatch "Invalid JSON") {
                throw
            }
        }
    }
}

if (-not (Test-OllamaServer -Base $apiBase)) {
    Write-Host "TurboQuant Ollama is not reachable at $apiBase" -ForegroundColor Red
    Write-Host ""
    Write-Host "Start the server in another PowerShell window, then re-run this script:"
    Write-Host "  .\scripts\ollama-serve-turboquant-port.ps1"
    Write-Host ""
    Write-Host "The 'cmd.exe' error from ollama create usually means the CLI tried to auto-start"
    Write-Host "the desktop app because nothing was listening on port 11435."
    exit 1
}

$models = @(
    @{ Name = "aquila-tq-32k"; File = "Modelfile.tq-32k" },
    @{ Name = "aquila-tq-64k"; File = "Modelfile.tq-64k" },
    @{ Name = "aquila-tq-96k"; File = "Modelfile.tq-96k" }
)

Push-Location $RepoRoot
try {
    foreach ($entry in $models) {
        $name = $entry.Name
        $file = $entry.File
        $path = Join-Path $RepoRoot $file
        if (-not (Test-Path $path)) {
            Write-Host "Skip $name - missing $file" -ForegroundColor Yellow
            continue
        }
        Write-Host "Creating $name from $file ..."
        try {
            Invoke-OllamaCreateApi -Base $apiBase -Name $name -ModelfilePath $path
        } catch {
            Write-Host "API create failed, trying CLI ..." -ForegroundColor Yellow
            $env:PATH = "$OllamaDir;$env:PATH"
            $env:OLLAMA_HOST = $hostUrl
            & $Ollama create $name -f $path
            if ($LASTEXITCODE -ne 0) {
                throw "ollama create $name failed: $_"
            }
        }
        Write-Host "  [ok] $name"
    }
    Write-Host ""
    Write-Host "Done. Suggested .env:"
    Write-Host "  OLLAMA_BASE_URL=$hostUrl"
    Write-Host "  OLLAMA_MODEL=aquila-tq-32k   # light tasks"
    Write-Host "  OLLAMA_MODEL=aquila-tq-64k   # default extended"
    Write-Host "  OLLAMA_MODEL=aquila-tq-96k   # max context"
}
finally {
    Pop-Location
}
