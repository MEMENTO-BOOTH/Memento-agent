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

- **prod** : version stable qui tourne sur les bornes, les mises a jour sont publiees ici
- **main** : copie de secours de prod
- **dev** : developpement et tests

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

```bash
python -m PyInstaller MementoAgent.spec --clean --noconfirm
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

Le setup est genere dans installer_output/.

## Publier une mise a jour

Quand le code est pret et compile, il suffit d'une seule commande :

```bash
gh release create v1.0.1 installer_output/MementoAgent_Setup_1.0.1.exe --title "Version 1.0.1" --notes "Description des changements" --target prod
```

C'est tout. Le reste est automatique :

1. Le GitHub Action se declenche
2. Il telecharge le .exe depuis la release GitHub
3. Il uploade le .exe dans Supabase Storage (bucket updates)
4. Il insere une ligne dans la table updates avec l'URL Supabase
5. Il supprime les anciennes versions dans le bucket (garde les 3 dernieres)
6. Les bornes detectent la nouvelle version lors de leur verification (toutes les 6 heures)
7. Elles telechargent le .exe depuis Supabase Storage et l'installent en mode silencieux

Les releases et les .exe restent aussi sur GitHub pour archivage.

### Etapes detaillees pour publier

1. Changer la version dans version.py et installer.iss
2. Compiler avec PyInstaller puis Inno Setup (voir section Compilation)
3. Commit et push sur prod
4. Lancer la commande gh release create (voir ci-dessus)
5. Verifier que le GitHub Action a reussi dans l'onglet Actions du repo

### Verifier que ca a marche

- Onglet Actions sur GitHub : le workflow doit etre en "success"
- Table updates dans Supabase : la nouvelle version doit apparaitre avec une URL Supabase Storage
- Bucket updates dans Supabase Storage : le .exe doit etre present

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

.github/workflows/
  update-supabase-on-release.yml   GitHub Action qui automatise les mises a jour
```

## Licence

Propriete de Memento Booth.
