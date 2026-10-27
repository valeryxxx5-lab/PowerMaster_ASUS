[Setup]
AppId={{5B6A8C2D-A45B-4C0E-921F-9A52B884C0F7}
AppName=PowerMaster ASUS TUF
AppVersion=0.2.60
VersionInfoVersion=0.2.60.0
VersionInfoTextVersion=0.2.60.0
VersionInfoProductVersion=0.2.60.0
VersionInfoProductTextVersion=0.2.60.0
AppPublisher=PowerMaster ASUS
; Устанавливается в %LOCALAPPDATA%\PowerMaster_ASUS — права администратора НЕ НУЖНЫ
DefaultDirName={localappdata}\PowerMaster_ASUS
DefaultGroupName=PowerMaster ASUS TUF
OutputDir=installer\Output
OutputBaseFilename=PowerMaster_ASUS_Setup
SetupIconFile=compiler:SetupClassicIcon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; lowest = не требует прав администратора, UAC не запрашивается
PrivilegesRequired=lowest
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "autostart"; Description: "Добавить в автозапуск (запуск при входе в систему)"; GroupDescription: "Автозапуск"

[Files]
Source: "dist\PowerMaster_ASUS.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "config.json"; DestDir: "{app}"; Flags: onlyifdoesntexist skipifsourcedoesntexist

[Icons]
Name: "{group}\PowerMaster ASUS TUF"; Filename: "{app}\PowerMaster_ASUS.exe"
Name: "{group}\{cm:UninstallProgram,PowerMaster ASUS TUF}"; Filename: "{uninstallexe}"

[Run]
; Запуск приложения после установки / обновления (включая тихий режим)
Filename: "{app}\PowerMaster_ASUS.exe"; Parameters: "--tray"; WorkingDir: "{app}"; Flags: nowait runasoriginaluser

[Registry]
; Автозапуск через реестр HKCU — не требует прав администратора
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "PowerMaster_ASUS"; ValueData: """{app}\PowerMaster_ASUS.exe"" --tray"; Flags: uninsdeletevalue; Tasks: autostart

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM PowerMaster_ASUS.exe"; Flags: runhidden; RunOnceId: "KillBeforeUninstall"

[Code]
procedure KillRunningPowerMaster();
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM PowerMaster_ASUS.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(600);
end;

function InitializeSetup(): Boolean;
begin
  KillRunningPowerMaster();
  Result := True;
end;

function InitializeUninstall(): Boolean;
begin
  KillRunningPowerMaster();
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Удаляем устаревшую папку Program Files (x86), если она осталась от старых версий
    if DirExists(ExpandConstant('{commonpf32}\PowerMaster_ASUS')) then
    begin
      DelTree(ExpandConstant('{commonpf32}\PowerMaster_ASUS'), True, True, True);
    end;
  end;
end;
