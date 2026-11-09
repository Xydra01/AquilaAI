@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo   Aquila AI Framework - Launching GUI
echo ===================================================

if exist "build\msvc-release-cuda\apps\aquila_gui\aquila_gui.exe" goto :launch_cuda
if exist "build\msvc-release\apps\aquila_gui\aquila_gui.exe" goto :launch_release

echo [ERROR] aquila_gui.exe not found! Please build first with scripts\msvc-dev.cmd.
exit /b 1

:launch_cuda
echo [INFO] Launching GPU-accelerated binary [build\msvc-release-cuda]...
start "" "build\msvc-release-cuda\apps\aquila_gui\aquila_gui.exe" %*
exit /b 0

:launch_release
echo [INFO] Launching release binary [build\msvc-release]...
start "" "build\msvc-release\apps\aquila_gui\aquila_gui.exe" %*
exit /b 0
