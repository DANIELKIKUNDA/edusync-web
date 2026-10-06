# Lanceur local EduSync (poste du propriétaire)

Démarre tout EduSync sur ce poste en un double-clic, sans doublon, puis ouvre l'application.

## Installation des raccourcis (une fois)

```powershell
powershell -ExecutionPolicy Bypass -File tools\local\install_shortcuts.ps1
```

Crée sur le bureau, avec le logo EduSync :

| Raccourci | Effet |
|---|---|
| **EduSync** | Vérifie les composants, démarre ce qui manque, attend que tout réponde, ouvre `http://localhost:5180/` |
| **Arrêter EduSync** | Arrête proprement interface, serveur, tâches de fond, stockage, Redis et base (données conservées) |
| **Journaux EduSync** | Ouvre le dossier des journaux (`.local/logs`) |

## Ce qui est démarré (dans cet ordre)

| Service | Port (local uniquement) | Détail |
|---|---|---|
| PostgreSQL 16 (instance isolée) | 55432 | `.local/postgres-certification` — jamais le service PostgreSQL de la machine (5432) |
| Redis (dans WSL Ubuntu) | 16379 | configuration privée, mot de passe, adresse locale |
| Stockage des documents S3 (SeaweedFS) | 18333 | bucket privé `.local/s3/data` |
| Serveur EduSync (API) | 58100 | `/health` attendu avant de continuer |
| Tâches de fond | — | diffusion des événements (outbox) et envoi SMS (fournisseur de démonstration) |
| Interface (build de production) | 5180 | API servie sur la même origine |

Un service qui répond déjà est réutilisé : relancer le raccourci ne crée jamais de doublon.

## Environnements

```text
tools\local\EduSync-Demarrer.cmd                  environnement de démonstration (par défaut)
tools\local\EduSync-Demarrer.cmd --profile blank  installation vierge (création du premier Manager Système)
```

- **demo** : base `edusync_claude_fresh` (écoles et comptes de recette existants).
- **blank** : base `edusync_closure_blank` ; la page de connexion propose « Créer le Manager Système » une seule fois.

Passer d'un environnement à l'autre arrête puis relance le serveur ; aucune donnée n'est supprimée.
Pour repartir d'une base vierge neuve : arrêter EduSync, supprimer la base `edusync_closure_blank`
(procédure dans le rapport de clôture), relancer avec `--profile blank`.

## Comptes de recette

`python tools/local/recette_accounts.py` écrit la fiche privée `.local/RECETTE_COMPTES.md`
(URL, codes d'établissement, comptes, rôles, mots de passe de test). Elle n'est jamais versionnée.

## Prérequis vérifiés au démarrage

`.venv` Python, Node.js, WSL (Ubuntu-22.04 avec `redis-server`), PostgreSQL 16 (`C:\Program Files\PostgreSQL\16\bin`),
`.local/s3/bin/weed.exe`, configuration privée `.local/certification.env`. L'interface est construite automatiquement
si `frontend/dist` n'existe pas.
