# Memento Agent

Application de monitoring pour les bornes Memento Booth. Tourne en arriere-plan sur chaque borne Windows et supervise l'ensemble du systeme photobooth.

## Fonctionnalites

### Monitoring
- Surveillance de l'imprimante DNP DS620 (statut, feuilles restantes, mode coupe)
- Detection des processus dslrBooth et Cash Interface
- Monitoring WiFi, espace disque, camera
- Heartbeat toutes les 60 secondes vers Supabase

### Alertes
- Capot ouvert, bourrage papier, fin de papier, fin de ruban
- Bac a dechets plein, surchauffe, erreur mecanique
- Imprimante deconnectee, camera deconnectee
- Crash dslrBooth, crash Cash Interface
- Disque bas / plein, borne hors ligne
- Coupe 2 pouces desactivee
- Resolution automatique par l'agent
- SMS via Twilio (webhook Supabase)
- Deux niveaux : critique (rouge, page de rupture) et warning (orange, pas de blocage)

### E-memento
- Surveillance du log dslrBooth
- Generation de codes courts 7 caracteres (unicite verifiee dans Supabase)
- Expiration automatique apres 2 mois
- Configuration apparence (taille, couleur, police) dans les parametres

### Drive Backup
- Copie automatique des photos vers Google Drive
- Detection de l'evenement dslrBooth actif
- Rattrapage des fichiers manquants au demarrage

### TPE (Terminal de Paiement)
- Affichage du chiffre d'affaires hebdomadaire (bar chart)
- Detail des transactions par jour
- Fichier tpe.log avec historique detaille

### Gestion des utilisateurs
- Authentification par code PIN (verifie dans Supabase table utilisateurs)
- Droits d'acces : admin (voit le CA) ou technicien (pas de CA)

### Interface
- Design shadcn (police Satoshi, contours 1.7px)
- System tray (tourne en arriere-plan quand on ferme la fenetre)
- Ecran de rupture plein ecran avec pave numerique tactile
- Scroll tactile pour ecrans tactiles

## Branches

- **prod** : version stable qui tourne sur les bornes (publie une *release* GitHub)
- **dev** : developpement et tests (publie une *pre-release* GitHub)
- **main** : copie de secours de prod

Le canal de mise a jour est determine par la branche depuis laquelle le workflow de release est lance :

| Branche | Type publie sur GitHub | Recu par les bornes prod ? |
|---------|------------------------|----------------------------|
| `prod`  | release               | oui (via `/releases/latest`) |
| `dev`   | pre-release           | non (les pre-releases sont ignorees par `/releases/latest`) |

## Prerequis

- Windows 10/11
- Python 3.12+ (pour le developpement)
- PyInstaller (compilation)
- Inno Setup 6 (installeur)
- Supabase (base de donnees + storage)

## Configuration

Copier .env.example en .env et renseigner :

```
SUPABASE_URL=https://votre-projet.supabase.co
SUPABASE_KEY=votre-cle-supabase
```

## Compilation

