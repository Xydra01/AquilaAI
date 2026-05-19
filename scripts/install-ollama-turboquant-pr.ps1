# Build Ollama from PR #15505 (full TurboQuant: tq3, tq3k, ...).
# Uses Visual Studio + NVIDIA nvcc (required - LLVM/clang CUDA builds fail at runtime with PTX errors).
#
# Usage:
#   .\scripts\install-ollama-turboquant-pr.ps1
#   .\scripts\install-ollama-turboquant-pr.ps1 -RebuildCuda   # only redo ggml-cuda.dll

param(
    [switch]$RebuildCuda,
    [switch]$SkipGo
)

$ErrorActionPreference = "Stop"
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$SrcDir = Join-Path $RepoRoot "tools\ollama-pr15505-src"
$AltSrc = Join-Path $RepoRoot "tools\ollama-pr15505\ollama-refs-pull-15505-head"
if (-not (Test-Path $SrcDir) -and (Test-Path $AltSrc)) {
    $SrcDir = $AltSrc
}
$InstallDir = Join-Path $RepoRoot "tools\ollama-turboquant"
$PrZip = Join-Path $env:TEMP "ollama-pr15505.zip"
$PrUrl = "https://github.com/ollama/ollama/archive/refs/pull/15505/head.zip"

function Test-Command($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Enter-VisualStudioDevShell {
    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) {
        throw "vswhere not found - install VS 2022 Build Tools with Desktop C++ workload"
    }
    $vsPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (-not $vsPath) {
        throw "Visual Studio C++ tools not found"
    }
    $devShell = Join-Path $vsPath "Common7\Tools\Microsoft.VisualStudio.DevShell.dll"
    if (-not (Test-Path $devShell)) {
        throw "DevShell module missing at $devShell"
    }
    Import-Module $devShell
    Enter-VsDevShell -VsInstallPath $vsPath -SkipAutomaticLocation -DevCmdArguments "-arch=amd64"
    Write-Host "VS DevShell: $vsPath"
}

function Find-CudaRoot {
    foreach ($root in @(
            "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA",
            "F:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
        )) {
        $nvcc = Get-Item (Join-Path $root "v13*\bin\nvcc.exe") -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($nvcc) {
            return (Split-Path (Split-Path $nvcc.FullName -Parent) -Parent)
        }
    }
    return $null
}

Write-Host "TurboQuant PR build -> $InstallDir"
Write-Host ""

foreach ($cmd in @("go", "cmake")) {
    if (-not (Test-Command $cmd)) {
        Write-Host "Missing: $cmd" -ForegroundColor Red
        exit 1
    }
}

$CudaRoot = Find-CudaRoot
if (-not $CudaRoot) {
    Write-Host "CUDA Toolkit 13.x not found. Install: winget install Nvidia.CUDA" -ForegroundColor Yellow
    exit 1
}
Write-Host "CUDA Toolkit: $CudaRoot"

if (-not (Test-Path $SrcDir)) {
    Write-Host "Downloading PR #15505 source..."
    Invoke-WebRequest -Uri $PrUrl -OutFile $PrZip -UseBasicParsing
    Expand-Archive -Path $PrZip -DestinationPath (Split-Path $SrcDir -Parent) -Force
    $extracted = Get-ChildItem (Split-Path $SrcDir -Parent) -Directory | Where-Object { $_.Name -like "ollama-*pull-15505*" } | Select-Object -First 1
    if ($extracted) {
        Move-Item $extracted.FullName $SrcDir -Force
    }
    Remove-Item $PrZip -ErrorAction SilentlyContinue
}

Enter-VisualStudioDevShell

$env:VERSION = "pr15505-turboquant"
$env:PKG_VERSION = "0.0.0"
$env:CGO_ENABLED = "1"
$env:CUDAToolkit_ROOT = $CudaRoot
$jobs = [Environment]::ProcessorCount

