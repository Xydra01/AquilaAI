; Inno Setup script for Aquila OS (Windows x64 / ARM64)
; Requires Inno Setup 6+ and a completed PyInstaller onedir at SourceDir

#ifndef AppVersion
  #define AppVersion "3.5.0"
#endif
#ifndef ArchSuffix
  #define ArchSuffix ""
#endif
#ifndef SourceDir
  #define SourceDir "dist\Aquila"
#endif

#ifndef DockerInstallerPath
  #define DockerInstallerPath ""
#endif

[Setup]
AppName=Aquila OS
AppVersion={#AppVersion}
DefaultDirName={autopf}\Aquila
DefaultGroupName=Aquila
OutputBaseFilename=Aquila-{#AppVersion}{#ArchSuffix}-setup
OutputDir=dist
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible arm64

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#DockerInstallerPath}"; DestDir: "{tmp}"; DestName: "DockerDesktopInstaller.exe"; Flags: deleteafterinstall; Tasks: dockerdesktop; Check: ShouldOfferDockerInstaller

[Icons]
Name: "{group}\Aquila"; Filename: "{app}\Aquila.exe"
Name: "{autodesktop}\Aquila"; Filename: "{app}\Aquila.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"
Name: "dockerdesktop"; Description: "Install Docker Desktop (optional - enables web search via SearXNG)"; GroupDescription: "Optional components:"; Flags: unchecked; Check: ShouldOfferDockerInstaller
Name: "startdocker"; Description: "Ensure Docker Desktop is running (already installed on this PC)"; GroupDescription: "Optional components:"; Check: DockerDesktopInstalled

[Run]
Filename: "{app}\Aquila.exe"; Description: "Launch Aquila"; Flags: nowait postinstall skipifsilent
Filename: "{code:DockerDesktopExePath}"; Description: "Start Docker Desktop"; StatusMsg: "Starting Docker Desktop..."; Tasks: startdocker; Flags: nowait postinstall skipifsilent; Check: ShouldTryStartDockerDesktop

[Code]
var
  DockerProgressPage: TOutputProgressWizardPage;
  VirtWarningPage: TWizardPage;
  VirtCheckResult: Integer;  { 1=enabled, 0=disabled, -1=unknown }
  DockerInstallDone: Boolean;

function DockerInstallerBundled: Boolean;
begin
  Result := '{#DockerInstallerPath}' <> '';
end;

function DockerDesktopInstalled: Boolean;
var
  Path: String;
begin
  Path := ExpandConstant('{pf}\Docker\Docker\Docker Desktop.exe');
  if FileExists(Path) then
  begin
    Result := True;
    exit;
  end;
  Path := ExpandConstant('{pf32}\Docker\Docker\Docker Desktop.exe');
  Result := FileExists(Path);
end;

function DockerDesktopExePath(Param: String): String;
begin
  Result := ExpandConstant('{pf}\Docker\Docker\Docker Desktop.exe');
  if not FileExists(Result) then
    Result := ExpandConstant('{pf32}\Docker\Docker\Docker Desktop.exe');
end;

function VirtOutputPath: String;
begin
  Result := ExpandConstant('{localappdata}\Aquila\virt-check.txt');
end;

procedure RunVirtualizationCheck;
var
  ResultCode: Integer;
  OutputFile: String;
  Lines: TArrayOfString;
  I: Integer;
  Line: String;
  PsCmd: String;
begin
  if VirtCheckResult <> -2 then
    Exit;
  VirtCheckResult := -1;
  OutputFile := VirtOutputPath;
  PsCmd :=
    '$out=''' + OutputFile + '''; ' +
    'New-Item -ItemType Directory -Force -Path (Split-Path $out) | Out-Null; ' +
    '$p = Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue | Select-Object -First 1; ' +
    'if ($null -eq $p) { ''unknown'' | Set-Content -NoNewline $out; exit 0 }; ' +
    'if ($p.VirtualizationFirmwareEnabled) { ''yes'' | Set-Content -NoNewline $out } ' +
    'else { ''no'' | Set-Content -NoNewline $out }';
  if Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -ExecutionPolicy Bypass -NonInteractive -WindowStyle Hidden -Command ' +
    PsCmd, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    if LoadStringsFromFile(OutputFile, Lines) then
    begin
      for I := 0 to GetArrayLength(Lines) - 1 do
      begin
        Line := LowerCase(Trim(Lines[I]));
        if Line = 'yes' then
        begin
          VirtCheckResult := 1;
          Exit;
        end;
        if Line = 'no' then
        begin
          VirtCheckResult := 0;
          Exit;
        end;
      end;
    end;
  end;
end;

function IsVirtualizationFirmwareEnabled: Boolean;
begin
  if DockerDesktopInstalled then
  begin
    Result := True;
    Exit;
  end;
  RunVirtualizationCheck;
  if VirtCheckResult = 1 then
    Result := True
  else if VirtCheckResult = 0 then
    Result := False
  else
    Result := True;
end;

function VirtCheckExplicitlyDisabled: Boolean;
begin
  if DockerDesktopInstalled then
  begin
    Result := False;
    Exit;
  end;
  RunVirtualizationCheck;
  Result := (VirtCheckResult = 0);
end;

function ShouldOfferDockerInstaller: Boolean;
begin
  Result := DockerInstallerBundled and (not DockerDesktopInstalled) and IsVirtualizationFirmwareEnabled;
end;

function ShouldTryStartDockerDesktop: Boolean;
begin
  Result := DockerDesktopInstalled and FileExists(DockerDesktopExePath(''));
end;

procedure InstallDockerDesktop;
var
  ResultCode: Integer;
  InstallerPath: String;
begin
  if DockerInstallDone then
    Exit;
  DockerInstallDone := True;
  InstallerPath := ExpandConstant('{tmp}\DockerDesktopInstaller.exe');
  if not FileExists(InstallerPath) then
  begin
    MsgBox('Docker Desktop installer file is missing.', mbError, MB_OK);
    Exit;
  end;
  DockerProgressPage := CreateOutputProgressPage(
    'Installing Docker Desktop',
    'This can take 5-15 minutes. The installer is still working - please leave this window open.');
  DockerProgressPage.SetText(
    'Running Docker Desktop installer (UAC may appear)...',
    'Download and setup progress is handled by Docker; Aquila will continue when it finishes.');
  DockerProgressPage.Show;
  try
    if not Exec(InstallerPath, 'install --quiet --accept-license', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      MsgBox('Docker Desktop installer failed to start.', mbError, MB_OK)
    else if ResultCode <> 0 then
      MsgBox(
        'Docker Desktop installer exited with code ' + IntToStr(ResultCode) + '.'#13#10 +
        'You can install Docker manually later for web search.',
        mbInformation, MB_OK);
  finally
    DockerProgressPage.Hide;
    DockerProgressPage := nil;
  end;
end;

function InitializeSetup(): Boolean;
begin
  VirtCheckResult := -2;
  DockerInstallDone := False;
  Result := True;
end;

procedure InitializeWizard();
begin
  if DockerInstallerBundled and (not DockerDesktopInstalled) and VirtCheckExplicitlyDisabled then
  begin
    VirtWarningPage := CreateOutputMsgPage(
      wpWelcome,
      'CPU virtualization appears disabled',
      'Docker Desktop requires Intel VT-x or AMD-V enabled in your BIOS/firmware.'#13#10#13#10 +
      'Aquila chat works without Docker. Enable virtualization, reboot, then re-run this installer to add optional web search.'#13#10#13#10 +
      'Task Manager -> Performance -> CPU shows whether virtualization is enabled.',
      'If virtualization is already enabled, this check can be wrong - you can install Docker manually.');
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and IsTaskSelected('dockerdesktop') and ShouldOfferDockerInstaller then
    InstallDockerDesktop;
end;
