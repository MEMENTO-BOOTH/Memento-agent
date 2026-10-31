# smoke-test-release.ps1
#
# Lance l'exe PyInstaller compile dans dist\MementoAgent.exe avec le flag
# --smoke-test et verifie qu'il sort en code 0 (= les ecrans sensibles comme
# rupture_screen / lock_screen se construisent sans ModuleNotFoundError).
#
# A executer AVANT git tag + gh release. Attrape les regressions de packaging
# PyInstaller qui autrement ne se verraient qu'en prod (incident O divin
# Bethune 30/10 : PyQt5.QtSvg manquait du build v1.0.28.18, boucle de 248
# crashs sur rupture_screen pendant 4h22).
#
# Usage :
#   .\scripts\smoke-test-release.ps1
# Exit 0 = OK, Exit 1 = FAIL (ne pas releaser).

$ErrorActionPreference = "Stop"

$exe = Join-Path $PSScriptRoot "..\dist\MementoAgent.exe"
if (-not (Test-Path $exe)) {
    Write-Host "KO : exe absent ($exe). Build d'abord : python -m PyInstaller MementoAgent.spec --clean --noconfirm" -ForegroundColor Red
    exit 1
}

Write-Host "Lancement smoke-test sur $exe"
# System.Diagnostics.Process pour recuperer ExitCode de maniere fiable
# (Start-Process -NoNewWindow retournait ExitCode vide ici).
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $exe
$psi.Arguments = "--smoke-test"
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.CreateNoWindow = $false
$p = [System.Diagnostics.Process]::Start($psi)
if (-not $p.WaitForExit(30000)) {
    try { $p.Kill() } catch {}
    Write-Host "KO : timeout 30s" -ForegroundColor Red
    exit 1
}
$stdout = $p.StandardOutput.ReadToEnd()
$stderr = $p.StandardError.ReadToEnd()
$code = $p.ExitCode

if ($code -eq 0) {
    Write-Host "OK : $stdout" -ForegroundColor Green
    exit 0
}
Write-Host "KO exit=$code" -ForegroundColor Red
Write-Host "stdout: $stdout"
Write-Host "stderr: $stderr"
exit 1
