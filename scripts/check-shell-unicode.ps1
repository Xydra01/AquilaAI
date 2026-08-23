#Requires -Version 5.1
<#
.SYNOPSIS
  Scan Aquila for Unicode that breaks Windows PowerShell 5.1 / cmd.

.EXAMPLE
  .\scripts\check-shell-unicode.ps1
  .\scripts\check-shell-unicode.ps1 -Fix
  .\scripts\check-shell-unicode.ps1 -FixDryRun
#>
param(
    [switch]$All,
    [switch]$Fix,
    [switch]$FixDryRun,
    [switch]$Quiet,
    [switch]$FullTree
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

$argsList = @((Join-Path $Root "scripts\check-shell-unicode.py"))
if ($All) { $argsList += "--all" }
if ($Fix) { $argsList += "--fix" }
if ($FixDryRun) { $argsList += "--fix-dry-run" }
if ($Quiet) { $argsList += "--quiet" }
if ($FullTree) { $argsList += "--full-tree" }

& $Python @argsList
exit $LASTEXITCODE
