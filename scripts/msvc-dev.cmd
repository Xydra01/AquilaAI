@echo off
rem Runs a command inside an x64 MSVC developer environment.
rem   scripts\msvc-dev.cmd cmake --workflow --preset msvc-release
rem Override the Visual Studio location with AQUILA_VSDEVCMD=<path to VsDevCmd.bat>.
setlocal
set "VSDEVCMD=%AQUILA_VSDEVCMD%"
if not defined VSDEVCMD (
    for /f "usebackq delims=" %%i in (`"%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VSDEVCMD=%%i\Common7\Tools\VsDevCmd.bat"
)
if not exist "%VSDEVCMD%" (
    echo msvc-dev: VsDevCmd.bat not found. Set AQUILA_VSDEVCMD. 1>&2
    exit /b 1
)
call "%VSDEVCMD%" -arch=x64 -host_arch=x64 -no_logo
if errorlevel 1 exit /b 1
%*
exit /b %ERRORLEVEL%
