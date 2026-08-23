# start-dual-servers.ps1 - Starts both stock and TurboQuant Ollama servers in the background

$Dir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$LogDir = Join-Path (Split-Path $Dir -Parent) "Agent-Logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

Write-Host "Starting Stock Ollama Server (Port 11434)..." -ForegroundColor Cyan
Start-Process -NoNewWindow -FilePath "powershell.exe" -ArgumentList "-ExecutionPolicy Bypass -File `"$Dir\ollama-serve-stock.ps1`"" -RedirectStandardOutput "$LogDir\ollama-stock.log" -RedirectStandardError "$LogDir\ollama-stock.log"

Write-Host "Starting TurboQuant Ollama Server (Port 11435)..." -ForegroundColor Cyan
Start-Process -NoNewWindow -FilePath "powershell.exe" -ArgumentList "-ExecutionPolicy Bypass -File `"$Dir\ollama-serve-turboquant-port.ps1`"" -RedirectStandardOutput "$LogDir\ollama-turboquant.log" -RedirectStandardError "$LogDir\ollama-turboquant.log"

Write-Host "Both servers are now running in the background!" -ForegroundColor Green
Write-Host "Logs are being written to Agent-Logs\"
