; 盘枢 Knowledge Base Engine — Inno Setup 6 安装脚本
; AppId 发布后永久不变；压缩 lzma2 + Solid；以普通用户权限运行。

#define MyAppName "盘枢 Knowledge Base Engine"
#define MyAppVersion "1.0.0"
#define MyAppId "{8F1D3C4A-6E2B-4F9A-9C7D-A0B1C2D3E4F5}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=release
OutputBaseFilename=panhub-kbengine-{#MyAppVersion}-setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
UsePreviousAppDir=yes
CloseApplications=yes
RestartApplications=yes
Uninstallable=yes

[Languages]
Name: "chs"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Files]
Source: "electron-dist\win-unpacked\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "engine-release\panhub-engine.exe"; DestDir: "{app}\engine"; Flags: ignoreversion

[Registry]
Root: HKCU; Subkey: "Software\Panhub\KBEngine"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\盘枢.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\盘枢.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："

[Run]
Filename: "{app}\盘枢.exe"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\engine"
