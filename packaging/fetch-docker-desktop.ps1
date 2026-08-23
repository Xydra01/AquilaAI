#Requires -Version 5.1
<#
.SYNOPSIS
  Download Docker Desktop Installer for optional bundling in Aquila setup.
#>
param(
    [string]$DestDir = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $DestDir) {
    $DestDir = Join-Path $Root "packaging\prerequisites"
}
New-Item -ItemType Directory -Force -Path $DestDir | Out-Null

$OutFile = Join-Path $DestDir "Docker Desktop Installer.exe"
if (Test-Path -LiteralPath $OutFile) {
    Write-Host "Docker Desktop installer already present: $OutFile"
    exit 0
}

$Url = "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"
Write-Host "Downloading Docker Desktop Installer..."
Invoke-WebRequest -Uri $Url -OutFile $OutFile
Write-Host "OK: $OutFile"
