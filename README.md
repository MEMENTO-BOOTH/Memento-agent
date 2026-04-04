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
- Imprimante deconnectee
- Camera deconnectee
- Crash dslrBooth, crash Cash Interface
- Disque bas / plein
- Borne hors ligne
- Coupe 2 pouces desactivee
- Resolution automatique par l'agent
- SMS via Twilio (webhook Supabase)

### E-memento
- Surveillance du log dslrBooth
- Generation de codes courts 7 caracteres (unicite verifiee dans Supabase)
- Expiration automatique apres 2 mois
- Generation d'image du code pour les templates dslrBooth
- Configuration apparence (taille, couleur, police) dans les parametres

### Drive Backup
- Copie automatique des photos vers Google Drive
- Detection de l'evenement dslrBooth actif
- Rattrapage des fichiers manquants au demarrage
- Structure : `G:\Mon Drive\dslrBooth\{nom_lieu} ({code})\{evenement}\`

### TPE (Terminal de Paiement)
- Affichage du chiffre d'affaires hebdomadaire (bar chart)
- Detail des transactions par jour (RESUMED, paiement, INHIBITED)
- Detection des impressions via log Cash Interface (keystroke P)
- Fichier `tpe.log` avec historique detaille

### Gestion des utilisateurs
- Authentification par code PIN (verifie dans Supabase table `utilisateurs`)
- Droits d'acces : admin (voit le CA) ou technicien (pas de CA)
- Le dashboard s'adapte aux droits de l'utilisateur connecte

### Mise a jour automatique
- Verification toutes les 6 heures
- Telechargement et installation silencieuse
- Publication via Supabase Storage + table `updates`

### Interface
- Design shadcn sobre (police Satoshi)
- System tray (tourne en arriere-plan)
- Ecran de rupture plein ecran (alerte critique)
- Toast notifications
- HoverCards sur les cartes du dashboard
- Scroll tactile
- Redimensionnable (s'adapte a l'ecran)

## Structure

```
main.py                     Point d'entree
version.py                  Version (1.0.0)
paths.py                    Chemins + registre Windows
dashboard.py                Dashboard principal
supabase_client.py          API Supabase
activity_logger.py          Logger (alertes.log + tpe.log)
user_session.py             Session utilisateur + droits
ui_components.py            Toast, HoverCard, Tooltip
rupture_screen.py           Ecran de rupture plein ecran
touch_scroll.py             Scroll tactile
TPE.py                      Page Terminal de Paiement

alertes/                    Page Alertes
  alertes_widget.py         Widget principal
  activity_table.py         Tableau d'activite (logs + alertes)
  stat_cards.py             Cartes statistiques
  table.py                  Table des alertes
  data.py                   Donnees + icones
  filter_bar.py             Filtres
  filters.py                Logique de filtrage
  stats.py                  Calcul stats

auth/                       Authentification
  lock_screen.py            Ecran PIN

monitoring/                 Monitoring
  engine.py                 Moteur principal (QThread)
  emmento.py                Watcher e-memento
  drive_backup.py           Backup Google Drive
  cashinterface.py          Watcher paiements
  alertes/                  Detection d'alertes
    alertes_monitor.py      Creation/resolution
    constants.py            Codes imprimante, seuils
  collectors/               Collecte de donnees
    heartbeat.py            Envoi heartbeat
    printer.py              Lecture imprimante DNP
    system.py               WiFi, disque, processus
  coupe_2pouces/            Gestion coupe 2 pouces
    coupe.py                API publique
    activer_coupe_2pouces.py
    desactiver_coupe_2pouces.py

settings/                   Page Parametres
  settings_widget.py        Widget principal
  config.py                 Config locale (registre)
  widgets.py                Widgets partages
  worker.py                 Worker API
  sections/                 Sections
  overlays/                 Popups

setup/                      Premier lancement
  config_page.py            Configuration initiale
  setup_window.py
  install_page.py
  progress_page.py
  styles.py

assets/                     Icones, polices, images
```

## Prerequis

- Windows 10/11
- Python 3.12+ (pour le developpement)
- PyInstaller (compilation)
- Inno Setup 6 (installeur)
- Supabase (base de donnees)

## Configuration

Copier `.env.example` en `.env` et renseigner :
```
SUPABASE_URL=https://votre-projet.supabase.co
SUPABASE_KEY=votre-cle-supabase
```

## Compilation

```bash
python -m PyInstaller MementoAgent.spec --clean --noconfirm
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

Le setup est genere dans `installer_output/`.

## Publication d'une mise a jour

1. Incrementer la version dans `version.py` et `installer.iss`
2. Compiler (voir ci-dessus)
3. Uploader le `.exe` dans Supabase Storage (bucket `updates`)
4. Inserer une ligne dans la table `updates` (version, fichier_url, notes)
5. Les bornes se mettent a jour automatiquement

## Base de donnees

Tables Supabase utilisees :
- `bornes` : identification des bornes
- `heartbeats` : etat en temps reel
- `alertes` : alertes creees/resolues
- `horaires` : horaires d'ouverture
- `transactions` : paiements TPE (via Lambda AWS)
- `ememento` : sessions photo + codes
- `utilisateurs` : authentification + droits
- `alerte_destinataires` : contacts SMS
- `updates` : mises a jour
- `partenaires` : bars/etablissements

## Licence

Propriete de Memento Booth.
