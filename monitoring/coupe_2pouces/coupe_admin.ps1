
$ErrorActionPreference = "SilentlyContinue"
$printerName = "DP-DS620"
$regPath = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Print\Printers\$printerName"
$targetByte = 0
$logFile = "C:/Users/MementoKiosk/Desktop/mementoagent/mementoagent/monitoring/coupe_2pouces/coupe.log"

function Log($msg) { Add-Content -Path $logFile -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [PS-ADMIN] $msg" }

# Arreter le spooler
Log "Arret spooler..."
Stop-Service -Name Spooler -Force
Start-Sleep -Seconds 1

# Modifier HKLM Default DevMode
try {
    $dm = (Get-ItemProperty -Path $regPath -Name "Default DevMode")."Default DevMode"
    if ($dm -and $dm.Length -gt 282) {
        $dm[282] = $targetByte
        # Modifier section SMTJ si presente
        $smtjText = [System.Text.Encoding]::ASCII.GetString($dm)
        if ($smtjText -match "CUT_2INCH") {
            $oldBytes = [System.Text.Encoding]::ASCII.GetBytes("CUT_2INCH")
            $newBytes = [System.Text.Encoding]::ASCII.GetBytes("CUT_STANDARD")
            $str = [System.Text.Encoding]::ASCII.GetString($dm)
            $idx = $str.IndexOf("CUT_2INCH")
            if ($idx -ge 0) {
                # Remplacer les bytes directement
                for ($i = 0; $i -lt $newBytes.Length; $i++) {
                    $dm[$idx + $i] = $newBytes[$i]
                }
                # Si le nouveau est plus court, remplir avec des zeros
                for ($i = $newBytes.Length; $i -lt $oldBytes.Length; $i++) {
                    $dm[$idx + $i] = 0
                }
            }
        }
        Set-ItemProperty -Path $regPath -Name "Default DevMode" -Value $dm -Type Binary
        Log "HKLM: byte 282 = $targetByte, SMTJ = CUT_STANDARD"
    } else {
        Log "HKLM: DEVMODE trop court ou introuvable"
    }
} catch {
    Log "HKLM erreur: $_"
}

# Modifier HKU (per-user DevMode)
$profilesReg = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList"
Get-ChildItem $profilesReg | ForEach-Object {
    $sid = $_.PSChildName
    if ($sid.Length -lt 20) { return }
    $hkuPath = "Registry::HKEY_USERS\$sid\Printers\DevModePerUser"
    try {
        $dmUser = (Get-ItemProperty -Path $hkuPath -Name $printerName -ErrorAction Stop).$printerName
        if ($dmUser -and $dmUser.Length -gt 282) {
            $dmUser[282] = $targetByte
            $str = [System.Text.Encoding]::ASCII.GetString($dmUser)
            $idx = $str.IndexOf("CUT_2INCH")
            if ($idx -ge 0) {
                $newBytes = [System.Text.Encoding]::ASCII.GetBytes("CUT_STANDARD")
                $oldBytes = [System.Text.Encoding]::ASCII.GetBytes("CUT_2INCH")
                for ($i = 0; $i -lt $newBytes.Length; $i++) {
                    $dmUser[$idx + $i] = $newBytes[$i]
                }
                for ($i = $newBytes.Length; $i -lt $oldBytes.Length; $i++) {
                    $dmUser[$idx + $i] = 0
                }
            }
            Set-ItemProperty -Path $hkuPath -Name $printerName -Value $dmUser -Type Binary
            Log "HKU ($sid): byte 282 = $targetByte"
        }
    } catch { }
}

# Redemarrer le spooler
Log "Redemarrage spooler..."
Start-Service -Name Spooler
Start-Sleep -Seconds 1
Log "Termine."
