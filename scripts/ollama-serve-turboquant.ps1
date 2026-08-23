# RETIRED: this PowerShell script now forwards to the cross-platform bash version.
# Prefer running scripts/ollama-serve-turboquant.sh directly (Git Bash on Windows).
# This shim is transitional and will be removed in a future release.
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Sh = Join-Path $ScriptDir "ollama-serve-turboquant.sh"
$Bash = Get-Command bash -ErrorAction SilentlyContinue
if (-not $Bash) {
    Write-Error "Git Bash 'bash' not found on PATH. Install Git for Windows: https://git-scm.com/download/win"
    exit 1
}
& $Bash.Source $Sh @args
exit $LASTEXITCODE
