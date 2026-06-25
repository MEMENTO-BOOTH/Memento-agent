@echo off
REM Installe la tache planifiee Windows qui lance le watchdog au boot.
REM
REM Necessite des droits admin (sinon impossible de creer une tache SYSTEM).
REM L'installer Inno Setup execute ce script avec PrivilegesRequired=admin.
REM
REM La tache :
REM   - tourne sous le compte SYSTEM (independant de la session user)
REM   - se declenche au boot
REM   - lance start-watchdog.vbs (qui lance watchdog.ps1 sans fenetre)
REM   - reste persistante meme si tous les utilisateurs sont deconnectes

set TASK_NAME=MementoWatchdog
set VBS_PATH=%LOCALAPPDATA%\MementoAgent\watchdog\start-watchdog.vbs

REM Verifier que le VBS existe (paranoia : si installer cassee, on log et on sort)
if not exist "%VBS_PATH%" (
    echo [ERREUR] %VBS_PATH% introuvable, watchdog non installe
    exit /b 1
)

REM Supprimer l'ancienne tache si elle existe (idempotence : ce script
REM peut etre relance par chaque update sans creer de doublons)
schtasks /query /tn "%TASK_NAME%" >nul 2>&1
if %ERRORLEVEL% == 0 (
    schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1
)

REM Creer la tache : au boot, en SYSTEM, sans interaction utilisateur
schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "wscript.exe \"%VBS_PATH%\"" ^
    /sc onstart ^
    /ru SYSTEM ^
    /rl HIGHEST ^
    /f >nul

if %ERRORLEVEL% == 0 (
    echo [OK] Tache planifiee "%TASK_NAME%" creee
    REM Lancer le watchdog immediatement (pas attendre le prochain reboot)
    schtasks /run /tn "%TASK_NAME%" >nul 2>&1
    exit /b 0
) else (
    echo [ERREUR] Creation tache echouee, code %ERRORLEVEL%
    exit /b 1
)
