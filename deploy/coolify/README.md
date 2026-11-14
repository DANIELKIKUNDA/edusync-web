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

### Essai réel de la pile complète, sans aucune donnée réelle

```bash
python tools/local/coolify_stack_e2e.py <SHA des images>
```

Ce script démarre la pile comme Coolify, simule Traefik, vérifie tout, puis supprime la pile.

Résultat du 14/11/2026, avec les images du commit `a96a518` construites localement, sur un Docker de 2,9 Go :
**25/25 vérifications réussies**.
- **Démarrage :** 144 s.
- **Fonctionnement :**
  - secrets et migrations sans erreur, rôles sans contournement du RLS ;
  - l'API ne voit pas le mot de passe propriétaire ;
  - HSTS est envoyé une seule fois, et la vraie adresse du client est vue par l'API ;
  - la sauvegarde est faite et sa restauration vérifiée ;
  - le second déploiement réussit et laisse les secrets inchangés.
- **Mémoire au repos :** 565 Mio.
- **Premier démarrage :** la création du premier Manager Système est disponible, avec jeton obligatoire.

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
- La configuration de la supervision (§9) : canaux Coolify, Healthchecks.io, UptimeRobot, puis la liste du §9.5.
- La reprise des données d'une école réelle (APN) : d'abord en local, puis sur le staging, et en production seulement
  après validation.

## 9. Supervision de la production (14/11/2026)

Objectif : être prévenu d'une panne, d'une saturation ou d'une sauvegarde manquée, **même quand le serveur lui-même
est hors service**, sans alourdir un VPS de 4 Go. Aucun Prometheus, Grafana ni Loki n'est installé sur le serveur :
ils consommeraient à eux seuls 0,5 à 1 Go de mémoire.

La supervision repose sur trois couches. Les deux premières sont sur le serveur, la troisième est indépendante.

| Couche | Où | Ce qu'elle voit | Qui est prévenu, et comment |
|---|---|---|---|
| 1. Coolify (natif) | sur le serveur | CPU et mémoire (historique), disque, conteneurs arrêtés ou redémarrés, déploiements | notifications Coolify (Telegram ou e-mail) |
| 2. EduSync, État du service | dans l'API | base de données, Redis, workers, stockage, erreurs serveur, messagerie, sauvegarde, **Ressources du serveur** (mémoire, disque, charge) | e-mail aux Managers Système après 5 min de panne (nécessite SMTP, §6) |
| 3. Externe | hors du serveur | serveur ou réseau injoignable, API arrêtée, panne de la couche 2, sauvegarde absente, certificat | Healthchecks.io et UptimeRobot : e-mail et Telegram, **indépendants du serveur** |

### 9.1 Couche 1 — Coolify (aucune ressource en plus)

1. **Servers › (le serveur) › Sentinel** :
   - activez Sentinel, puis **Metrics** ;
   - historique : **7 jours**, le compromis entre l'utilité et le disque.

   Vous obtenez les courbes CPU et mémoire du serveur et de chaque conteneur.
2. **Servers › (le serveur) › Configuration** : seuil d'alerte disque à **80 %**.
3. **Notifications** : créez un canal **Telegram** (un bot et votre conversation), ou **E-mail** (SMTP). Cochez au
   minimum les événements suivants :
   - **Server Disk Usage** ;
   - **Container Status Changes** (conteneur arrêté, redémarré ou bloqué en redémarrage) ;
   - **Server Unreachable / Reachable** ;
   - **Deployment Failed**.

   Puis cliquez sur **Send test notification**.
4. **Limite de Coolify** : il tourne sur le même serveur. Si le serveur s'arrête, Coolify se tait aussi. C'est le rôle de
   la couche 3.

Coolify n'alerte pas sur la saturation de la mémoire ni du processeur : la couche 2 le fait.

### 9.2 Couche 2 — EduSync (État du service)

- **Nouveau composant « Ressources du serveur »** : il mesure la mémoire, le disque et la charge du processeur depuis
  l'API (lecture de `/proc` et du disque, sans agent supplémentaire).

  | Mesure | Attention | Critique |
  |---|---|---|
  | Mémoire utilisée | 85 % | 95 % |
  | Disque | 80 % | 90 % |
  | Charge sur 5 min, par cœur | 1,5 | 3 |

  Un état critique qui dure plus de 5 minutes ouvre un incident, comme les autres composants. Les seuils se changent
  avec les variables `EDUSYNC_HOST_*` : `EDUSYNC_HOST_MEMORY_CRITICAL_PERCENT`, `EDUSYNC_HOST_DISK_CRITICAL_PERCENT`, etc.
- **E-mails d'incident** : ils partent par la messagerie de l'application. **Sans SMTP configuré (§6), aucun e-mail
  ne part.** Configurez SMTP avant l'ouverture, ajoutez vos adresses dans État du service › Destinataires, puis
  utilisez **« Envoyer une alerte de test »**.
