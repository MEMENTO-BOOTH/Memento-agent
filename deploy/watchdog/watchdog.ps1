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
# v1.0.28.21 : Stop-Agent attend reellement la mort du process (10 x 500 ms)
#              avant de laisser Start-Agent tourner. Sinon Stop-Process -Force
#              n'etant pas synchrone, on pouvait lancer un doublon pendant
#              que l'ancien process etait encore actif (bug Le confess
#              06/11/2026 : 2 MementoAgent.exe actifs, TPE serie + alertes.log
#              + reseau partages -> plus aucun heartbeat + PIN admin casse).
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


function Get-ProtectedMeiInfo {
    # v1.0.28.28 : identifie les _MEI qu'il ne faut JAMAIS supprimer.
    #
    # Bug corrige (Le confess 13/11/2026) : le cleanup supprimait le _MEI de
    # l'instance EN COURS des qu'il depassait 1 h. Or PyInstaller y garde
    # certifi\cacert.pem -> des sa suppression, requests leve
    # "OSError: Could not find a suitable TLS CA certificate bundle" et plus
    # aucun HTTPS ne marche : heartbeat, PIN admin, PATCH transactions, tout
    # casse jusqu'au prochain restart. L'ancien commentaire "l'instance en
    # cours est protegee" etait faux : son _MEI vieillit comme les autres.
    #
    # Deux protections :
    #   1. Noms des _MEI reellement charges par un process MementoAgent (lu
    #      dans ses modules). Precis mais peut echouer en Access Denied.
    #   2. StartTime du plus vieux agent actif : un _MEI cree APRES ce moment
    #      appartient forcement a un agent vivant. Filet de securite qui
    #      marche meme si (1) echoue.
    $names = @{}
    $oldestStart = $null
    try {
        foreach ($p in (Get-Process -Name $processName -ErrorAction SilentlyContinue)) {
            try {
                if ($null -eq $oldestStart -or $p.StartTime -lt $oldestStart) {
                    $oldestStart = $p.StartTime
                }
            } catch {}
            try {
                foreach ($m in $p.Modules) {
                    if ($m.FileName -match '\\(_MEI\d+)\\') { $names[$Matches[1]] = $true }
                }
            } catch {
                # Access denied sur .Modules : on se repliera sur $oldestStart
            }
        }
    } catch {}
    return @{ Names = $names; OldestStart = $oldestStart }
}


function Invoke-MeiCleanup {
    # Supprime les dossiers _MEI* orphelins (> meiMinAgeMinutes) dans %TEMP%.
    # Ne touche JAMAIS a un _MEI utilise par un agent en cours (cf.
    # Get-ProtectedMeiInfo).
    try {
        $temp = [IO.Path]::GetTempPath()
        $cutoff = (Get-Date).AddMinutes(-$meiMinAgeMinutes)
        $prot = Get-ProtectedMeiInfo
        $old = @(Get-ChildItem $temp -Directory -Force -Filter "_MEI*" -ErrorAction SilentlyContinue |
            Where-Object {
                $_.CreationTime -lt $cutoff -and
                -not $prot.Names.ContainsKey($_.Name) -and
                ($null -eq $prot.OldestStart -or $_.CreationTime -lt $prot.OldestStart)
            })
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
            $nbProt = $prot.Names.Count
            Write-WatchdogLog "_MEI cleanup: $n dossier(s) supprime(s), $nbProt protege(s) (libre: $freeGo Go)"
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
    # Retourne $true si l'agent est reellement mort (0 process restant),
    # $false s'il refuse de mourir apres toutes les tentatives.
    # Le caller NE DOIT PAS appeler Start-Agent si retour $false (sinon
    # on lance un doublon qui se marche dessus sur TPE serie, alertes.log,
    # reseau — bug observe sur Le confess 06/11/2026 : 2 MementoAgent.exe
    # actifs, l'un bloque depuis 441s CPU, l'autre fraichement relance).
    try {
        $procs = Get-Process -Name $processName -ErrorAction SilentlyContinue
        if (-not $procs) { return $true }
        Stop-Process -Name $processName -Force -ErrorAction SilentlyContinue
        Write-WatchdogLog "Agent kille (etait fige ou bloque)"
        # Attente active : jusqu'a 10 x 500 ms = 5 s max. Stop-Process -Force
        # n'est PAS synchrone : il envoie SIGTERM-equivalent et rend la main,
        # le process peut mettre plusieurs secondes a reellement s'arreter
        # (voire jamais, si bloque dans un appel DLL/kernel noninterruptible).
        for ($i = 1; $i -le 10; $i++) {
            Start-Sleep -Milliseconds 500
            $still = Get-Process -Name $processName -ErrorAction SilentlyContinue
            if (-not $still) {
                if ($i -gt 1) {
                    Write-WatchdogLog "Agent mort apres $($i * 500) ms"
                }
                return $true
            }
        }
        $pids = (Get-Process -Name $processName -ErrorAction SilentlyContinue | ForEach-Object { $_.Id }) -join ","
        Write-WatchdogLog "ALERTE: process survit au kill apres 5s (PIDs: $pids) — Start-Agent SKIPPED, intervention manuelle possiblement necessaire"
        return $false
    } catch {
        Write-WatchdogLog "Stop-Agent exception: $_"
        return $false
    }
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


Write-WatchdogLog "=== Watchdog v1.0.28.28 demarre (check ${checkIntervalSec}s, grace ${graceDelaySec}s, max ${maxRestartsPerHour} restarts/h) ==="
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
            if (Stop-Agent) {
                Start-Agent
            }
            # Si Stop-Agent retourne $false (process survit), on NE lance PAS
            # Start-Agent — le log d'alerte a deja ete emis. On retentera au
            # prochain tick du watchdog ; si le process reste zombi, on finit
            # par ouvrir le circuit breaker, ce qui est un signal correct.
        }
    } catch {
        Write-WatchdogLog "Boucle: exception $_"
    }
    Start-Sleep -Seconds $checkIntervalSec
}
