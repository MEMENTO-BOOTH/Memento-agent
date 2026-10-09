# Memento Agent Watchdog
#
# Verifie toutes les 30s que MementoAgent.exe tourne ET ecrit dans alertes.log.
# Si process absent OU log fige depuis > 3 min -> kill + restart.
#
# v1.0.28.14 : 3 protections critiques contre la boucle de kills (bug observe
#              MB-39, MB-13, MB-31 : env 730 Go de dossiers _MEI accumules
#              dans %TEMP% faute d'arret propre du bootloader PyInstaller) :
#
#   1. GRACE DELAY : apres un restart, on ne check PAS alertes.log pendant
#      5 min — laisse l'agent le temps de boot (import PyInstaller + PyQt5
#      + attente reseau prennent souvent 60-90 s).
#   2. CIRCUIT BREAKER : max 6 restarts par heure. Au-dela, on sleep 30 min
#      et on nettoie — evite la boucle de kills.
#   3. _MEI CLEANUP : au demarrage ET toutes les heures, supprime les dossiers
#      _MEIxxxxx de %TEMP% plus vieux qu'1 h (209 Mo chacun, orphelins si
#      bootloader PyInstaller tue avant son cleanup).
#
# Lance par start-watchdog.vbs (fenetre cachee) via tache planifiee Windows.
# Logs rotatifs dans %LOCALAPPDATA%\MementoAgent\watchdog.log (max 1 Mo).

$ErrorActionPreference = "Continue"

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

# v1.0.28.14 — nouvelles protections
$graceDelaySec = 300           # 5 min apres chaque restart avant de re-check alertes.log
$maxRestartsPerHour = 6        # circuit breaker
$meiCleanupIntervalSec = 3600  # nettoyage _MEI toutes les heures
$meiMinAgeMinutes = 60         # ne touche pas aux _MEI de moins d'1 h

$lastRestartTs = $null
$restartTimestamps = @()
$lastMeiCleanupTs = Get-Date 0


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


function Invoke-MeiCleanup {
    # Supprime les dossiers _MEI* > meiMinAgeMinutes dans le %TEMP% user.
    # NE touche PAS aux dossiers recents (l'instance en cours est protegee).
    try {
        $temp = [IO.Path]::GetTempPath()
        $cutoff = (Get-Date).AddMinutes(-$meiMinAgeMinutes)
        $old = @(Get-ChildItem $temp -Directory -Force -Filter "_MEI*" -ErrorAction SilentlyContinue |
            Where-Object { $_.CreationTime -lt $cutoff })
        if ($old.Count -eq 0) {
            return
        }
        $n = 0
        foreach ($d in $old) {
            try {
                Remove-Item -LiteralPath $d.FullName -Recurse -Force -ErrorAction SilentlyContinue
                if (-not (Test-Path $d.FullName)) { $n++ }
            } catch {}
        }
        if ($n -gt 0) {
            $freeGo = [math]::Round((Get-PSDrive C).Free / 1GB, 1)
            Write-WatchdogLog "_MEI cleanup: $n dossier(s) supprime(s) (libre: $freeGo Go)"
        }
    } catch {
        Write-WatchdogLog "_MEI cleanup erreur: $_"
    }
}


function Start-Agent {
    if (-not (Test-Path $agentExe)) {
        Write-WatchdogLog "ERREUR: $agentExe introuvable, agent non demarre"
        return
    }
    try {
        Start-Process -FilePath $agentExe -WindowStyle Hidden -ErrorAction Stop
        $script:lastRestartTs = Get-Date
        $script:restartTimestamps += (Get-Date)
        # Garder seulement les restarts de la derniere heure
        $cutoff = (Get-Date).AddHours(-1)
        $script:restartTimestamps = @($script:restartTimestamps | Where-Object { $_ -gt $cutoff })
        Write-WatchdogLog "Agent demarre (grace delay ${graceDelaySec}s, restarts dernere h: $($script:restartTimestamps.Count))"
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
    # v1.0.28.14 : grace delay — ne pas check le log pendant les N min
    # qui suivent un restart (l'agent peut mettre 60-90 s a ecrire sa 1re
    # ligne meme avec le fix _boot_alertes_log en v1.0.28.14).
    if ($script:lastRestartTs -and ((Get-Date) - $script:lastRestartTs).TotalSeconds -lt $graceDelaySec) {
        return $true
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


function Test-CircuitBreakerOpen {
    # v1.0.28.14 : ne pas restart si on en a deja fait > maxRestartsPerHour
    # dans la derniere heure. Casse la boucle infinie de kills.
    $cutoff = (Get-Date).AddHours(-1)
    $recent = @($script:restartTimestamps | Where-Object { $_ -gt $cutoff })
    return $recent.Count -ge $maxRestartsPerHour
}


Write-WatchdogLog "=== Watchdog v1.0.28.14 demarre (check ${checkIntervalSec}s, grace ${graceDelaySec}s, max ${maxRestartsPerHour} restarts/h) ==="
Invoke-MeiCleanup
$lastMeiCleanupTs = Get-Date

while ($true) {
    try {
        # Nettoyage _MEI toutes les heures
        if (((Get-Date) - $lastMeiCleanupTs).TotalSeconds -ge $meiCleanupIntervalSec) {
            Invoke-MeiCleanup
            $lastMeiCleanupTs = Get-Date
        }

        if (-not (Test-AgentHealthy)) {
            if (Test-CircuitBreakerOpen) {
                # Circuit breaker ouvert : on ne restart plus, on attend 30 min.
                # Laisse le disque se calmer (plus de _MEI qui s'accumule) et
                # eventuellement a l'operateur de debloquer manuellement.
                Write-WatchdogLog "Circuit breaker OUVERT (>=$($script:restartTimestamps.Count) restarts dans la derniere h) — pause 30 min"
                Start-Sleep -Seconds 1800
                # Reset partiel : on retire les plus vieux pour pouvoir reessayer
                $script:restartTimestamps = @()
                continue
            }
            Stop-Agent
            Start-Agent
        }
    } catch {
        Write-WatchdogLog "Boucle: exception $_"
    }
    Start-Sleep -Seconds $checkIntervalSec
}
