# EduSync — Handoff staging pour Codex

Clôture locale du 2026-10-17. Ce document suffit pour déployer le staging sans redemander l'architecture.
Il ne contient **aucune valeur secrète**.

## 1. Référence de déploiement

| Élément | Valeur |
|---|---|
| Dépôt | `https://github.com/DANIELKIKUNDA/edusync-web` |
| Branche | `main` |
| SHA de code certifié | **`2ad66ef309cf16a614d96ca20307254d2fc5a8b1`** (`2ad66ef`) |
| Tag officiel (immuable) | **`edusync-local-certified-2026-10-17`** → `2ad66ef` |
| Commit de preuves | `f86d4a1` (manifeste, preuves JSON, captures PNG, rapport ; aucun code) |
| Certification | N0 / N1 / N2 / N3 + messagerie externe : **47 / 47 PASS**, arbre propre au démarrage (`CERTIFICATION_EVIDENCE_MANIFEST.md`) |
| Autres tags | `prestaging-certified-2026-10-16` → `aed2305` ; `n3-local-certified-2026-10-16` → `cc03eb5` |

**Règle** : le code déployé provient exclusivement du tag `edusync-local-certified-2026-10-17` (ou du SHA `2ad66ef`).
Jamais d'un état local non commité, jamais d'une correction faite à la main sur le serveur. Les commits postérieurs
au tag (documentation, dont ce fichier) ne changent pas le code : `git diff 2ad66ef..main -- backend frontend deploy
docker-compose.yml` doit rester vide ; sinon, ne pas déployer et signaler.

```bash
git clone https://github.com/DANIELKIKUNDA/edusync-web.git && cd edusync-web
git checkout --detach edusync-local-certified-2026-10-17
```

## 2. Architecture d'exécution (`docker-compose.yml`)

| Service | Image / build | Rôle | Persistant |
|---|---|---|---|
| `postgres` | `postgres:16-alpine` | PostgreSQL 16, RLS FORCE par école, rôles `edusync_owner` (migrateur), `edusync_tenant`, `edusync_platform`, `edusync_worker` | volume `postgres_data` |
| `redis` | `redis:7-alpine` (`appendonly yes`, `noeviction`) | signal de réveil des workers, temps réel (SSE), limites de débit — jamais source de vérité | volume `redis_data` |
| `object-storage` | `chrislusf/seaweedfs:4.48` | S3 privé des documents (identité S3 générée au démarrage depuis l'environnement), jamais exposé | volume `object_data` |
| `migrator` | `./backend` | une seule exécution : `provision_database.py` puis `bootstrap_platform_admin.py` | — |
| `backend` | `./backend` (Python **3.13**-slim, FastAPI, uvicorn `--proxy-headers`) | API ; healthcheck `GET /health` ; port publié sur `127.0.0.1:8000` uniquement | lit `backup_status` (lecture seule) |
| `outbox-worker` | `./backend` | publie l'outbox transactionnelle (rôle `edusync_worker`) | — |
| `communications-worker` | `./backend` | messagerie : dispatch (NotificationPolicy), envoi e-mail / SMS / push, portefeuille SMS, accusés | — |
| `frontend` | `./frontend` (build **Node 24** + `nginx:alpine`) | PWA React/Vite + reverse proxy `/api/` (SSE non tamponné, imports ≤ 11 Mo) ; `127.0.0.1:8080` | — |
| `tls-proxy` (profil `tls`) | `caddy:2.10.2-alpine` | HTTPS public Let's Encrypt, HSTS `max-age=31536000` (sans includeSubDomains ni preload) ; ports 80/443 | volumes `caddy_data`, `caddy_config` |
| `backup` | `./deploy/backup` (`postgres:16-alpine` + rclone) | sauvegarde quotidienne base + documents, restauration vérifiée, copie hors site optionnelle | volumes `backups`, `backup_status` |

Réseau interne `172.30.57.0/24` : nginx `172.30.57.10`, Caddy `172.30.57.11` (seules adresses acceptées pour
`X-Forwarded-For`). PostgreSQL, Redis et SeaweedFS ne sont jamais publiés.

Démarrage : `docker compose --env-file <fichier> --profile tls up -d --build`. Si l'hébergeur fournit déjà le TLS
(Coolify / Traefik), ne pas activer le profil `tls` : faire pointer le proxy de la plateforme sur `frontend:80` et
ajouter son adresse à `EDUSYNC_FORWARDED_ALLOW_IPS`.

**linux/arm64** : vérifié — les 7 images de base existent en `arm64` ; les 13 paquets Python natifs du
`requirements.lock` publient une roue `aarch64` pour CPython 3.13 ; le frontend est construit dans le conteneur
(`npm ci` sur `package-lock.json`). Aucun binaire spécifique à amd64.

Ressources : 4 Go de RAM minimum dédiés, 2 vCPU, 40 Go de disque (le poste local de 5,8 Go a fait tomber PostgreSQL
sous Docker Desktop).

## 3. Variables d'environnement (noms uniquement)

Un fichier d'environnement par déploiement (`EDUSYNC_ENV_FILE` = chemin du fichier lu par le migrateur ; le compose
lit le même fichier via `--env-file`). 🔐 = secret à **forte entropie**, à générer (≥ 32 octets aléatoires,
ex. `python -c "import secrets;print(secrets.token_urlsafe(32))"`) et à garder dans le coffre de l'hébergeur.

