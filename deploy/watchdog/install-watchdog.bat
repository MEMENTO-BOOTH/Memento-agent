@echo off
REM Installe le watchdog en mode user normal (sans admin, sans UAC).
REM
REM Cree un raccourci dans le dossier Startup de l'utilisateur courant qui lance
REM start-watchdog.vbs au demarrage Windows. Aucun droit admin requis.
REM Les bornes en kiosk ont l'utilisateur connecte en permanence, donc startup
REM folder est suffisant et evite la fenetre UAC sur les 200+ bornes.

set STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set VBS_PATH=%LOCALAPPDATA%\MementoAgent\watchdog\start-watchdog.vbs
set SHORTCUT=%STARTUP_DIR%\MementoWatchdog.lnk

if not exist "%VBS_PATH%" (
    echo [ERREUR] %VBS_PATH% introuvable, watchdog non installe
    exit /b 1
)

REM Supprimer ancien raccourci si existe (idempotence : reinstall ne casse rien)
if exist "%SHORTCUT%" del "%SHORTCUT%" >nul 2>&1

REM Si une ancienne tache planifiee SYSTEM existe (vieux pre-release v1.0.25.0
REM avant correction), la supprimer. Necessite admin mais si ca rate c'est pas grave.
schtasks /query /tn "MementoWatchdog" >nul 2>&1
if %ERRORLEVEL% == 0 (
    schtasks /delete /tn "MementoWatchdog" /f >nul 2>&1
)

REM Creer le raccourci via PowerShell (sans console visible grace au flag minimized)
powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT%'); $s.TargetPath='wscript.exe'; $s.Arguments='\"%VBS_PATH%\"'; $s.WindowStyle=7; $s.Save()" >nul 2>&1

if not exist "%SHORTCUT%" (
    echo [ERREUR] Creation raccourci echouee
    exit /b 1
)

echo [OK] Watchdog installe au demarrage Windows (user, sans admin)

REM Demarrer immediatement le watchdog (pas attendre prochain reboot)
start "" wscript.exe "%VBS_PATH%"
exit /b 0
