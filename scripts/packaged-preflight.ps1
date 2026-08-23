#Requires -Version 5.1
<#
.SYNOPSIS
  Fast packaged-install preflight (no PyInstaller). Catch wizard/Docker bugs before a long build.

.EXAMPLE
  .\scripts\packaged-preflight.ps1
  .\scripts\packaged-preflight.ps1 -Quick
#>
param(
    [switch]$Quick
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$VenvPython = Join-Path $Root "ai-agent-env\Scripts\python.exe"
if (Test-Path -LiteralPath $VenvPython) {
    $Python = $VenvPython
} else {
    $Python = "python"
}

$preflightArgs = @((Join-Path $Root "scripts\packaged-preflight.py"))
if ($Quick) {
    $preflightArgs += "--quick"
}

Write-Host "Running packaged preflight with $Python ..."
& $Python @preflightArgs
exit $LASTEXITCODE
