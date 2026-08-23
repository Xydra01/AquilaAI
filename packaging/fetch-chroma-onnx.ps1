#Requires -Version 5.1
<#
.SYNOPSIS
  Fetch Chroma all-MiniLM-L6-v2 ONNX embedding assets into a packaging staging dir.

  Same model Chroma downloads at runtime (~90 MB extracted). Cached under
  packaging/cache/chroma-onnx so rebuilds do not re-download. Prefer seeding
  from the local Chroma cache when present.

.EXAMPLE
  .\packaging\fetch-chroma-onnx.ps1 -DestDir dist\Aquila\runtime\embeddings
  .\packaging\fetch-chroma-onnx.ps1 -DestDir dist\Aquila\runtime\embeddings -ForceRefresh
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$DestDir,
    [switch]$ForceRefresh
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ModelName = "all-MiniLM-L6-v2"
$Url = "https://chroma-onnx-models.s3.amazonaws.com/all-MiniLM-L6-v2/onnx.tar.gz"
$ExpectedSha256 = "913d7300ceae3b2dbc2c50d1de4baacab4be7b9380491c27fab7418616a16ec3"
$MinTarBytes = 50MB

$CacheDir = Join-Path $RepoRoot "packaging\cache\chroma-onnx\$ModelName"
New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
$CachedTar = Join-Path $CacheDir "onnx.tar.gz"
$StampName = ".aquila-chroma-onnx-stamp"
$ExpectedStamp = "$ModelName|$ExpectedSha256"

function Get-FileSha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Test-OnnxDestReady {
    param([string]$Dir)
    $model = Join-Path $Dir "$ModelName\onnx\model.onnx"
    $tok = Join-Path $Dir "$ModelName\onnx\tokenizer.json"
    $stampPath = Join-Path $Dir $StampName
    if (-not (Test-Path -LiteralPath $model)) { return $false }
    if (-not (Test-Path -LiteralPath $tok)) { return $false }
    if (-not (Test-Path -LiteralPath $stampPath)) { return $false }
    $got = (Get-Content -LiteralPath $stampPath -Raw -ErrorAction SilentlyContinue).Trim()
    return ($got -eq $ExpectedStamp)
}

function Get-CurlExe {
    $cmd = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in @(
        "$env:SystemRoot\System32\curl.exe",
        "$env:SystemRoot\SysWOW64\curl.exe"
    )) {
        if (Test-Path -LiteralPath $p) { return $p }
    }
    return $null
}

function Download-File {
    param([string]$Uri, [string]$OutFile)
    $curl = Get-CurlExe
    if ($curl) {
        Write-Host "Downloading embedding model with curl.exe..."
        Write-Host "  $Uri"
        Write-Host "  -> $OutFile"
        & $curl -L --fail --retry 3 --retry-delay 2 --progress-bar -o $OutFile $Uri
        if ($LASTEXITCODE -ne 0) {
            throw "curl.exe download failed (exit $LASTEXITCODE)"
        }
        return
    }
    Write-Warning "curl.exe not found; falling back to Invoke-WebRequest."
    Invoke-WebRequest -Uri $Uri -OutFile $OutFile
}

function Ensure-CachedTar {
    if (-not $ForceRefresh -and (Test-Path -LiteralPath $CachedTar)) {
        $len = (Get-Item -LiteralPath $CachedTar).Length
        if ($len -ge $MinTarBytes) {
            $sha = Get-FileSha256 $CachedTar
            if ($sha -eq $ExpectedSha256) {
                Write-Host "Using cached onnx.tar.gz ($([math]::Round($len/1MB)) MB)"
                return
            }
            Write-Warning "Cached onnx.tar.gz SHA mismatch - re-downloading."
        }
    }

    # Prefer seeding from the developer's existing Chroma cache (no network).
    $userTar = Join-Path $env:USERPROFILE ".cache\chroma\onnx_models\$ModelName\onnx.tar.gz"
    if (-not $ForceRefresh -and (Test-Path -LiteralPath $userTar)) {
        $sha = Get-FileSha256 $userTar
        if ($sha -eq $ExpectedSha256) {
            Write-Host "Seeding cache from local Chroma download: $userTar"
            Copy-Item -LiteralPath $userTar -Destination $CachedTar -Force
            return
        }
    }

    Download-File -Uri $Url -OutFile $CachedTar
    $sha = Get-FileSha256 $CachedTar
    if ($sha -ne $ExpectedSha256) {
        Remove-Item -LiteralPath $CachedTar -Force -ErrorAction SilentlyContinue
        throw "Downloaded onnx.tar.gz SHA256 mismatch (got $sha, expected $ExpectedSha256)"
    }
}

function Expand-OnnxToDest {
    param([string]$Dir)
    $modelRoot = Join-Path $Dir $ModelName
    if (Test-Path -LiteralPath $modelRoot) {
        Remove-Item -LiteralPath $modelRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $modelRoot | Out-Null

    # Prefer already-extracted user cache (faster than re-extracting 83 MB tar).
    $userOnnx = Join-Path $env:USERPROFILE ".cache\chroma\onnx_models\$ModelName\onnx"
    $userModel = Join-Path $userOnnx "model.onnx"
    if (-not $ForceRefresh -and (Test-Path -LiteralPath $userModel)) {
        Write-Host "Copying extracted ONNX assets from local Chroma cache..."
        Copy-Item -LiteralPath $userOnnx -Destination (Join-Path $modelRoot "onnx") -Recurse -Force
    } else {
        Write-Host "Extracting onnx.tar.gz..."
        tar -xzf $CachedTar -C $modelRoot
        if (-not (Test-Path -LiteralPath (Join-Path $modelRoot "onnx\model.onnx"))) {
            throw "Extract did not produce $ModelName\onnx\model.onnx"
        }
    }

    Set-Content -LiteralPath (Join-Path $Dir $StampName) -Value $ExpectedStamp -Encoding ascii
}

if (-not $ForceRefresh -and (Test-OnnxDestReady -Dir $DestDir)) {
    Write-Host "Embedding assets already staged at $DestDir - skip."
    exit 0
}

New-Item -ItemType Directory -Force -Path $DestDir | Out-Null
Ensure-CachedTar
Expand-OnnxToDest -Dir $DestDir

$model = Join-Path $DestDir "$ModelName\onnx\model.onnx"
if (-not (Test-Path -LiteralPath $model)) {
    throw "Embedding model missing after staging: $model"
}
$sizeMb = [math]::Round((Get-Item -LiteralPath $model).Length / 1MB)
Write-Host "Bundled embedding ready: $model ($sizeMb MB)"
