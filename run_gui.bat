@echo off
setlocal
cd /d "%~dp0"

echo ===================================================
echo   Aquila AI Framework - Launching GUI
echo ===================================================

if exist "build\msvc-release-cuda\apps\aquila_gui\aquila_gui.exe" (
    echo [INFO] Launching GPU-accelerated binary (build\msvc-release-cuda)...
    start "" "build\msvc-release-cuda\apps\aquila_gui\aquila_gui.exe" %*
    goto :done
)

if exist "build\msvc-release\apps\aquila_gui\aquila_gui.exe" (
    echo [INFO] Launching release binary (build\msvc-release)...
    start "" "build\msvc-release\apps\aquila_gui\aquila_gui.exe" %*
    goto :done
)

echo [ERROR] aquila_gui.exe not found! Please build first with scripts\msvc-dev.cmd.
exit /b 1

:done
exit /b 0
