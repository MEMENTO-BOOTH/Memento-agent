# Script de publication d'une release Memento Agent.
#
# Usage : .\publier-release.ps1 [-Notes "Description des changements"]
#
# Branche dev   -> pre-release sur GitHub
# Branche prod  -> release normale (latest)
#
# Pre-requis : version.py a jour, .exe deja compile dans installer_output\
#
# Ce que fait le script :
#   1. Verifie qu'on est sur dev ou prod et que le working tree est propre
#   2. Lit la version dans version.py
#   3. Verifie que le tag v<version> n'existe pas deja
#   4. Verifie que installer_output\MementoAgent_Setup_<version>.exe existe
#   5. Cree le tag git, le push
#   6. Cree la release GitHub (--prerelease si dev) avec l'installeur en piece jointe

[CmdletBinding()]
param(
    [string]$Notes = ""
)

$ErrorActionPreference = "Stop"

# 1. Branche
$branch = (git rev-parse --abbrev-ref HEAD).Trim()
Write-Host "Branche : $branch"

if ($branch -ne "dev" -and $branch -ne "prod") {
    Write-Error "Ce script ne peut etre lance que depuis 'dev' ou 'prod' (branche actuelle : $branch)"
    exit 1
}

$prerelease = ($branch -eq "dev")
$channel = if ($prerelease) { "pre-release (canal dev)" } else { "release (canal prod)" }
Write-Host "Type    : $channel"

# Working tree propre ?
$dirty = git status --porcelain
if ($dirty) {
    Write-Warning "Le working tree n'est pas propre :"
    git status --short
    $confirm = Read-Host "Continuer quand meme ? (o/N)"
    if ($confirm -ne "o" -and $confirm -ne "O") {
        Write-Host "Abandon."
        exit 1
    }
}

# 2. Version depuis version.py
$versionLine = Get-Content "version.py" | Where-Object { $_ -match '^VERSION\s*=\s*"([^"]+)"' } | Select-Object -First 1
if (-not $versionLine) {
    Write-Error "Impossible de lire VERSION dans version.py"
    exit 1
}
$null = $versionLine -match '"([^"]+)"'
$version = $Matches[1]
$tag = "v$version"
Write-Host "Version : $version (tag : $tag)"

# 3. Tag deja existant ?
$tagExists = git ls-remote --tags origin $tag
if ($tagExists) {
    Write-Error "Le tag $tag existe deja sur origin. Bump VERSION dans version.py avant de relancer."
    exit 1
}

# 4. .exe present ?
$setupPath = "installer_output\MementoAgent_Setup_$version.exe"
if (-not (Test-Path $setupPath)) {
    Write-Error "Installeur introuvable : $setupPath. Compile-le d'abord (PyInstaller + Inno Setup)."
    exit 1
}
$sizeMB = [math]::Round((Get-Item $setupPath).Length / 1MB, 1)
Write-Host "Asset   : $setupPath ($sizeMB MB)"

# Confirmation finale
Write-Host ""
Write-Host "===== Recap ====="
Write-Host "  Branche : $branch"
Write-Host "  Version : $version"
Write-Host "  Tag     : $tag"
Write-Host "  Type    : $channel"
Write-Host "  Asset   : $setupPath"
if ($Notes) { Write-Host "  Notes   : $Notes" }
Write-Host ""
$confirm = Read-Host "Publier ? (o/N)"
if ($confirm -ne "o" -and $confirm -ne "O") {
    Write-Host "Abandon."
    exit 0
}

# 5. Tag git
Write-Host ""
Write-Host "Creation du tag $tag..."
git tag -a $tag -m "Release $tag depuis $branch"
git push origin $tag

# 6. Release GitHub
Write-Host "Creation de la release GitHub..."
if (-not $Notes) {
    $Notes = "Release $tag depuis la branche $branch."
}

$titleSuffix = if ($prerelease) { " (pre-release)" } else { "" }
$title = "Memento Agent $tag$titleSuffix"

$ghArgs = @(
    "release", "create", $tag,
    $setupPath,
    "--target", $branch,
    "--title", $title,
    "--notes", $Notes
)
if ($prerelease) {
    $ghArgs += "--prerelease"
}

& gh @ghArgs

if ($LASTEXITCODE -ne 0) {
    Write-Error "gh release create a echoue. Le tag $tag a ete cree et pushe — supprime-le si tu veux retenter (gh release delete $tag --yes; git push origin --delete $tag)."
    exit 1
}

Write-Host ""
Write-Host "OK : release $tag publiee ($channel)"
