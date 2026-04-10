#define MyAppName "Memento Agent"
#define MyAppVersion "1.0.7"
#define MyAppPublisher "Memento Booth"
#define MyAppExeName "MementoAgent.exe"
#define MyAppIconFile "assets\logo.ico"

[Setup]
AppId={{B3A2F7D1-4E8C-4A2B-9F3D-1C5E7A9B2D4F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://www.mementobooth.com
AppSupportURL=https://www.mementobooth.com
AppUpdatesURL=https://www.mementobooth.com
DefaultDirName={localappdata}\MementoAgent
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
SetupIconFile={#MyAppIconFile}
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
OutputDir=installer_output
OutputBaseFilename=MementoAgent_Setup_{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
; Masquer les pages redondantes — l'app gère son propre setup au 1er lancement
DisableWelcomePage=yes
DisableReadyPage=yes
DisableFinishedPage=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer une icône sur le &Bureau"; GroupDescription: "Icônes supplémentaires :"; Flags: checkedonce
Name: "startmenuicon"; Description: "Créer une icône dans le menu &Démarrer"; GroupDescription: "Icônes supplémentaires :"; Flags: checkedonce

[Files]
; Exécutable principal (depuis le build PyInstaller)
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Dossier assets complet
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs

; Fichier de configuration .env (ne pas écraser si existe déjà)
Source: ".env"; DestDir: "{app}"; Flags: onlyifdoesntexist


[Icons]
; Raccourci Bureau
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\logo.ico"; Tasks: desktopicon

; Raccourci Menu Démarrer
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\logo.ico"; Tasks: startmenuicon

; Désinstallateur dans le menu Démarrer
Name: "{group}\Désinstaller {#MyAppName}"; Filename: "{uninstallexe}"

[Registry]
; Démarrage automatique avec Windows pour l'utilisateur courant
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "MementoAgent"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[UninstallRun]
; Fermer l'app avant désinstallation
Filename: "taskkill"; Parameters: "/F /IM {#MyAppExeName}"; Flags: runhidden; RunOnceId: "KillApp"

[Code]
var
  ResultCode: Integer;

procedure CleanRegistry();
begin
  RegDeleteKeyIncludingSubkeys(HKCU, 'Software\MementoAgent');
end;

procedure CleanDataFolders();
var
  ProfilePath: String;
begin
  // Nettoyer .mementoagent
  ProfilePath := ExpandConstant('{%USERPROFILE}');
  if ProfilePath <> '' then
    DelTree(ProfilePath + '\.mementoagent', True, True, True);
  // Nettoyer AppData\Local\MementoAgent
  DelTree(ExpandConstant('{localappdata}\MementoAgent'), True, True, True);
end;

function IsUpgrade(): Boolean;
begin
  // Vérifie si l'app est déjà installée (le .exe existe)
  Result := FileExists(ExpandConstant('{app}\{#MyAppExeName}'));
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    // Fermer l'app
    Exec('taskkill', '/F /IM {#MyAppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    // Première installation → nettoyer le registre pour afficher la page setup
    if not IsUpgrade() then
    begin
      CleanRegistry();
      CleanDataFolders();
    end;
    // Mise à jour → ne rien toucher
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    CleanRegistry();
    CleanDataFolders();
  end;
end;
