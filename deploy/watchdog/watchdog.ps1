# Memento Agent Watchdog
#
# Verifie toutes les 30s que MementoAgent.exe tourne ET ecrit dans alertes.log.
# Si process absent OU log fige depuis > 3 min -> kill + restart.
#
# Lance par start-watchdog.vbs (fenetre cachee) via tache planifiee Windows.
# Voir install-watchdog.bat.
#
# Logs rotatifs dans %LOCALAPPDATA%\MementoAgent\watchdog.log (max 1 Mo).

$ErrorActionPreference = "Continue"

# Single-instance via mutex Local : si une autre instance tourne deja dans
# la meme session user, on sort silencieusement. Sur les bornes en kiosk,
# une seule session user existe donc Local suffit. Global\ requiert
# SeCreateGlobalPrivilege que les users normaux n'ont pas (silent fail).
$mutex = New-Object System.Threading.Mutex($false, "Local\Memento_AgentWatchdog")
if (-not $mutex.WaitOne(0, $false)) {
    exit
}

$agentDir = Join-Path $env:LOCALAPPDATA "MementoAgent"
$agentExe = Join-Path $agentDir "MementoAgent.exe"
$alertesLog = Join-Path $agentDir "alertes.log"
$watchdogLog = Join-Path $agentDir "watchdog.log"
$processName = "MementoAgent"

$checkIntervalSec = 30
$logFreezeThresholdMin = 3
$logMaxBytes = 1MB


function Write-WatchdogLog {
    param([string]$Message)
    try {
        if ((Test-Path $watchdogLog) -and ((Get-Item $watchdogLog).Length -gt $logMaxBytes)) {
            $old = "$watchdogLog.old"
            if (Test-Path $old) { Remove-Item $old -Force -ErrorAction SilentlyContinue }
            Rename-Item $watchdogLog $old -Force -ErrorAction SilentlyContinue
        }
        $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -Path $watchdogLog -Value "[$ts] $Message" -Encoding UTF8 -ErrorAction SilentlyContinue
    } catch {}
}


function Start-Agent {
    if (-not (Test-Path $agentExe)) {
        Write-WatchdogLog "ERREUR: $agentExe introuvable, agent non demarre"
        return
    }
    try {
        Start-Process -FilePath $agentExe -WindowStyle Hidden -ErrorAction Stop
        Write-WatchdogLog "Agent demarre"
    } catch {
        Write-WatchdogLog "ERREUR start: $_"
    }
}


function Stop-Agent {
    try {
        $procs = Get-Process -Name $processName -ErrorAction SilentlyContinue
        if ($procs) {
            Stop-Process -Name $processName -Force -ErrorAction SilentlyContinue
            Write-WatchdogLog "Agent kille (etait fige ou bloque)"
            Start-Sleep -Seconds 2
        }
    } catch {}
}


function Test-AgentHealthy {
    $proc = Get-Process -Name $processName -ErrorAction SilentlyContinue
    if (-not $proc) {
        Write-WatchdogLog "Process absent"
        return $false
    }
    if (-not (Test-Path $alertesLog)) {
        return $true
    }
    try {
        $lastWrite = (Get-Item $alertesLog).LastWriteTime
        $age = (Get-Date) - $lastWrite
        if ($age.TotalMinutes -gt $logFreezeThresholdMin) {
            Write-WatchdogLog "Log fige depuis $([math]::Round($age.TotalMinutes, 1)) min"
            return $false
        }
    } catch {}
    return $true
}


Write-WatchdogLog "=== Watchdog demarre (check toutes les ${checkIntervalSec}s) ==="

while ($true) {
    try {
        if (-not (Test-AgentHealthy)) {
            Stop-Agent
            Start-Agent
        }
    } catch {
        Write-WatchdogLog "Boucle: exception $_"
    }
    Start-Sleep -Seconds $checkIntervalSec
}