```powershell
python -m PyInstaller MementoAgent.spec --clean --noconfirm
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

Le setup est genere dans `installer_output\MementoAgent_Setup_<version>.exe`. La version dans [installer.iss](installer.iss) est lue automatiquement depuis [version.py](version.py) via le preprocesseur Inno Setup — pas besoin de la modifier.

## Publier une mise a jour

Le build se fait **localement** (PyInstaller + Inno Setup). La publication sur GitHub Releases (avec le bon flag prerelease/release selon la branche) est automatisee par le script [publier-release.ps1](publier-release.ps1).

### Pre-requis

1. Bump la version dans [version.py](version.py).
2. Commit et push le bump sur la branche cible (`dev` ou `prod`).
3. Compiler en local (voir section *Compilation* ci-dessus).
4. Verifier que `installer_output\MementoAgent_Setup_<version>.exe` existe.

### Publier une PRE-RELEASE (canal dev)

Depuis la branche `dev` :

```powershell
git checkout dev
git pull
# (... bump version.py, commit, push, compile ...)
.\publier-release.ps1 -Notes "Description des changements"
```

Resultat : tag `v<version>` cree sur `dev`, installeur attache, **prerelease = true** (badge "Pre-release" sur GitHub).

### Publier une RELEASE (canal prod)

Depuis la branche `prod`. En general on merge `dev` -> `prod` apres validation des pre-releases :

```powershell
git checkout prod
git merge dev          # ou cherry-pick les commits voulus
git push
# (... compile ...)
.\publier-release.ps1 -Notes "Description des changements"
```

Resultat : tag `v<version>` cree sur `prod`, installeur attache, **prerelease = false** -> badge "Latest", visible par toutes les bornes prod a leur prochaine verification (toutes les 6 heures).

### Ce que fait le script

1. Verifie qu'on est sur `dev` ou `prod` (rejette les autres branches)
2. Verifie que le working tree est propre (warning sinon, demande confirmation)
3. Lit la version dans `version.py`
4. Verifie que le tag `v<version>` n'existe pas deja sur origin
5. Verifie que `installer_output\MementoAgent_Setup_<version>.exe` est present
6. Affiche un recap et demande confirmation avant de publier
7. Cree le tag git, le push
8. Cree la release GitHub avec l'installeur en piece jointe (`--prerelease` si lance depuis `dev`)

### Verifier que ca a marche

- Onglet **Releases** sur GitHub :
  - Depuis `dev` -> badge **Pre-release** sur la release
  - Depuis `prod` -> badge **Latest**
- L'asset attache doit etre `MementoAgent_Setup_<version>.exe`
- Sur une borne prod : *Parametres -> Mise a jour -> Verifier* doit detecter la nouvelle version (uniquement pour les releases prod, pas les pre-releases)

## Base de donnees

Tables Supabase :

| Table | Description |
|-------|------------|
| bornes | Identification des bornes (hostname, nom du lieu, ville) |
| heartbeats | Etat en temps reel de chaque borne |
| alertes | Alertes creees et resolues |
| horaires | Horaires d'ouverture par jour |
| transactions | Paiements TPE |
| ememento | Sessions photo et codes generes |
| utilisateurs | Authentification par PIN et droits |
| alerte_destinataires | Contacts SMS par borne |
| updates | Mises a jour publiees (version, URL, notes) |
| config | Configuration globale (cles, tokens) |
| partenaires | Bars et etablissements |

Supabase Storage :

| Bucket | Description |
|--------|------------|
| updates | Fichiers .exe des mises a jour (3 dernieres versions) |
| logos | Logos des bornes |

## Structure du projet

```
main.py                     Point d'entree
version.py                  Version courante
dashboard.py                Dashboard principal
supabase_client.py          API Supabase
activity_logger.py          Logger (alertes.log + tpe.log)
rupture_screen.py           Ecran de rupture plein ecran
TPE.py                      Page Terminal de Paiement

monitoring/
  engine.py                 Moteur principal (QThread, cycle 60s)
  emmento.py                Watcher e-memento
  drive_backup.py           Backup Google Drive
  cashinterface.py          Watcher paiements
  alertes/
    alertes_monitor.py      Detection et resolution des alertes
    constants.py            Codes imprimante DNP, seuils
  collectors/
    printer.py              Lecture imprimante DNP DS620
    heartbeat.py            Envoi heartbeat Supabase
    system.py               WiFi, disque, processus

alertes/                    Page Alertes (UI)
auth/                       Ecran PIN
settings/                   Page Parametres
setup/                      Premier lancement (configuration initiale)
assets/                     Icones Feather, polices Satoshi, images

publier-release.ps1         Script de publication d'une release/pre-release sur GitHub
```

## Licence

Propriete de Memento Booth.
