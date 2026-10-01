; HERCULE Inno Setup script — produces HERCULE-Setup.exe
; Build: installer output from dist/HERCULE (PyInstaller --onedir).
; Requires Inno Setup 6 (iscc). User data lives in %LOCALAPPDATA%\HERCULE
; and is NEVER deleted by install, upgrade, or uninstall.
#define MyAppName "HERCULE"
#define MyAppFullName "HERCULE AI Operating System"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "HERCULE"
#define MyAppExeName "HERCULE.exe"

[Setup]
AppId={{3B4E5A1C-7F2A-4D8E-9C1B-8A7F6E5D4C3B}
AppName={#MyAppName}
AppVerName={#MyAppFullName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=..\installer-output
OutputBaseFilename=HERCULE-Setup
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
; Per-user install: no Administrator privileges required. {autopf} maps to
; the per-user Programs folder with lowest privileges, so the install dir
; stays read-only at runtime and all writable state lives in %LOCALAPPDATA%\HERCULE.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\{#MyAppExeName}
; Upgrade-safe: reinstall over existing installation without prompts
UsePreviousAppDir=yes
DirExistsWarning=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Application bundle only — never user data, tests, venv, or model weights
Source: "..\dist\HERCULE\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\hercule.ico"
Name: "{userprograms}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\hercule.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Only install-dir leftovers. %LOCALAPPDATA%\HERCULE (memory, tasks,
; logs, config, caches, experience data) is deliberately preserved.
Type: files; Name: "{app}\*.log"
