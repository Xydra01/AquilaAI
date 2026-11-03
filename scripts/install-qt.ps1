# Installs the Qt SDK used by the MSVC presets.
# Re-runnable: aqt skips archives that are already extracted.
param(
    [string]$QtVersion = "6.11.3",
    [string]$OutputDir = "F:\Qt",
    # aqtinstall 3.3.0 (latest release) cannot read the Qt >= 6.11 repository layout;
    # the fix (miurahr/aqtinstall#1000) is only on master, so pin a master commit.
    [string]$AqtCommit = "5a49f2b391ae8ee1d3c0dd87f8b33c1d49a4deb7",
    [string]$VenvDir = "$env:USERPROFILE\.aqt-venv"
)
$ErrorActionPreference = "Stop"

if (-not (Test-Path "$VenvDir\Scripts\python.exe")) {
    py -3 -m venv $VenvDir
}
& "$VenvDir\Scripts\python.exe" -m pip install --quiet "aqtinstall @ git+https://github.com/miurahr/aqtinstall.git@$AqtCommit"
if ($LASTEXITCODE -ne 0) { throw "pip install aqtinstall@$AqtCommit failed" }

# Since Qt 6.8, WebEngine ships from the "extensions" repository; aqt resolves it via -m.
# qttasktree: WebEngine's Qml dependency chain looks for Qt6TaskTree in 6.11.
& "$VenvDir\Scripts\aqt.exe" install-qt windows desktop $QtVersion win64_msvc2022_64 `
    --outputdir $OutputDir `
    -m qtwebengine qtwebchannel qtpositioning qttasktree
if ($LASTEXITCODE -ne 0) { throw "aqt install-qt failed" }

$prefix = Join-Path $OutputDir "$QtVersion\msvc2022_64"
& "$prefix\bin\qtpaths.exe" --qt-version
if (-not (Test-Path "$prefix\lib\cmake\Qt6WebEngineWidgets")) {
    throw "Qt6WebEngineWidgets CMake package missing under $prefix"
}
Write-Host "QT_ROOT_DIR=$prefix"
