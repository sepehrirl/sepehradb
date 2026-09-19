[Setup]
AppId={{A1C9E2E7-5B0D-4D5A-9C4D-SEPEHRADB2026}}
AppName=SEPEHR ADB HUB
AppVersion=2.0.0
AppPublisher=SEPEHR
DefaultDirName={autopf}\SEPEHR ADB HUB
DefaultGroupName=SEPEHR ADB HUB
OutputDir=installer
OutputBaseFilename=SEPEHR-ADB-HUB-Setup
SetupIconFile=SEPEHR-ADB-HUB.ico
UninstallDisplayIcon={app}\SEPEHR-ADB-HUB.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin

[Tasks]
Name: "desktopicon"; Description: "ساخت میانبر روی دسکتاپ"; GroupDescription: "میانبرها:"; Flags: unchecked

[Files]
Source: "release\SEPEHR-ADB-HUB.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "release\adb.exe"; DestDir: "{app}\platform-tools"; Flags: ignoreversion
Source: "release\AdbWinApi.dll"; DestDir: "{app}\platform-tools"; Flags: ignoreversion
Source: "release\AdbWinUsbApi.dll"; DestDir: "{app}\platform-tools"; Flags: ignoreversion
Source: "release\sepehradb.svg"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "release\OFL.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion
Source: "release\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\SEPEHR ADB HUB"; Filename: "{app}\SEPEHR-ADB-HUB.exe"; IconFilename: "{app}\SEPEHR-ADB-HUB.exe"
Name: "{autodesktop}\SEPEHR ADB HUB"; Filename: "{app}\SEPEHR-ADB-HUB.exe"; Tasks: desktopicon; IconFilename: "{app}\SEPEHR-ADB-HUB.exe"

[Run]
Filename: "{app}\SEPEHR-ADB-HUB.exe"; Description: "اجرای SEPEHR ADB HUB"; Flags: nowait postinstall skipifsilent
