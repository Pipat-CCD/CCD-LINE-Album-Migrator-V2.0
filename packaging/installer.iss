#ifndef AppVersion
  #define AppVersion "2.0.1"
#endif
#define AppName "CCD LINE Album Migrator V2.0"

[Setup]
AppId={{5779E42C-6A0B-4DC0-939D-8F607F40E7E5}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=CCD Thailand
AppPublisherURL=https://github.com/Pipat-CCD/CCD-LINE-Album-Migrator-V2.0
DefaultDirName={localappdata}\Programs\CCDLineMigrator
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist\installer
OutputBaseFilename=CCDLineMigrator-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\CCDLineMigrator.exe
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "thai"; MessagesFile: "Thai.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "สร้างไอคอนบน Desktop"; GroupDescription: "ทางลัด"; Flags: unchecked

[Files]
Source: "..\dist\CCDLineMigrator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "THIRD_PARTY_NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\CCDLineMigrator.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\CCDLineMigrator.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\CCDLineMigrator.exe"; Description: "เปิด CCD LINE Album Migrator"; Flags: nowait postinstall skipifsilent

; User data lives outside {app}, in {localappdata}\CCDLineMigrator.
; Intentionally no UninstallDelete entries: preserve history, copies, and account settings.