### Application
`EDUSYNC_ENV` (**`staging`** ou `production` : active tous les contrôles de sécurité ; refuse de démarrer avec un
secret de démo, du CORS HTTP, un fournisseur simulé…), `EDUSYNC_ENV_FILE`, `EDUSYNC_ACCESS_TOKEN_MINUTES`,
`EDUSYNC_RATE_LIMIT_MULTIPLIER` (**1** en staging), `EDUSYNC_API_MAX_BODY_BYTES`, `EDUSYNC_API_MAX_QUERY_BYTES`,
`EDUSYNC_OFFLINE_FINANCE_ENABLED` / `EDUSYNC_OFFLINE_FINANCE_CERTIFIED` (**false**).

### PostgreSQL
`POSTGRES_DB`, `POSTGRES_OWNER_USER`, `POSTGRES_OWNER_PASSWORD` 🔐, `EDUSYNC_OWNER_DATABASE_URL` 🔐 (migrateur
seulement), `EDUSYNC_TENANT_DATABASE_URL` 🔐, `EDUSYNC_PLATFORM_DATABASE_URL` 🔐, `EDUSYNC_WORKER_DATABASE_URL` 🔐
(rôle `edusync_worker`). Quatre mots de passe distincts.

### Redis
`EDUSYNC_REDIS_URL` (réseau interne ; ajouter un mot de passe / `rediss://` si Redis est externe).

### Stockage S3
`EDUSYNC_OBJECT_STORAGE_BACKEND` (`s3`), `EDUSYNC_OBJECT_STORAGE_ENDPOINT`, `EDUSYNC_OBJECT_STORAGE_ACCESS_KEY` 🔐,
`EDUSYNC_OBJECT_STORAGE_SECRET_KEY` 🔐, `EDUSYNC_OBJECT_STORAGE_BUCKET`, `EDUSYNC_OBJECT_STORAGE_REGION`,
`EDUSYNC_OBJECT_STORAGE_PATH_STYLE` (optionnel en conteneur : `EDUSYNC_OBJECT_STORAGE_LOCAL_ROOT`, non utilisé avec S3).

### Sécurité / session
`EDUSYNC_JWT_SECRET` 🔐 (≥ 32 caractères), `EDUSYNC_JWT_ISSUER`, `EDUSYNC_JWT_AUDIENCE`,
`EDUSYNC_PERSISTENT_SESSION_COOKIE`, `EDUSYNC_SESSION_ABSOLUTE_DAYS` / `EDUSYNC_SESSION_IDLE_DAYS` (0 : décision du
propriétaire), `EDUSYNC_SESSION_ROTATION_GRACE_SECONDS`, `EDUSYNC_SESSION_COOKIE_MAX_AGE_DAYS`,
`EDUSYNC_LOGIN_MAX_ATTEMPTS`, `EDUSYNC_LOGIN_WINDOW_SECONDS`, `EDUSYNC_LOGIN_LOCK_SECONDS`.

### MFA (comptes plateforme)
`EDUSYNC_MFA_ENCRYPTION_KEY` 🔐 (32 octets en base64, **différente** du secret JWT ; obligatoire en staging ; donnée
aussi au `communications-worker`, qui en dérive les clés des jetons push et des liens), `EDUSYNC_MFA_PLATFORM_REQUIRED`
(true, non désactivable hors développement), `EDUSYNC_MFA_CHALLENGE_SECONDS`, `EDUSYNC_MFA_MAX_ATTEMPTS`,
`EDUSYNC_MFA_LOCK_SECONDS`, `EDUSYNC_MFA_STEPUP_SECONDS`.

