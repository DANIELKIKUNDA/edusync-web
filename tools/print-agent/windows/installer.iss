[Setup]
AppId=EduSyncPrintConnectorStaging
AppMutex=Local\EduSyncPrintConnectorStaging
AppName=EduSync Print Connector (staging)
AppVersion=0.1.0
AppPublisher=Volcano Tech
DefaultDirName={localappdata}\Programs\EduSync Print Connector Staging
DefaultGroupName=EduSync Print Connector (staging)
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
OutputDir=dist
WizardStyle=modern
UninstallDisplayIcon={app}\EduSyncPrintConnector.exe
#ifdef SignStaging
OutputBaseFilename=EduSync-Print-Setup-Staging-Signed
SignTool=edusync
SignedUninstaller=yes
#else
OutputBaseFilename=EduSync-Print-Setup-Staging
#endif

[Files]
Source: "payload\*"; DestDir: "{app}"; Excludes: "EduSyncPrintConnector.exe"; Flags: ignoreversion recursesubdirs createallsubdirs
#ifdef SignStaging
Source: "payload\EduSyncPrintConnector.exe"; DestDir: "{app}"; Flags: ignoreversion sign
#else
Source: "payload\EduSyncPrintConnector.exe"; DestDir: "{app}"; Flags: ignoreversion
#endif
Source: "..\server.mjs"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\EduSync Print Connector (staging)"; Filename: "{app}\EduSyncPrintConnector.exe"
Name: "{userstartup}\EduSync Print Connector (staging)"; Filename: "{app}\EduSyncPrintConnector.exe"

[Run]
Filename: "{app}\EduSyncPrintConnector.exe"; Description: "Ouvrir EduSync Print Connector"; Flags: nowait postinstall skipifsilent
