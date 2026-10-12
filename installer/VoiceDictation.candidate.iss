#ifndef SourceDir
  #define SourceDir "..\dist\VoiceDictation-portable-signed"
#endif
#ifndef AppVersion
  #define AppVersion "2.0"
#endif

[Setup]
AppId={{7F4B1655-C78D-49C7-9EAB-26063FB9A2A0}
AppName=VoiceDictation
AppVersion={#AppVersion}
AppPublisher=RanLiAiJay
VersionInfoCompany=RanLiAiJay
VersionInfoDescription=VoiceDictation 本地离线语音听写安装程序
VersionInfoProductName=VoiceDictation
VersionInfoProductVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\VoiceDictation
DefaultGroupName=VoiceDictation
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=VoiceDictation-Setup-{#AppVersion}
SetupIconFile=..\resources\VoiceDictation.ico
UninstallDisplayIcon={app}\VoiceDictation.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\VoiceDictation"; Filename: "{app}\VoiceDictation.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\VoiceDictation"; Filename: "{app}\VoiceDictation.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "VoiceDictationRanLiAiJay"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\VoiceDictation.exe"; Description: "启动 VoiceDictation"; Flags: nowait postinstall skipifsilent