### Documents / liens signés
`EDUSYNC_DOCUMENT_LINK_SECRET` 🔐 (explicite en staging), `EDUSYNC_DOCUMENT_LINK_SECONDS`.

### Bootstrap Manager Système
`EDUSYNC_SETUP_TOKEN` 🔐 (usage unique, à retirer après), `EDUSYNC_PLATFORM_ADMIN_EMAIL`,
`EDUSYNC_PLATFORM_ADMIN_PASSWORD` (**laisser vide** : création par la page de premier démarrage),
`EDUSYNC_PLATFORM_ADMIN_NAME`.

### Sauvegarde
`EDUSYNC_BACKUP_STATUS_FILE` (fixé par le compose : `/backup-status/last.json`), `EDUSYNC_BACKUP_INTERVAL_SECONDS`,
`EDUSYNC_BACKUP_KEEP_DAYS`, `EDUSYNC_BACKUP_OFFSITE`, `EDUSYNC_BACKUP_OFFSITE_TYPE`, `EDUSYNC_BACKUP_OFFSITE_PROVIDER`,
`EDUSYNC_BACKUP_OFFSITE_ENDPOINT`, `EDUSYNC_BACKUP_OFFSITE_ACCESS_KEY` 🔐, `EDUSYNC_BACKUP_OFFSITE_SECRET_KEY` 🔐.

### E-mail
`EDUSYNC_EMAIL_PROVIDER` (`disabled` au départ ; `smtp` plus tard), `EDUSYNC_SMTP_HOST`, `EDUSYNC_SMTP_PORT`,
`EDUSYNC_SMTP_USERNAME`, `EDUSYNC_SMTP_PASSWORD` 🔐 (worker seulement), `EDUSYNC_SMTP_FROM_EMAIL`,
`EDUSYNC_SMTP_FROM_NAME`, `EDUSYNC_SMTP_SECURITY` (`starttls`|`tls`), `EDUSYNC_SMTP_TIMEOUT_SECONDS`,
`EDUSYNC_INVITATION_TTL_HOURS`, `EDUSYNC_PASSWORD_RESET_TTL_MINUTES`.

### SMS
`EDUSYNC_SMS_PROVIDER` (`disabled` au départ ; `orange` plus tard), `EDUSYNC_ORANGE_SMS_CLIENT_ID`,
`EDUSYNC_ORANGE_SMS_CLIENT_SECRET` 🔐 (worker seulement), `EDUSYNC_ORANGE_SMS_SENDER_ADDRESS`,
`EDUSYNC_ORANGE_SMS_SENDER_NAME`, `EDUSYNC_ORANGE_SMS_API_BASE`, `EDUSYNC_ORANGE_SMS_MAX_TPS`,
`EDUSYNC_ORANGE_SMS_DR_SECRET` 🔐 (≥ 24 caractères), `EDUSYNC_ORANGE_SMS_DR_ALLOWED_IPS`.

### Push
`EDUSYNC_PUSH_PROVIDER` (`disabled` au départ ; `fcm` plus tard), `EDUSYNC_FCM_SERVICE_ACCOUNT_FILE` (secret monté,
recommandé) ou `EDUSYNC_FCM_SERVICE_ACCOUNT_JSON` 🔐 (worker seulement), `EDUSYNC_FCM_WEB_CONFIG_JSON` (public),
`EDUSYNC_FCM_VAPID_PUBLIC_KEY` (public).

