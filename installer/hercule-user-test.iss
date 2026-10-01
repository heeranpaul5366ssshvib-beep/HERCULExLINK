; HERCULE TEST-ONLY per-user installer variant (no admin required).
; Validates the current payload's install -> launch -> uninstall cycle in
; non-elevated CI-like shells. NOT the release installer (see hercule.iss).
; Payload is identical: dist/HERCULE bundle, user data stays in
; %LOCALAPPDATA%\HERCULE and is never touched.
#define MyAppName "HERCULE-Test"
#define MyAppFullName "HERCULE AI Operating System (Test)"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "HERCULE"
#define MyAppExeName "HERCULE.exe"

[Setup]
AppId={{3B4E5A1C-7F2A-4D8E-9C1B-8A7F6E5D4C3C}
AppName={#MyAppName}
AppVerName={#MyAppFullName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=..\installer-output
OutputBaseFilename=HERCULE-User-Test-Setup
Compression=lzma2/max
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\{#MyAppExeName}
UsePreviousAppDir=yes
DirExistsWarning=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\HERCULE\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\hercule.ico"

[UninstallDelete]
Type: files; Name: "{app}\*.log"
