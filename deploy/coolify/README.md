# EduSync en production sur Coolify — app.myeducsync.com

Fichiers :
- `docker-compose.coolify.yml` (racine du dépôt) ;
- dans l'image backend : `backend/scripts/coolify_secrets.py` (génère les secrets) et `backend/scripts/coolify_run.py`
  (démarre chaque service avec ses seuls secrets) ;
- dans l'image frontend : `frontend/nginx.production.conf` ;
- dans l'image de sauvegarde : `deploy/backup/backup.sh`, qui lit ses secrets depuis des fichiers (`*_FILE`).
Serveur visé : VPS AMD64 de 4 Go, adresse 46.62.227.155, Coolify 4.4.6.

Le staging n'est pas concerné. Il continue avec `docker-compose.yml`, `deploy/staging/` et son contrôleur à privilèges
limités. Ce dossier ne les modifie pas.

Contrôle automatique de la configuration, avant chaque mise en production :

```bash
python tools/ci/coolify_compose_check.py --render
```

Le fichier est lisible tel quel par Coolify 4.4.6 :
- aucune ancre YAML, aucun champ `x-` ;
- aucun `$` dans les commandes, que Coolify pourrait interpréter ;
- aucun fichier monté depuis le dépôt : l'option « Preserve repository » n'est **pas** nécessaire ;
- la seule clé propre à Coolify est `exclude_from_hc`, sur les deux tâches ponctuelles.

## 1. Ce que fait ce Compose (audit du 12/11/2026)