### URLs publiques, CORS, hôtes, proxy
`EDUSYNC_PUBLIC_APP_URL` (`https://<domaine>`, obligatoire en HTTPS dès que l'e-mail est actif), `EDUSYNC_DOMAIN`,
`EDUSYNC_ACME_EMAIL` (profil `tls`), `EDUSYNC_CORS_ORIGINS` (`https://<domaine>` uniquement),
`EDUSYNC_TRUSTED_HOSTS` (`<domaine>,localhost` — `localhost` pour le healthcheck interne),
`EDUSYNC_FORWARDED_ALLOW_IPS` (adresses fixes des proxys).

Gabarit complet et commenté : `.env.example` (noms seulement).

## 4. Messagerie — état exact

| Canal | Code local | Fournisseur réel | Staging initial |
|---|---|---|---|
| **E-mail** | prêt (`EMAIL_LOCAL_READY`) | **non certifié** (`EXTERNAL_REQUIRED`) | peut rester `disabled` ; sans e-mail, l'invitation se fait par mot de passe provisoire affiché une fois ; aucune fonction métier fondamentale n'en dépend |
| **SMS** | prêt (`SMS_LOCAL_READY`), architecture indépendante du fournisseur (`SmsProviderPort`) | **Orange : réponse commerciale / API en attente** (`EXTERNAL_REQUIRED`) ; API RDC marquée « deprecated » sur Orange Developer, à confirmer | `disabled` ; chaque école peut couper ses SMS ; l'absence de SMS ne bloque jamais EduSync |
| **Push** | prêt (`PUSH_LOCAL_READY`) | **FCM non configuré** (`EXTERNAL_REQUIRED`) ; FCM n'est pas un SMS payant | `disabled` ; certification réelle avec un projet Firebase et un vrai téléphone (Android PWA, iOS à part) |

Les fournisseurs simulés (`fake`) sont refusés en staging. Détails : `EXTERNAL_MESSAGING_ARCHITECTURE.md`,
`SMS_ORANGE_INTEGRATION.md`, `SMS_WALLET_MODEL.md`, `PUSH_FCM_INTEGRATION.md`, `EMAIL_TRANSACTIONAL_INTEGRATION.md`,
`EXTERNAL_MESSAGING_SECURITY_REVIEW.md`, `EXTERNAL_MESSAGING_CERTIFICATION.md`.

## 5. Bootstrap du premier Manager Système

1. Avant le premier démarrage : `EDUSYNC_PLATFORM_ADMIN_PASSWORD` **vide**, `EDUSYNC_SETUP_TOKEN` = valeur aléatoire
   connue du seul opérateur.
2. Le migrateur crée le schéma ; `bootstrap_platform_admin.py` ne crée aucun compte (mot de passe vide) : la page de
   connexion propose « Première installation ».
3. Sur `https://<domaine>/`, saisir nom, e-mail, mot de passe (≥ 12 caractères) et le **jeton de setup**. Sans jeton
   ou avec un faux jeton : refus (403). En staging, le jeton est exigé même depuis le serveur.
4. **Usage unique** : dès qu'un Manager existe, `platform_setup_completion` est écrit (verrou consultatif + clé
   singleton) ; toute nouvelle tentative répond 409, même avec le bon jeton.
5. Première connexion : mot de passe, puis **enrôlement TOTP obligatoire** (QR code local, clé manuelle), confirmation
   par un premier code ; **10 codes de secours** affichés une seule fois — à conserver hors ligne.
6. Après usage : **retirer `EDUSYNC_SETUP_TOKEN`** de l'environnement et redémarrer `backend` (le mécanisme est déjà
   fermé par la base ; le retrait évite de garder un secret inutile).
7. Recommandé : créer immédiatement un **second Manager Système** (Équipe plateforme) pour la récupération en cas de
   téléphone perdu. Secours ultime : `docker compose run --rm migrator python scripts/reset_platform_mfa.py` (audité).

## 6. Migrations

