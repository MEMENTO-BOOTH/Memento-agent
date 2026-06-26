@echo off
REM Installe le watchdog en mode user normal (sans admin, sans UAC).
REM
REM Cree une entree HKCU\Software\Microsoft\Windows\CurrentVersion\Run
REM pour lancer start-watchdog.vbs au demarrage de la session utilisateur.
REM
REM Pourquoi pas le startup folder : certaines bornes ont un script tiers
REM (StartupWatchdog generique) qui scanne le startup folder et relance
REM tout programme qu'il ne trouve pas en process. Vu que notre VBS meurt
REM apres avoir lance powershell, le StartupWatchdog le relance en boucle.
REM HKCU\Run n'est pas scanne par ce script tiers -> pas de conflit.

set VBS_PATH=%LOCALAPPDATA%\MementoAgent\watchdog\start-watchdog.vbs
set REG_NAME=MementoAgentWatchdog

if not exist "%VBS_PATH%" (
    echo [ERREUR] %VBS_PATH% introuvable, watchdog non installe
    exit /b 1
)

REM Cleanup ancien raccourci Startup (rollback pour les bornes ayant eu
REM la v1.0.25.0 initiale avec startup folder)
set OLD_LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\MementoWatchdog.lnk
if exist "%OLD_LNK%" del "%OLD_LNK%" >nul 2>&1

REM Cleanup ancienne tache planifiee SYSTEM (rollback v1.0.25.0 admin)
schtasks /query /tn "MementoWatchdog" >nul 2>&1
if %ERRORLEVEL% == 0 (
    schtasks /delete /tn "MementoWatchdog" /f >nul 2>&1
)

REM Cleanup proactif : tuer toutes les instances existantes du watchdog
REM avant d'en lancer une nouvelle. Empeche l'accumulation observee sur
REM les bornes equipees du StartupWatchdog tiers (qui pouvait spawner
REM plusieurs instances avant le passage en HKCU\Run + mutex Local).
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | Where-Object { $_.CommandLine -match 'MementoAgent.watchdog.watchdog.ps1' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

REM Creer l'entree HKCU\Run (pas besoin d'admin, pas dans startup folder)
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "%REG_NAME%" /t REG_SZ /d "wscript.exe \"%VBS_PATH%\"" /f >nul

if %ERRORLEVEL% neq 0 (
    echo [ERREUR] Creation entree registry echouee
    exit /b 1
)

echo [OK] Watchdog installe (HKCU\Run, sans admin, sans conflit avec autres watchdogs)

REM Demarrer immediatement le watchdog (pas attendre prochain reboot).
REM Le mutex single-instance dans watchdog.ps1 empeche les doublons si
REM celui-ci est appele plusieurs fois.
start "" wscript.exe "%VBS_PATH%"
exit /b 0