| Sujet | Problème du Compose générique avec Coolify | Choix en production |
|---|---|---|
| Compilation | `build:` compile sur le VPS (npm, pip) : trop lourd pour 4 Go, et non certifié | Images de la CI seulement : `ghcr.io/danielkikunda/edusync-*` au SHA validé, infrastructure épinglée par empreinte (les mêmes que le staging) |
| Variables « required » | 9 variables `:?` (dont 4 URL de base de données à recopier à la main) : Coolify bloque tant qu'elles sont vides, et l'opérateur doit inventer des valeurs | Une seule variable obligatoire : `EDUSYNC_RELEASE_SHA` |
| Secrets dans `.env` | Coolify v4 injecte **toutes** les variables de la ressource dans **tous** les conteneurs ([coollabsio/coolify#7655](https://github.com/coollabsio/coolify/issues/7655), correction prévue seulement en v5) ; `env_file: .env` donnait aussi le mot de passe propriétaire au migrateur | Aucun secret généré dans Coolify : le service `secrets-init` les crée une fois dans deux volumes, `secrets_owner` et `secrets_app` ; chaque service ne lit que les siens |
| Mot de passe propriétaire PostgreSQL | Visible de l'API | Monté seulement pour `postgres`, `migrator` et `backup` ; jamais pour l'API ni les workers |
| Migrations et rôles | Mêmes scripts que le staging | `migrator` crée ou met à jour les rôles `edusync_tenant`, `edusync_platform` et `edusync_worker` (moindre privilège, sans contournement du RLS), applique les migrations, puis s'arrête. L'API attend sa réussite |
| HTTPS, Traefik et Caddy | Caddy (`tls-proxy`) voulait les ports 80 et 443, déjà pris par Traefik | Pas de Caddy. Traefik termine le HTTPS. Aucun port publié |
| Adresse IP des utilisateurs | IP fixes 172.30.57.x : avec Traefik devant nginx, tous les utilisateurs auraient eu l'adresse de Traefik, et le blocage anti-force brute aurait bloqué tout le monde | `FORWARDED_ALLOW_IPS` = réseaux Docker privés : uvicorn retient la vraie adresse du client |
| CORS, hôtes, HSTS | `http://localhost` par défaut. HSTS fourni par Caddy | `https://app.myeducsync.com` partout. nginx de production : HSTS, schéma `https` relayé à l'API, flux temps réel sans tampon |
| Disque | Journaux Docker sans limite. 14 jours de sauvegardes locales | 3 fichiers de 10 Mo par service. 7 jours en local. L'historique long va hors serveur (§7) |

Mémoire : `WEB_CONCURRENCY=2` (2 processus API), adapté à 4 Go. Aucune limite stricte n'est posée : on surveille avant
d'en ajouter.

## 2. Préparer (une fois)

1. **DNS** : un enregistrement `A` pour `app.myeducsync.com` vers `46.62.227.155`.
2. **Registre d'images** : les images `ghcr.io/danielkikunda/edusync-*` sont **privées**.
   - Créez un jeton GitHub limité à `read:packages` (lecture seule, sans autre droit).
   - Enregistrez-le dans Coolify, ou sur le serveur avec `docker login ghcr.io`. Il ne va jamais dans le dépôt.
3. **Coolify** : créez une **Application** de type **Docker Compose** depuis le dépôt `DANIELKIKUNDA/edusync-web`.
   - Branche : `main`.
   - **Docker Compose Location** : `/docker-compose.coolify.yml`.
   - Inutile de cocher **Preserve repository during deployment** : aucun fichier du dépôt n'est monté.
   - Les images doivent être celles d'un commit de `main` : la CI ne publie les images qu'après une fusion.
4. **Domaine** : dans **Domains**, attachez `https://app.myeducsync.com` au service **frontend**, port **80**. Laissez
   les autres services sans domaine.

## 3. Variables dans Coolify

| Variable | Valeur |
|---|---|
| `EDUSYNC_RELEASE_SHA` | **obligatoire** : SHA complet autorisé par `python tools/ci/production_release_gate.py <SHA>` (CI, déploiement staging et E2E staging réussis) |
| `SERVICE_PASSWORD_64_SETUPTOKEN` | générée par Coolify : jeton du premier Manager Système (§5) |
| `EDUSYNC_DOMAIN` | facultative, `app.myeducsync.com` par défaut |
| `EDUSYNC_BACKUP_OFFSITE` et `EDUSYNC_BACKUP_OFFSITE_*` | copie hors serveur (§7), fortement conseillée |
| Messagerie (`EDUSYNC_EMAIL_PROVIDER`, `EDUSYNC_SMTP_*`, `EDUSYNC_PUSH_PROVIDER`, `EDUSYNC_FCM_*`, `EDUSYNC_SMS_PROVIDER`, `EDUSYNC_ORANGE_SMS_*`) | désactivée par défaut (§6) |

Ne saisissez **aucune** URL de base de données, aucun secret JWT ni aucune clé MFA : `secrets-init` les génère.

## 4. Mettre en production une version

1. Vérifiez la version : `python tools/ci/production_release_gate.py <SHA>`. Si elle est refusée, n'allez pas plus
   loin.
2. Dans Coolify, `EDUSYNC_RELEASE_SHA = <SHA>`, puis **Deploy**.
3. Ordre de démarrage :
   - `secrets-init` (secrets présents) ;
   - `postgres` ;
   - `migrator` (migrations, puis arrêt) ;
   - `backend` (santé `/health`), les workers et `frontend` ;
   - `backup`.
4. Contrôles :
   - `https://app.myeducsync.com/version.json` affiche le bon SHA ;
   - la connexion fonctionne ;
   - l'écran Plateforme › Santé est vert, et la sauvegarde y apparaît après le premier passage.

**Retour arrière** : remettez le SHA précédent et redéployez. Les migrations ne reviennent pas en arrière : un retour
arrière n'est sûr que si aucune migration n'est arrivée entre les deux versions. Sinon, restaurez la sauvegarde
(`docs/architecture/RUNBOOK_INCIDENT.md` §5) avant de redéployer.

## 5. Premier démarrage : le premier Manager Système

1. Ouvrez `https://app.myeducsync.com`, puis la page de création du premier Manager Système.
2. Saisissez le jeton : la valeur de `SERVICE_PASSWORD_64_SETUPTOKEN` dans Coolify.
3. Activez le second facteur (TOTP), obligatoire pour la plateforme.
4. Le jeton ne sert plus dès qu'un manager existe.

## 6. Messagerie (SMTP, FCM, SMS)

- **SMTP** : `EDUSYNC_EMAIL_PROVIDER=smtp`, `EDUSYNC_SMTP_HOST`, `EDUSYNC_SMTP_PORT` (587), `EDUSYNC_SMTP_SECURITY`
  (`starttls` ou `tls`), `EDUSYNC_SMTP_FROM_EMAIL`, `EDUSYNC_SMTP_USERNAME` et `EDUSYNC_SMTP_PASSWORD`. Sans
  chiffrement, l'API refuse de démarrer.
- **FCM (notifications push)** : `EDUSYNC_PUSH_PROVIDER=fcm`, puis la configuration web publique
  (`EDUSYNC_FCM_WEB_CONFIG_JSON`, `EDUSYNC_FCM_VAPID_PUBLIC_KEY`). Pour le compte de service, préférez un **fichier** :
  - montez-le sur le seul service `communications-worker` (Coolify › Persistent Storage › File Mount) ;
  - indiquez son chemin dans `EDUSYNC_FCM_SERVICE_ACCOUNT_FILE` ;
  - ne collez pas le JSON du compte de service dans une variable.
- **SMS Orange** : variables `EDUSYNC_ORANGE_SMS_*`.

**Risque résiduel à connaître** : les secrets des fournisseurs (mot de passe SMTP, secret Orange) sont des variables
Coolify, donc visibles par tous les conteneurs de la ressource (#7655). Limitez-les à des comptes dédiés à EduSync,
changez-les si un conteneur est compromis, et passez à Coolify v5 dès sa sortie.

## 7. Sauvegardes

- **Local, chaque nuit** : `pg_dump` et copie des documents, puis restauration d'essai dans une base isolée, avec
  l'état affiché dans Plateforme › Santé. 7 jours sont gardés sur le disque.
- **Hors serveur (indispensable)** : un stockage objet S3, par exemple Hetzner Object Storage :
  - `EDUSYNC_BACKUP_OFFSITE=offsite:edusync-backups/production` ;
  - `EDUSYNC_BACKUP_OFFSITE_ENDPOINT`, `EDUSYNC_BACKUP_OFFSITE_ACCESS_KEY` et `EDUSYNC_BACKUP_OFFSITE_SECRET_KEY`.
  - Vous pouvez y ajouter la sauvegarde du serveur entier chez l'hébergeur.
- **Les secrets eux-mêmes** : **conservez hors du serveur une copie de `mfa_key`** (volume `secrets_app`). Sans elle,
  les secrets TOTP chiffrés des comptes plateforme deviennent illisibles.
  - Commande, une seule fois, à lancer sur le serveur sans la copier dans un ticket ni dans un chat :
    `docker run --rm -v <ressource>_secrets_app:/s:ro alpine cat /s/mfa_key`.
  - Rangez la valeur dans le gestionnaire de mots de passe du propriétaire.
  - Gardez aussi le volume `secrets_owner` : sans lui, on ne peut plus se connecter à PostgreSQL avec le compte
    propriétaire. Une restauration depuis `pg_dump` dans un nouveau volume reste possible.

## 8. Ce qui reste manuel, et validé par le propriétaire

- La mise en production elle-même : choix du SHA, puis **Deploy** dans Coolify. Rien ne part automatiquement.
- La reprise des données d'une école réelle (APN) : d'abord en local, puis sur le staging, et en production seulement
  après validation.