* Commande (lancée automatiquement par le service `migrator` avant l'API et les workers) :
  `docker compose --env-file <fichier> run --rm migrator` — soit
  `python scripts/provision_database.py && python scripts/bootstrap_platform_admin.py`.
* Ordre : `postgres` sain → `migrator` (code de sortie 0 exigé : `service_completed_successfully`) → `backend`,
  `outbox-worker`, `communications-worker`, `backup` → `frontend` (après l'API saine).
* Base vierge : crée les rôles (`edusync_tenant`, `edusync_platform`, `edusync_worker` avec leurs mots de passe),
  applique les 79 migrations dans l’ordre (0001 → **0076_external_messaging**), réapplique les droits et politiques,
  affiche `POINT-4A database provisioning: PASS`.
* Mise à niveau : n'applique que les migrations absentes de `schema_migrations` ; idempotent (relancer ne change rien).
* Échec : tout le provisionnement s'exécute **dans une seule transaction** ; une migration en erreur annule l'ensemble
  de l'exécution, la base reste dans l'état précédent, le migrateur sort en erreur et l'API ne démarre pas. Ne jamais
  corriger à la main sur le serveur : remonter l'erreur, corriger dans le dépôt, recertifier, redéployer.
* Rollback : migrations **en avant seulement**. Retour arrière applicatif = redéployer l'image précédente si aucune
  nouvelle migration n'a été appliquée ; sinon restauration de la sauvegarde vérifiée prise avant la mise à jour, ou
  migration corrective en avant (préférable dès que des données réelles existent).

## 7. Sauvegarde / restauration

* Service `backup` (`deploy/backup/backup.sh`), toutes les `EDUSYNC_BACKUP_INTERVAL_SECONDS` (24 h par défaut) :
  `pg_dump -Fc` + copie des documents S3 (rclone) → `SHA256SUMS` → **restauration dans une base isolée**
  (`edusync_restore_check`) → comptes de lignes de 12 tables encadrés avant / après → suppression de la base de
  contrôle → rétention `EDUSYNC_BACKUP_KEEP_DAYS` (14 j) → `/backup-status/last.json`
  (`ok`, `restore_verified`, `offsite`) lu par l'écran **Santé du système** de l'Atelier Pro.
* Déclencher et vérifier à la main : `docker compose exec backup sh /usr/local/bin/edusync-backup once`.
* Copie hors site : `EDUSYNC_BACKUP_OFFSITE` + `EDUSYNC_BACKUP_OFFSITE_*` (tout remote rclone, S3 par défaut) —
  **`EXTERNAL_REQUIRED`** tant qu'aucune cible n'est fournie (`offsite=false` dans l'état).
* Restauration réelle : `pg_restore` du `db.dump` vers une base neuve + recopie de `objects/` dans le bucket ;
  exercice à faire sur le staging avant le pilote.

## 8. Tests à rejouer sur le staging

Le dernier test réel de pile Docker était **28 / 28 sur `aed2305`** ; il doit être rejoué sur le code déployé
(`2ad66ef`), le compose ayant reçu depuis les variables de messagerie.

1. **Pile staging** (`certification/prestaging-20261016/staging_stack_probe.py`) — à exécuter sur l'hôte Docker, dans
   un **projet compose jetable** (la sonde crée le premier Manager Système : jamais sur le staging qui servira au
   pilote) :
   ```bash
   cp <env-staging-de-test> .local/staging-smoke.env
   docker compose --env-file .local/staging-smoke.env -p edusync-smoke up -d --build
   PYTHONUTF8=1 python certification/prestaging-20261016/staging_stack_probe.py
   ```
   La sonde s'adresse à `http://127.0.0.1:8080` avec l'hôte `staging.edusync.localhost` : inclure cet hôte dans
   `EDUSYNC_TRUSTED_HOSTS` et `https://staging.edusync.localhost` dans `EDUSYNC_CORS_ORIGINS` du fichier de test.
   Couvre : services, migrateur, contrôles de sécurité, SeaweedFS, bootstrap + TOTP, cookie Secure, imports > 1 Mo via
   nginx, SSE > 60 s, sauvegarde réelle et restauration isolée, état de sauvegarde (28 contrôles).
2. **Santé** : `GET https://<domaine>/health-api` → 200 ; Atelier Pro → Santé du système (base, Redis, stockage,
   workers, sauvegarde) au vert.
3. **Sondes N0 / N1 / N2 / N3 et messagerie** : `python tools/certification/n0_n1_certify.py` exécute toutes les
   sondes (RLS / multi-école, connexion / MFA, imports, notifications, sauvegarde, UI 390 / 1280 px, PWA, messagerie).
   Elles **créent des écoles et des comptes de recette** et ont besoin d'un accès propriétaire à la base : ne les lancer
   que sur un environnement de staging **dédié aux tests** (base jetable), avec un `.local/certification.env` pointant
   vers lui, et un navigateur Edge/Chromium piloté (port 59223) pour les contrôles UI. Jamais sur les données du pilote.
4. **Manuel sur appareil** : installation de la PWA (Android Chrome, iPhone Safari), hors ligne / reprise, impression.

## 9. Règles de handoff

* Ne pas modifier le code fonctionnel pour « faire passer » le staging : tout écart se corrige dans le dépôt,
  se recertifie, puis se redéploie depuis un nouveau tag.
* Le tag `edusync-local-certified-2026-10-17` ne se déplace jamais.
* Aucun secret dans Git, dans ce document, dans les captures, ni dans le chat.
* Ouvrir les certifications réelles des fournisseurs (e-mail, SMS, push) uniquement quand le propriétaire fournit
  leurs accès — chacune avec sa sonde réelle et une confirmation humaine de réception.
