#Requires -Version 5.1
<#
.SYNOPSIS
  Fetch portable stock Ollama into a packaging staging directory (Windows).

  Uses a persistent zip cache under packaging/cache/ollama so rebuilds do not
  re-download ~1.5 GB. Prefers curl.exe (much faster than Invoke-WebRequest).

.EXAMPLE
  .\packaging\fetch-ollama.ps1 -DestDir dist\Aquila\runtime\ollama
  .\packaging\fetch-ollama.ps1 -DestDir dist\Aquila\runtime\ollama -Version v0.31.1 -Arch arm64
  .\packaging\fetch-ollama.ps1 -DestDir dist\Aquila\runtime\ollama -ForceRefresh
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$DestDir,
    [string]$Version = "v0.31.1",
    [ValidateSet("amd64", "arm64")]
    [string]$Arch = "amd64",
    [switch]$ForceRefresh
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$asset = if ($Arch -eq "arm64") { "ollama-windows-arm64.zip" } else { "ollama-windows-amd64.zip" }
$url = "https://github.com/ollama/ollama/releases/download/$Version/$asset"
# Portable zip is ~1.4+ GB; reject tiny/corrupt cache entries.
$MinZipBytes = 500MB

$CacheDir = Join-Path $RepoRoot "packaging\cache\ollama\$Version"
New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
$CachedZip = Join-Path $CacheDir $asset
$StampName = ".aquila-ollama-stamp"
$ExpectedStamp = "$Version|$Arch|$asset"

function Test-OllamaDestReady {
    param([string]$Dir, [string]$Stamp)
    $exe = Get-ChildItem -Path $Dir -Recurse -Filter "ollama.exe" -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $exe) { return $false }
    $stampPath = Join-Path $Dir $StampName
    if (-not (Test-Path -LiteralPath $stampPath)) { return $false }
    $got = (Get-Content -LiteralPath $stampPath -Raw -ErrorAction SilentlyContinue).Trim()
    return ($got -eq $Stamp)
}

function Get-CurlExe {
    $cmd = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        "$env:SystemRoot\System32\curl.exe",
        "$env:SystemRoot\SysWOW64\curl.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path -LiteralPath $p) { return $p }
    }
    return $null
}

function Download-File {
    param([string]$Uri, [string]$OutFile)
    $curl = Get-CurlExe
    if ($curl) {
        Write-Host "Downloading with curl.exe (faster than Invoke-WebRequest)..."
        Write-Host "  $Uri"
        Write-Host "  -> $OutFile"
        # -L follow redirects, -f fail on HTTP errors, --retry for flaky GitHub
        & $curl -L --fail --retry 3 --retry-delay 2 --progress-bar -o $OutFile $Uri
        if ($LASTEXITCODE -ne 0) {
            throw "curl.exe download failed (exit $LASTEXITCODE)"
        }
        return
    }
    Write-Warning "curl.exe not found; falling back to Invoke-WebRequest (slower)."
    Invoke-WebRequest -Uri $Uri -OutFile $OutFile
}

# Fast path: dest already extracted for this version/arch (e.g. rebuild after abort mid-Inno).
if (-not $ForceRefresh -and (Test-OllamaDestReady -Dir $DestDir -Stamp $ExpectedStamp)) {
    $exe = Get-ChildItem -Path $DestDir -Recurse -Filter "ollama.exe" |
        Select-Object -First 1
    Write-Host "Ollama $Version ($Arch) already staged at $DestDir - skipping download/extract."
    Write-Host "OK: $($exe.FullName)"
    try { & $exe.FullName --version 2>&1 | ForEach-Object { Write-Host $_ } } catch {}
    return
}

$haveCache = $false
if (-not $ForceRefresh -and (Test-Path -LiteralPath $CachedZip)) {
    $len = (Get-Item -LiteralPath $CachedZip).Length
    if ($len -ge $MinZipBytes) {
        $haveCache = $true
        Write-Host ("Using cached Ollama zip ({0:N1} GB): {1}" -f ($len / 1GB), $CachedZip)
    } else {
        Write-Warning "Cached zip too small ($len bytes); re-downloading."
        Remove-Item -LiteralPath $CachedZip -Force -ErrorAction SilentlyContinue
    }
}

if (-not $haveCache) {
    Write-Host "Fetching stock Ollama $Version (windows/$Arch)"
    Write-Host "Cache miss - downloading once to $CachedZip (reuse on later builds)."
    $partial = "$CachedZip.partial"
    if (Test-Path -LiteralPath $partial) {
        Remove-Item -LiteralPath $partial -Force
    }
    Download-File -Uri $url -OutFile $partial
    $len = (Get-Item -LiteralPath $partial).Length
    if ($len -lt $MinZipBytes) {
        Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
        throw "Downloaded zip too small ($len bytes); expected >= $MinZipBytes"
    }
    Move-Item -LiteralPath $partial -Destination $CachedZip -Force
    Write-Host ("Cached ({0:N1} GB): {1}" -f ($len / 1GB), $CachedZip)
}

if (Test-Path -LiteralPath $DestDir) {
    Get-ChildItem -LiteralPath $DestDir -Force | Remove-Item -Recurse -Force
} else {
    New-Item -ItemType Directory -Force -Path $DestDir | Out-Null
}

Write-Host "Extracting $CachedZip -> $DestDir ..."
$extractStart = Get-Date
Expand-Archive -LiteralPath $CachedZip -DestinationPath $DestDir -Force
Write-Host ("Extract done in {0:N0}s" -f ((Get-Date) - $extractStart).TotalSeconds)

Set-Content -LiteralPath (Join-Path $DestDir $StampName) -Value $ExpectedStamp -Encoding ASCII

$ollama = Get-ChildItem -Path $DestDir -Recurse -Filter "ollama.exe" -ErrorAction SilentlyContinue |
    Select-Object -First 1
if (-not $ollama) {
    throw "ollama.exe not found under $DestDir after extract"
}

Write-Host "OK: $($ollama.FullName)"
try {
    & $ollama.FullName --version 2>&1 | ForEach-Object { Write-Host $_ }
} catch {
    Write-Host "Ollama binary present (version check skipped)."
}
