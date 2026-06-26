#define MyAppName "Memento Agent"
#define MyAppPublisher "Memento Booth"
#define MyAppExeName "MementoAgent.exe"
#define MyAppIconFile "assets\logo.ico"

; Lecture de la version depuis version.py (source unique de verite)
; Format attendu de version.py :
;   ligne 1 : """docstring"""
;   ligne 2 : (vide)
;   ligne 3 : VERSION = "x.y.z"
#define VersionFile FileOpen("version.py")
#expr FileRead(VersionFile)
#expr FileRead(VersionFile)
#define VersionLine FileRead(VersionFile)
#expr FileClose(VersionFile)
#if Pos("VERSION", VersionLine) == 0
  #error "version.py: ligne VERSION introuvable a la ligne 3 (format inattendu)"
#endif
#define MyAppVersion Copy(VersionLine, Pos('"', VersionLine) + 1, RPos('"', VersionLine) - Pos('"', VersionLine) - 1)

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
; Auto-update : le nouvel installer doit fermer MementoAgent.exe en cours
; (sinon le replace du .exe foire silencieusement et la borne reste bloquee
; sur l'ancienne version meme si elle voit la nouvelle dispo).
; CloseApplications=force utilise le Restart Manager Windows pour fermer
; proprement l'agent avant de remplacer le fichier. RestartApplications=no
; car le watchdog (ou le postinstall) relancera l'agent.
CloseApplications=force
RestartApplications=no
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

; Watchdog : surveille MementoAgent.exe et le redemarre s'il crashe.
; Suite incident REV3 22/06/2026 (44h agent mort, ~15 clients impactes).
Source: "deploy\watchdog\watchdog.ps1"; DestDir: "{app}\watchdog"; Flags: ignoreversion
Source: "deploy\watchdog\start-watchdog.vbs"; DestDir: "{app}\watchdog"; Flags: ignoreversion
Source: "deploy\watchdog\install-watchdog.bat"; DestDir: "{app}\watchdog"; Flags: ignoreversion
Source: "deploy\watchdog\uninstall-watchdog.bat"; DestDir: "{app}\watchdog"; Flags: ignoreversion


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
; Installer la tache planifiee watchdog (necessite admin, on en a deja les droits)
Filename: "{app}\watchdog\install-watchdog.bat"; Flags: runhidden waituntilterminated
; Lancer l'agent
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[UninstallRun]
; Cleanup complet du watchdog (registry + raccourcis + processus)
Filename: "{app}\watchdog\uninstall-watchdog.bat"; Flags: runhidden waituntilterminated; RunOnceId: "UninstallWatchdog"
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