Push-Location $SrcDir
try {
    $DistDir = Join-Path $SrcDir "dist\windows-amd64"
    New-Item -ItemType Directory -Path $DistDir -Force | Out-Null

    if ($RebuildCuda) {
        Remove-Item -Recurse -Force (Join-Path $SrcDir "build\cuda_v13") -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force (Join-Path $DistDir "lib\ollama\cuda_v13") -ErrorAction SilentlyContinue
    }

    $cpuOk = Test-Path (Join-Path $DistDir "lib\ollama\ggml-cpu-x64.dll")
    if (-not $cpuOk) {
        Write-Host "Building CPU backend (MSVC)..."
        & cmake -B build\cpu --preset CPU --install-prefix $DistDir
        if ($LASTEXITCODE -ne 0) { throw "cmake cpu configure failed" }
        & cmake --build build\cpu --target ggml-cpu --config Release --parallel $jobs
        if ($LASTEXITCODE -ne 0) { throw "cmake cpu build failed" }
        & cmake --install build\cpu --component CPU --strip
        if ($LASTEXITCODE -ne 0) { throw "cmake cpu install failed" }
    } else {
        Write-Host "CPU libs present, skipping"
    }

    $cudaOk = Test-Path (Join-Path $DistDir "lib\ollama\cuda_v13\ggml-cuda.dll")
    if (-not $cudaOk -or $RebuildCuda) {
        Write-Host "Building CUDA 13 backend (MSVC + nvcc) - this takes 15-45 min..."
        Remove-Item -Recurse -Force (Join-Path $SrcDir "build\cuda_v13") -ErrorAction SilentlyContinue
        & cmake -B build\cuda_v13 --preset "CUDA 13" -T "cuda=$CudaRoot" --install-prefix $DistDir
        if ($LASTEXITCODE -ne 0) { throw "cmake cuda13 configure failed" }
        & cmake --build build\cuda_v13 --target ggml-cuda --config Release --parallel $jobs
        if ($LASTEXITCODE -ne 0) { throw "cmake cuda13 build failed" }
        & cmake --install build\cuda_v13 --component CUDA --strip
        if ($LASTEXITCODE -ne 0) { throw "cmake cuda13 install failed" }
        $dll = Join-Path $DistDir "lib\ollama\cuda_v13\ggml-cuda.dll"
        if (-not (Test-Path $dll)) { throw "ggml-cuda.dll not installed to dist" }
        Write-Host "Installed: $dll"
    } else {
        Write-Host "CUDA libs present, skipping (use -RebuildCuda to force)"
    }

    if (-not $SkipGo) {
        Write-Host "Building ollama.exe (go + CGO in VS environment)..."
        & go build -trimpath -ldflags "-s -w -X=github.com/ollama/ollama/version.Version=$env:VERSION -X=github.com/ollama/ollama/server.mode=release" -o ollama.exe .
        if ($LASTEXITCODE -ne 0) { throw "go build failed" }
        Copy-Item ollama.exe (Join-Path $DistDir "ollama.exe") -Force
    }

    if (-not (Test-Path (Join-Path $DistDir "ollama.exe"))) {
        throw "dist\windows-amd64\ollama.exe missing"
    }
} finally {
    Pop-Location
}

$DistDir = Join-Path $SrcDir "dist\windows-amd64"
Get-Process ollama -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
if (Test-Path $InstallDir) { Remove-Item -Recurse -Force $InstallDir }
New-Item -ItemType Directory -Path $InstallDir | Out-Null
Copy-Item (Join-Path $DistDir "ollama.exe") $InstallDir
Copy-Item (Join-Path $DistDir "lib") (Join-Path $InstallDir "lib") -Recurse

$bin = [IO.File]::ReadAllBytes((Join-Path $InstallDir "ollama.exe"))
$text = [Text.Encoding]::ASCII.GetString($bin)
Write-Host ""
Write-Host "Deployed to $InstallDir"
Write-Host "tq3=$($text.Contains('tq3')) tq3k=$($text.Contains('tq3k'))"
& (Join-Path $InstallDir "ollama.exe") --version
Write-Host ""
Write-Host "Next: .\scripts\ollama-serve-turboquant-port.ps1"
Write-Host "Test:  curl http://127.0.0.1:11435/v1/chat/completions -H Content-Type:application/json -d '{\"model\":\"qwen3.5:9b\",\"messages\":[{\"role\":\"user\",\"content\":\"pong\"}],\"stream\":false,\"options\":{\"num_ctx\":4096}}'"
