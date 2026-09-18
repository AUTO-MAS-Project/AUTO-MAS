; AUTO-MAS Inno Setup script.
; VERSION_TAG / GITHUB_WORKSPACE are provided by the build workflow environment.

#define MyAppName "AUTO-MAS"
#define MyAppVersion GetEnv("VERSION_TAG")
#define MyAppPublisher "AUTO-MAS Team"
#define MyAppURL "https://auto-mas.top/"
#define MyAppExeName "AUTO-MAS.exe"
#define MyAppPath GetEnv("GITHUB_WORKSPACE") + "\frontend\dist\win-unpacked"
#define RootPath GetEnv("GITHUB_WORKSPACE")

[Setup]
AppId={{D116A92A-E174-4699-B777-61C5FD837B19}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
LicenseFile={#RootPath}\LICENSE
PrivilegesRequired=admin
OutputDir={#RootPath}
OutputBaseFilename=AUTO-MAS-Setup
SetupIconFile={#RootPath}\res\icons\AUTO-MAS.ico
SolidCompression=yes
WizardStyle=modern
AppMutex=AUTO_MAS_Installer_Mutex

[Languages]
Name: "Chinese"; MessagesFile: "{#RootPath}\res\docs\ChineseSimplified.isl"
Name: "English"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#MyAppPath}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall runascurrentuser

[Code]

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DelTree(ExpandConstant('{app}'), True, True, True);
  end;
end;
