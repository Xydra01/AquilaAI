# Start Aquila MCP host (stdio) for Cursor / MCP clients.
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
if (-not (Test-Path "$RepoRoot\agent\mcp_host.py")) {
    $RepoRoot = Split-Path $PSScriptRoot -Parent
}
$AgentDir = Join-Path $RepoRoot "agent"
$Python = Join-Path $RepoRoot "ai-agent-env\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }
$env:AQUILA_DATA_ROOT = if ($env:AQUILA_DATA_ROOT) { $env:AQUILA_DATA_ROOT } else { $RepoRoot }
Set-Location $AgentDir
& $Python mcp_host.py @args
