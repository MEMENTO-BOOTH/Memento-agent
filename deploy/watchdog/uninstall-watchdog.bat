@echo off
REM Cleanup du watchdog lors de la desinstallation.

REM Supprimer entree HKCU\Run
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "MementoAgentWatchdog" /f >nul 2>&1

REM Cleanup ancien raccourci Startup folder (versions anterieures)
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\MementoWatchdog.lnk" >nul 2>&1

REM Cleanup ancienne tache planifiee SYSTEM (versions anterieures)
schtasks /delete /tn "MementoWatchdog" /f >nul 2>&1

REM Tuer tous les processus PowerShell qui executent watchdog.ps1
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" | Where-Object { $_.CommandLine -match 'MementoAgent.watchdog.watchdog.ps1' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

exit /b 0
