#Requires -Version 5.1
<#
.SYNOPSIS
  Build Aquila Windows installer (x64 or arm64).

.EXAMPLE
  .\packaging\build-windows.ps1
  .\packaging\build-windows.ps1 -Arch arm64
  .\packaging\build-windows.ps1 -BundleDocker
#>
param(
    [switch]$BundleDocker,
    [switch]$SkipPreflight,
    [string]$Version = "3.5.0",
    [string]$OllamaVersion = "v0.31.1",
    [ValidateSet("amd64", "arm64")]
    [string]$Arch = "amd64"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

# --- Build ETA helpers (ASCII-only; PS 5.1 safe) ---
$script:TimingsPath = Join-Path $Root "packaging\.build-timings-windows.json"
$script:DefaultEstimatesSec = @{
    preflight   = 30
    pip         = 120
    pyinstaller = 300
    ollama      = 45   # cached zip extract; first cold download ~15m (see fetch-ollama.ps1)
    embeddings  = 30   # MiniLM ONNX (~90 MB); cached under packaging/cache/chroma-onnx
    docker      = 240
    inno        = 180
}
$script:StepActualsSec = @{}
$script:StepStartedAt = $null
$script:CurrentStep = $null
$script:BuildStartedAt = Get-Date
$script:Plan = @()

function Format-Duration([double]$Seconds) {
    if ($Seconds -lt 0) { $Seconds = 0 }
    $s = [int][math]::Round($Seconds)
    if ($s -lt 60) { return "${s}s" }
    $m = [int][math]::Floor($s / 60)
    $r = $s % 60
    if ($m -lt 60) { return ("{0}m {1:D2}s" -f $m, $r) }
    $h = [int][math]::Floor($m / 60)
    $m = $m % 60
    return ("{0}h {1}m {2:D2}s" -f $h, $m, $r)
}

function Get-SavedEstimates {
    $est = @{}
    foreach ($k in $script:DefaultEstimatesSec.Keys) {
        $est[$k] = [double]$script:DefaultEstimatesSec[$k]
    }
    if (Test-Path -LiteralPath $script:TimingsPath) {
        try {
            $json = Get-Content -LiteralPath $script:TimingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($prop in $json.PSObject.Properties) {
                if ($null -ne $prop.Value -and $prop.Name -ne "updated") {
                    $est[$prop.Name] = [double]$prop.Value
                }
            }
        } catch {
            Write-Warning "Could not read $($script:TimingsPath); using default ETA estimates."
        }
    }
    return $est
}

function Save-BuildTimings {
    $out = [ordered]@{ updated = (Get-Date).ToString("o") }
    $est = Get-SavedEstimates
    foreach ($k in $est.Keys) {
        if ($script:StepActualsSec.ContainsKey($k)) {
            # EMA: blend last run with prior estimate so one slow network blip does not dominate.
            $prev = [double]$est[$k]
            $cur = [double]$script:StepActualsSec[$k]
            $out[$k] = [math]::Round((0.4 * $prev) + (0.6 * $cur), 1)
        } else {
            $out[$k] = [math]::Round([double]$est[$k], 1)
        }
    }
    ($out | ConvertTo-Json) | Set-Content -LiteralPath $script:TimingsPath -Encoding UTF8
}

function Get-RemainingEstimateSec([string[]]$RemainingIds, $Estimates) {
    $sum = 0.0
    foreach ($id in $RemainingIds) {
        if ($Estimates.ContainsKey($id)) { $sum += [double]$Estimates[$id] }
    }
    return $sum
}

function Write-BuildBanner($Estimates, [string[]]$StepIds, [hashtable]$StepLabels) {
    $total = Get-RemainingEstimateSec $StepIds $Estimates
    Write-Host ""
    Write-Host "=== Aquila Windows build ==="
    Write-Host ("Plan (~{0} total ETA from prior runs / defaults):" -f (Format-Duration $total))
    $i = 1
    foreach ($id in $StepIds) {
        $label = $StepLabels[$id]
        $sec = [double]$Estimates[$id]
        Write-Host ("  {0}. {1}  (~{2})" -f $i, $label, (Format-Duration $sec))
        $i++
    }
    Write-Host ""
}

function Start-BuildStep([string]$Id, [string]$Label, $Estimates, [string[]]$AllRemainingIncludingCurrent) {
    $script:CurrentStep = $Id
    $script:StepStartedAt = Get-Date
    $remain = Get-RemainingEstimateSec $AllRemainingIncludingCurrent $Estimates
    $elapsed = ((Get-Date) - $script:BuildStartedAt).TotalSeconds
    Write-Host ""
    Write-Host (">>> [{0}] {1}" -f $Id.ToUpper(), $Label)
    Write-Host ("    Elapsed {0} | Step ETA ~{1} | Build ETA remaining ~{2}" -f `
        (Format-Duration $elapsed), `
        (Format-Duration ([double]$Estimates[$Id])), `
        (Format-Duration $remain))
}

function Complete-BuildStep([string]$Id) {
    $dt = ((Get-Date) - $script:StepStartedAt).TotalSeconds
    $script:StepActualsSec[$Id] = $dt
    Write-Host ("<<< [{0}] done in {1}" -f $Id.ToUpper(), (Format-Duration $dt))
    $script:CurrentStep = $null
}

$Estimates = Get-SavedEstimates
$StepLabels = @{
    preflight   = "Packaged preflight"
    pip         = "pip install (core + packaging)"
    pyinstaller = "PyInstaller (Aquila onedir)"
    ollama      = "Fetch / bundle Ollama"
    embeddings  = "Fetch / bundle MiniLM ONNX embeddings"
    docker      = "Fetch Docker Desktop installer"
    inno        = "Inno Setup compiler"
}

$PlanIds = @()
if (-not $SkipPreflight) { $PlanIds += "preflight" }
$PlanIds += @("pip", "pyinstaller", "ollama", "embeddings")
if ($BundleDocker) { $PlanIds += "docker" }
# inno may be skipped if ISCC missing; still list it and adjust later
$PlanIds += "inno"

Write-BuildBanner $Estimates $PlanIds $StepLabels
$remaining = [System.Collections.Generic.List[string]]::new()
foreach ($id in $PlanIds) { [void]$remaining.Add($id) }

function Pop-Remaining([string]$Id) {
    [void]$remaining.Remove($Id)
}

# --- Build steps ---

if (-not $SkipPreflight) {
    Start-BuildStep "preflight" $StepLabels.preflight $Estimates @($remaining.ToArray())
    $preflight = Join-Path $Root "scripts\packaged-preflight.ps1"
    & $preflight
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Packaged preflight failed - fix issues above before compiling. Re-run with -SkipPreflight only if you intentionally want to build anyway."
    }
    Complete-BuildStep "preflight"
    Pop-Remaining "preflight"
}

$Venv = Join-Path $Root "ai-agent-env"
$Python = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $Python)) {
    python -m venv $Venv
    $Python = Join-Path $Venv "Scripts\python.exe"
}

# uv-created venvs may not ship pip.exe; ensure pip module is available.
& $Python -m pip --version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Bootstrapping pip in ai-agent-env..."
    & $Python -m ensurepip --upgrade
}

Start-BuildStep "pip" $StepLabels.pip $Estimates @($remaining.ToArray())
& $Python -m pip install -r requirements-core.txt -r requirements-packaging.txt
# PyInstaller breaks if the obsolete backport pathlib package is installed (common in uv venvs).
$prevErrorPref = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
& $Python -m pip uninstall -y pathlib *> $null
$ErrorActionPreference = $prevErrorPref
Complete-BuildStep "pip"
Pop-Remaining "pip"

Start-BuildStep "pyinstaller" $StepLabels.pyinstaller $Estimates @($remaining.ToArray())
& $Python -m PyInstaller -y packaging\aquila.spec
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller failed (exit $LASTEXITCODE). Fix errors above before creating the installer."
}
Complete-BuildStep "pyinstaller"
Pop-Remaining "pyinstaller"

$Dist = Join-Path $Root "dist\Aquila"
$AquilaExe = Join-Path $Dist "Aquila.exe"
if (-not (Test-Path -LiteralPath $AquilaExe)) {
    Write-Error "PyInstaller did not produce dist\Aquila\Aquila.exe - aborting installer step."
}
Write-Host "PyInstaller OK: $AquilaExe"

Start-BuildStep "ollama" $StepLabels.ollama $Estimates @($remaining.ToArray())
$OllamaDest = Join-Path $Dist "runtime\ollama"
$fetchOllamaPs1 = Join-Path $Root "packaging\fetch-ollama.ps1"
try {
    & $fetchOllamaPs1 -DestDir $OllamaDest -Version $OllamaVersion -Arch $Arch
} catch {
    Write-Error "fetch-ollama.ps1 failed - installer cannot ship without bundled Ollama. $_"
}
Complete-BuildStep "ollama"
Pop-Remaining "ollama"

$OllamaExe = Get-ChildItem -Path $OllamaDest -Recurse -Filter "ollama.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $OllamaExe) {
    Write-Error "Ollama binary not found under $OllamaDest after fetch - aborting."
}
Write-Host "Ollama bundled: $($OllamaExe.FullName)"

Start-BuildStep "embeddings" $StepLabels.embeddings $Estimates @($remaining.ToArray())
$EmbDest = Join-Path $Dist "runtime\embeddings"
$fetchEmbPs1 = Join-Path $Root "packaging\fetch-chroma-onnx.ps1"
try {
    & $fetchEmbPs1 -DestDir $EmbDest
} catch {
    Write-Error "fetch-chroma-onnx.ps1 failed - installer needs offline embeddings. $_"
}
Complete-BuildStep "embeddings"
Pop-Remaining "embeddings"

$EmbModel = Join-Path $EmbDest "all-MiniLM-L6-v2\onnx\model.onnx"
if (-not (Test-Path -LiteralPath $EmbModel)) {
    Write-Error "Embedding model not found under $EmbDest after fetch - aborting."
}
Write-Host "Embeddings bundled: $EmbModel"

$DockerInstaller = Join-Path $Root "packaging\prerequisites\Docker Desktop Installer.exe"
if ($BundleDocker) {
    Start-BuildStep "docker" $StepLabels.docker $Estimates @($remaining.ToArray())
    & (Join-Path $Root "packaging\fetch-docker-desktop.ps1")
    Complete-BuildStep "docker"
    Pop-Remaining "docker"
} else {
    Pop-Remaining "docker"
}

function Resolve-InnoSetupCompiler {
    $cmd = Get-Command iscc -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "F:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path -LiteralPath $path)) { return $path }
    }
    return $null
}

$Iss = Join-Path $Root "packaging\aquila.iss"
$Iscc = Resolve-InnoSetupCompiler
if ($Iscc) {
    Start-BuildStep "inno" $StepLabels.inno $Estimates @($remaining.ToArray())
    $archSuffix = if ($Arch -eq "arm64") { "-arm64" } else { "" }
    $OutDir = Join-Path $Root "dist"
    $isccArgs = @(
        "/DAppVersion=$Version",
        "/DArchSuffix=$archSuffix",
        "/DSourceDir=$Dist",
        "/O$OutDir"
    )
    if (Test-Path -LiteralPath $DockerInstaller) {
        $isccArgs += "/DDockerInstallerPath=$DockerInstaller"
        Write-Host "Docker Desktop installer will be offered as an optional setup task."
    }
    $isccArgs += $Iss
    & $Iscc @isccArgs
    Complete-BuildStep "inno"
    Pop-Remaining "inno"
    Write-Host "Installer: $OutDir\Aquila-$Version$archSuffix-setup.exe"
} else {
    Pop-Remaining "inno"
    Write-Warning "Inno Setup not found (iscc / ISCC.exe)."
    Write-Warning "Install Inno Setup 6 and add its folder to PATH, then re-run this script."
    Write-Warning "Onedir build is ready at: dist\Aquila"
}

Save-BuildTimings
$totalElapsed = ((Get-Date) - $script:BuildStartedAt).TotalSeconds
Write-Host ""
Write-Host ("=== Build finished in {0} ===" -f (Format-Duration $totalElapsed))
Write-Host ("Timing history updated: {0}" -f $script:TimingsPath)