- **Alertes métier** (Vigie, alertes entre rôles : caisse, annulations, abandons, dérogations) :
  - elles arrivent toujours dans la cloche de l'application, sans aucun fournisseur ;
  - l'e-mail exige SMTP, la notification push exige FCM.

### 9.3 Couche 3 — Externe, indépendante du serveur

**Signaux de vie (Healthchecks.io, offre gratuite de 20 contrôles).** Créez deux contrôles dont le nom contient
« EduSync » :

| Contrôle | Période | Grâce | Variable Coolify | Envoyé par |
|---|---|---|---|---|
| EduSync production — santé | 5 min | 5 min | `EDUSYNC_HEARTBEAT_URL` | l'API, environ une fois par minute |
| EduSync production — sauvegarde | 1 jour | 3 h | `EDUSYNC_BACKUP_HEARTBEAT_URL` | le service `backup`, après chaque sauvegarde |

**Fonctionnement du contrôle « santé » :**
- tout va bien : un signal simple ;
- un composant est hors service depuis plus de 5 minutes : un signal **/fail**, avec la raison en clair (base de
  données injoignable, disque rempli à 92 %…) ;
- le serveur, le réseau ou l'API s'arrêtent : plus aucun signal, et Healthchecks.io alerte.

**Fonctionnement du contrôle « sauvegarde » :** un signal /start, puis un succès ou un /fail avec la raison. Aucun
signal pendant 1 jour et 3 heures déclenche une alerte.

**Réglages :**
- Dans Healthchecks.io › Integrations, branchez votre **e-mail** et **Telegram**. Ces messages partent de chez
  Healthchecks.io, jamais de votre serveur.
- Les adresses de signal ne donnent qu'un droit : envoyer un signal à ce contrôle. Coolify les rend visibles à tous les
  conteneurs (#7655) : risque faible, accepté. Si une adresse est exposée, recréez-la dans Healthchecks.io.

**Sondes HTTP (UptimeRobot, offre gratuite, toutes les 5 min).** Elles voient ce qu'un signal sortant ne voit pas :
DNS, Traefik, certificat, accès depuis Internet. Créez trois sondes :
- **mot-clé** sur `https://app.myeducsync.com/health-api` (mot attendu `ok`) ;
- **HTTP** sur `https://app.myeducsync.com/api/v1/setup/status` ;
- **certificat** sur `app.myeducsync.com` (alerte 14 jours avant l'expiration).

Alertes par e-mail et par l'application mobile ou Telegram.

### 9.4 Conservation des métriques et des journaux

| Donnée | Durée | Où |
|---|---|---|
| Journaux des conteneurs | 3 fichiers de 10 Mo par service, environ 300 Mo au maximum | serveur |
| Métriques CPU et mémoire | 7 jours | Coolify (Sentinel) |
| Incidents et erreurs serveur | historique (1 h / 24 h / 7 j) et incidents récents | État du service |
| Signaux de vie | 100 derniers par contrôle | Healthchecks.io |
| Sauvegardes | 7 jours en local, l'historique long hors serveur (§7) | serveur et stockage S3 |

Le contrôle `tools/ci/coolify_compose_check.py` refuse un service sans limite de journaux.

### 9.5 Avant l’ouverture de la première école (liste à cocher)

1. **Couche 1 :** dans Coolify, **Send test notification** arrive sur Telegram ou par e-mail. Les courbes Sentinel
   s'affichent. Le seuil disque est à 80 %.
2. **Couche 2 :**
   - SMTP est configuré ;
   - État du service › **Envoyer une alerte de test** arrive ;
   - « Ressources du serveur » affiche des chiffres réels.
3. **Couche 3, signaux de vie :**
   - les deux contrôles Healthchecks.io sont **verts** après le déploiement ;
   - pour le contrôle « sauvegarde », lancez une sauvegarde : terminal Coolify du service `backup`, puis
     `/bin/sh /usr/local/bin/edusync-backup once`.
4. **Couche 3, sondes HTTP :** les trois sondes UptimeRobot sont vertes.
5. **Vérification automatique**, depuis votre ordinateur. Toutes les lignes doivent être PASS :

   ```bash
   HEALTHCHECKS_API_KEY=<clé en lecture seule> python tools/local/verify_production_monitoring.py --sha <SHA déployé>
   ```

6. **Essai de panne réel**, hors des heures d'ouverture, quand aucune école n'utilise l'application :
   - arrêtez le service `backend` dans Coolify pendant 12 minutes ;
   - vous devez recevoir l'alerte Coolify (conteneur arrêté), Healthchecks.io (« santé » en panne) et UptimeRobot ;
   - redémarrez-le : les trois annoncent la résolution.
7. **Alertes métier**, dans l'école de démonstration :
   - annulez un reçu de test, ou clôturez une caisse avec un écart ;
   - le promoteur et le gestionnaire voient l'alerte dans la cloche (et par e-mail ou push si configurés).

Notez la date et le résultat de chaque point. Tant qu'un point échoue, l'école n'ouvre pas.
