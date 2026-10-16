# EduSync Web — préparation au staging (rapport, aucun déploiement)

Date : 2026-10-16. Base : `main` = `5302743` (code certifié `cc03eb5`, tag `n3-local-certified-2026-10-16`).
Méthode : lecture de `docker-compose.yml`, `.env.example`, `backend/Dockerfile`, `frontend/Dockerfile`,
`frontend/nginx.conf`, `backend/src/edusync/bootstrap/settings.py`, des workers, de la PWA et des outils locaux.
**Aucun comportement métier modifié, aucune dépendance changée, rien déployé.**

Légende :
* `PRÊT` : utilisable tel quel.
* `À CONFIGURER` : réglage d'exploitation, sans code métier.
* `ÉCART` : à corriger avant le staging. Correctif d'infrastructure ou de configuration, jamais de règle métier.
* `BLOCKED_EXTERNAL` : dépend d'un service ou d'un compte externe.
* `APPAREIL` : exige un téléphone ou un poste réel.

## Mise à jour du 2026-10-16 — S1 à S9 corrigés

Commits d'infrastructure (aucune règle métier) : S1 `0bb3378`, S2 `56862de`, S3 `e5428d9`, S4 `214a260`, S5 `15cba7e`,
S6 `1afbfb4`, S7 `eb32e7c`, S8 `07f6dcc`, S9 `44624c2`, versions des images `a29b8d1`, garde d'import `b18accc`, test de
pile `aed2305` (candidat pré-staging). Test réel de la pile Docker en mode staging : 28/28
(`certification/prestaging-20261016/staging-stack-live.json`). Certification complète N0/N1/N2/N3 : 45/45 sur `aed2305`.

* HSTS : `max-age=31536000`, **sans** `includeSubDomains` ni `preload` (décision du propriétaire).
* **Mémoire** : la pile complète (PostgreSQL, Redis, SeaweedFS, API, 2 workers, nginx, sauvegarde) a fait tomber
  PostgreSQL sur un poste de 5,8 Go partagé avec Docker Desktop et un navigateur. Serveur de staging : **4 Go de RAM
  minimum dédiés**, 2 vCPU, 40 Go de disque (base, documents, sauvegardes locales).
* Restent `BLOCKED_EXTERNAL` : domaine et certificat public, cible de sauvegarde hors site, supervision externe,
  e-mail, push et SMS (désactivés proprement, non certifiés).

## 0. Écarts bloquants identifiés avant correction (historique)

| # | Écart | Gravité | Correctif proposé (non appliqué) |
|---|---|---|---|
| S1 | `assert_runtime_safe()` ne contrôle que `EDUSYNC_ENV` = `prod` ou `production`. Avec `EDUSYNC_ENV=staging`, **aucune** vérification n'est faite : secret JWT de dev, mots de passe de démo, CORS non HTTPS et hôtes de confiance sont tous acceptés. Le cookie de session n'a le drapeau `Secure` qu'en `prod`/`production` (`iam/api/router.py:39`), alors que la MFA et le jeton de setup traitent déjà `staging` comme protégé. | **Haute** | Option immédiate, sans code : lancer le staging avec `EDUSYNC_ENV=production` et des données fictives. Option propre : inclure `staging` dans les deux contrôles (petit correctif d'infrastructure, testé, commit séparé). |
| S2 | `docker-compose.yml` ne transmet pas à l'API `EDUSYNC_TRUSTED_HOSTS`, `EDUSYNC_MFA_ENCRYPTION_KEY`, `EDUSYNC_DOCUMENT_LINK_SECRET`, `EDUSYNC_BACKUP_STATUS_FILE` ni `EDUSYNC_OBJECT_STORAGE_BACKEND`. En `production`, l'API refuse de démarrer sans clé MFA, et l'hôte de confiance par défaut (`localhost,127.0.0.1,testserver`) rejette le vrai domaine. | **Haute** | Ajouter ces variables au service `backend`, ou passer par un `env_file` dédié à l'API (sans les secrets owner ni bootstrap). |
| S3 | `.env.example` pointe vers `http://object-storage:8333`, mais **aucun service de stockage objet** n'existe dans `docker-compose.yml`. Sans endpoint, les documents renvoient 503. | **Haute** | Ajouter un service S3 auto-hébergé (SeaweedFS ou Garage) ou un compte S3 externe (R2, B2, S3), avec un bucket privé. |
| S4 | nginx n'a pas de `client_max_body_size` : la valeur par défaut est **1 Mo**. Les imports Excel acceptent jusqu'à **10 Mio** (`MAX_IMPORT_BYTES`) et l'API accepte 2 Mio par défaut. Au-delà de 1 Mo, nginx renvoie 413 avant même l'API. | **Haute** | `client_max_body_size 11m;` sur `/api/` (ou au moins sur `/api/v1/import/`). |
| S5 | Le flux temps réel (SSE, `notifications_center`) passe par `location /api/` avec `proxy_read_timeout 60s` et la mise en tampon nginx active. L'API envoie bien `X-Accel-Buffering: no`, mais la connexion est coupée toutes les 60 s. | Moyenne | `location` dédiée au SSE : `proxy_buffering off; proxy_read_timeout 1h;`. |
| S6 | L'image frontend fait `npm install` sans copier `package-lock.json` : le build n'est pas reproductible et diffère de ce qui a été certifié. | Moyenne | `COPY package.json package-lock.json` puis `npm ci`. |
| S7 | Aucune terminaison TLS ni HSTS : le frontend expose `8080:80` en HTTP. | **Haute** | Reverse proxy TLS devant le service (Caddy ou Traefik, ou nginx avec certbot), HSTS ajouté à ce niveau. |
| S8 | `FORWARDED_ALLOW_IPS` vaut `*` par défaut. | Moyenne | Restreindre à l'adresse ou au réseau du proxy nginx. |
| S9 | Aucune tâche de sauvegarde en production : `tools/local/backup_restore.py` ne fonctionne que sur le poste Windows (`C:\Program Files\PostgreSQL\16\bin`, `.local/certification.env`). | **Haute** | Tâche planifiée pg_dump + objets S3, avec hors-site, rétention et restauration vérifiée (voir § 9). |

## 1. Configuration production / staging

* Architecture certifiée : une API FastAPI (uvicorn), PostgreSQL 16 avec RLS FORCE, Redis 7, deux workers (outbox,
  communications), un frontend nginx (PWA statique), un stockage objet S3 et un migrateur à exécution unique. `PRÊT`
  (en code).
* `docker-compose.yml` est un **squelette** : il manque le stockage objet, TLS, la sauvegarde, la supervision et
  plusieurs variables (S2, S3, S7, S9). `ÉCART`.
* **Versions** : l'image backend utilise `python:3.12-slim`, alors que la certification a tourné en **Python 3.13.14**
  (`requires-python >=3.11`). L'image frontend utilise `node:22-alpine` ; Node local : 24. → Aligner les versions ou
  refaire la certification dans les images. `À CONFIGURER`.
* Recommandation : un staging **identique à la production** (mêmes images, mêmes variables, `EDUSYNC_ENV=production`
  tant que S1 n'est pas corrigé), avec des données fictives.

## 2. Variables d'environnement

| Variable | Rôle | État |
|---|---|---|
| `EDUSYNC_ENV` | active les contrôles de sécurité | `production` obligatoire (voir S1) |
| `EDUSYNC_TENANT_DATABASE_URL`, `EDUSYNC_PLATFORM_DATABASE_URL` | API : rôles applicatifs | refusées si elles contiennent des marqueurs de démo |
| `EDUSYNC_OWNER_DATABASE_URL` | migrateur uniquement | jamais dans l'API (respecté par le compose) |
| `EDUSYNC_WORKER_DATABASE_URL` | workers, rôle `edusync_worker` | contrôlée par `worker_url()` |
| `EDUSYNC_REDIS_URL` | file d'attente, temps réel, limitation de débit | défaut compose correct |
| `EDUSYNC_JWT_SECRET` | ≥ 32 caractères (validateur) | à générer |
| `EDUSYNC_MFA_ENCRYPTION_KEY` | 32 octets en base64, distincte du JWT | **absente du compose (S2)** |
| `EDUSYNC_TRUSTED_HOSTS` | domaine(s) exact(s) | **absente du compose (S2)** |
| `EDUSYNC_CORS_ORIGINS` | origines `https://` explicites | défaut `http://localhost…`, refusé en production |
| `EDUSYNC_DOCUMENT_LINK_SECRET` | liens signés des documents | absente : dérivée du JWT, à rendre explicite |
| `EDUSYNC_OBJECT_STORAGE_*` | S3 | service absent (S3) |
| `EDUSYNC_BACKUP_STATUS_FILE` | état de sauvegarde affiché sur l'écran de santé | absente (S2, S9) |
| `EDUSYNC_SETUP_TOKEN` | création du premier Manager Système | usage unique, à retirer ensuite |
| `EDUSYNC_PLATFORM_ADMIN_*` | création initiale par le migrateur | mot de passe de démo refusé en production |
| `EDUSYNC_SMS_PROVIDER`, `ORANGE_SMS_*` | SMS | `disabled` (`BLOCKED_EXTERNAL`) |
| `EDUSYNC_PUSH_PROVIDER` | notifications push | `disabled` (`BLOCKED_EXTERNAL`) |
| `EDUSYNC_OFFLINE_FINANCE_ENABLED` / `_CERTIFIED` | finance hors ligne | rester à `false` |
| `EDUSYNC_RATE_LIMIT_MULTIPLIER` | limites de débit | **1** en staging (les sondes locales l'augmentent) |
| `EDUSYNC_SESSION_ABSOLUTE_DAYS` / `_IDLE_DAYS` | session persistante | décision propriétaire du 2026-10-07 : 0 |
| `VITE_API_BASE_URL` | build frontend | inutile en mode même origine (`/api/v1` par défaut) |

## 3. Secrets

* Les secrets sont lus depuis l'environnement, jamais depuis le dépôt. Le scan de secrets de la certification donne
  0 fuite sur 1 540 fichiers. `PRÊT`.
* À générer pour le staging (jamais réutiliser ceux de `.local/`) : mots de passe des 4 rôles PostgreSQL (owner,
  tenant, platform, worker), secret JWT, clé MFA, secret des liens de documents, clés S3, jeton de setup.
* Le migrateur reçoit tout le fichier `.env` (`env_file: .env`), y compris des secrets dont il n'a pas besoin.
  L'API, elle, ne reçoit que ses propres variables. Il faut séparer `api.env`, `worker.env` et `migrator.env`.
  `À CONFIGURER`.
* Il faut stocker les secrets dans un coffre (gestionnaire de secrets de l'hébergeur ou fichiers `chmod 600` hors
  dépôt), avec une procédure de rotation documentée (JWT, MFA, S3). `À CONFIGURER`.
* Changer la clé MFA rend illisibles les secrets TOTP existants. La procédure de récupération existe
  (`backend/scripts/reset_platform_mfa.py`).

## 4. PostgreSQL

* RLS FORCE par école, 4 rôles à moindre privilège et droits accordés migration par migration : `PRÊT`, certifié
  N0 à N3.
* Le compose utilise `postgres:16-alpine` avec un volume local, sans réglage mémoire ni connexions.
  `À CONFIGURER` : `shared_buffers`, `max_connections` (pool SQLAlchemy de l'API et des workers), `log_min_duration_statement`.
* Fuseau, encodage `UTF8` et locale à fixer explicitement. Les montants sont en `numeric` et ne dépendent pas de la locale.
* PostgreSQL ne doit **jamais** être exposé publiquement (le compose n'ouvre pas le port 5432). `PRÊT`.
* Option managée : possible, à condition que le service autorise `FORCE ROW LEVEL SECURITY` et la création de rôles
  par le migrateur.

## 5. Redis

* Utilisé pour l'outbox, la diffusion temps réel et la limitation de débit. La reprise après panne Redis est
  certifiée (`resilience_probe` 16/16, POINT10H10). `PRÊT`.
* Le compose lance `redis:7-alpine --appendonly yes` sans mot de passe, sur le réseau interne uniquement. Pour un
  hôte partagé : `requirepass` ou ACL, et `rediss://` si Redis est externe. `À CONFIGURER`.
* Fixer `maxmemory` et une politique `noeviction`, pour ne pas perdre de messages de la file. `À CONFIGURER`.

## 6. Stockage objet

* Le code est compatible avec tout S3 (style chemin ou virtuel), avec un bucket **privé** et des liens signés de
  300 s. `PRÊT` (en code).
* **Service absent du compose (S3).** Il faut choisir entre un S3 auto-hébergé (SeaweedFS, utilisé en local, ou
  Garage) et un S3 externe (R2, B2, S3). `ÉCART` / `BLOCKED_EXTERNAL` si l'option est externe.
* Prévoir la sauvegarde des objets (logos, documents générés) avec la base (§ 9), le versionnement du bucket et une
  règle de cycle de vie.

## 7. Workers

* `outbox-worker` et `communications-worker` tournent dans le compose avec le rôle `edusync_worker` (jamais le
  owner) et redémarrent automatiquement. `PRÊT`.
* Ils n'ont pas de `healthcheck` dans le compose : l'état de la file est visible sur l'écran de santé de la
  plateforme, mais pas pour l'orchestrateur. `À CONFIGURER`.
* SMS : `disabled`. Le contrat réel de l'opérateur (Orange) reste à certifier en staging. `BLOCKED_EXTERNAL`.

## 8. Domaine / HTTPS

* Il faut un nom de domaine, un DNS et un certificat TLS (Let's Encrypt). `BLOCKED_EXTERNAL`.
* La terminaison TLS et HSTS manquent (S7). Les en-têtes CSP, X-Frame-Options, nosniff, Referrer-Policy et COOP sont
  déjà posés par nginx. `PRÊT`.
* Après HTTPS : `EDUSYNC_CORS_ORIGINS=https://<domaine>`, `EDUSYNC_TRUSTED_HOSTS=<domaine>`, cookie `Secure` (S1).
* Points qui n'ont jamais pu être testés en local, faute de HTTPS public : cookie `Secure`, HSTS, installation de la
  PWA, push. À faire en staging.

## 9. Sauvegarde / restauration

* L'exercice local est certifié : pg_dump et objets, chaque fichier avec son SHA-256, restauration isolée et
  comparaison des comptes (8/8 PASS). `PRÊT` comme **procédure**.
* **Il n'y a pas de tâche de production (S9).** À mettre en place :
  * une sauvegarde quotidienne pg_dump `-Fc` et des objets S3 ;
  * une copie hors site chiffrée, avec une rétention (par exemple 7 jours, 4 semaines, 12 mois) ;
  * l'écriture du fichier `EDUSYNC_BACKUP_STATUS_FILE`, lu par l'écran de santé ;
  * une restauration testée chaque mois dans une base isolée.
* Objectifs à décider par le propriétaire : RPO et RTO. Option : archivage WAL ou PITR pour un RPO inférieur à 24 h.
  `OWNER_DECISION`.

## 10. Logs / monitoring

* Logs JSON structurés (structlog 26.1.0 est figé), avec un identifiant de corrélation par requête (`X-Correlation-ID`),
  sans corps de requête ni données personnelles. Compteur horaire des erreurs 5xx et écran de santé de la plateforme
  (base, Redis, file, sauvegarde). `PRÊT`.
* `/health` ne vérifie que la vie du processus, pas la base : c'est correct pour la liveness, mais il faut une
  sonde de disponibilité externe qui interroge l'écran de santé ou une route métier. `À CONFIGURER`.
* À fournir côté exploitation :
  * la collecte des logs (Loki, ou le service de l'hébergeur), avec une rétention ;
  * une supervision externe (uptime) ;
  * des alertes sur les 5xx, la file outbox en retard, une sauvegarde en échec, le disque, et l'expiration du
    certificat TLS.

  `BLOCKED_EXTERNAL` (choix du service).
* Il n'y a pas de traçage APM ni de suivi d'erreurs (Sentry ou équivalent). C'est optionnel. Si on en ajoute un, il
  faut filtrer les données personnelles.

## 11. Migrations

* 78 fichiers SQL **en avant seulement** (0001 à 0075), appliqués dans l'ordre par `provision_database.py` et suivis
  dans `schema_migrations`. Le migrateur à exécution unique tourne avant l'API (`service_completed_successfully`). Le
  provisionnement sur base vierge est certifié. `PRÊT`.
* Il n'existe **aucune migration de retour arrière**. Le retour arrière d'un schéma passe par une restauration (§ 13).
* Faire tourner le migrateur une première fois sur une copie de la base de staging avant chaque mise en production.
  `À CONFIGURER`.

## 12. PWA

* Manifeste complet (icônes 192 et 512, maskable, SVG), `display: standalone`, langue `fr`. Le service worker ne
  met **jamais** en cache `/api/` ni les requêtes authentifiées (sécurité multi-école). Les assets portent un hash de
  contenu et sont mis en cache un an ; le HTML, `sw.js` et le manifeste sont revalidés à chaque visite. `PRÊT`.
* Le nom du cache est fixe (`edusync-shell-2026-10-n0n1`). Le contenu reste à jour (navigation réseau d'abord, assets
  hachés), mais les anciens assets s'accumulent dans le cache. Bonne pratique : dériver le nom du cache de la version
  de build. `À CONFIGURER` (optionnel).
* Installation réelle sur téléphone : nécessite HTTPS (`BLOCKED_EXTERNAL`) et un appareil réel (`APPAREIL`).

## 13. Stratégie de rollback

1. **Application** : images étiquetées par SHA. Pour revenir en arrière, on redéploie l'image précédente. C'est sans
   risque tant que la version déployée n'a pas appliqué de nouvelle migration.
2. **Schéma** : les migrations ne vont qu'en avant. Avant chaque mise en production, faire une sauvegarde vérifiée.
   Si une migration doit être annulée, deux options :
   * restaurer la sauvegarde, avec perte des écritures postérieures (RPO) ;
   * écrire une migration corrective en avant (préférable dès que des données réelles ont été saisies).
3. Les règles d'ajout seul (paiements, contre-opérations, audit) rendent un rollback par « UPDATE manuel » impossible
   **par conception** : toute correction de données passe par une opération auditable.
4. Il n'existe pas de bascule de fonctionnalités (feature flags), sauf pour la finance hors ligne (`false`).
5. À rédiger avant le staging : un runbook de déploiement et de rollback (ordre migrateur → API → workers →
   frontend, critères de retour arrière, contacts).

## 14. Données de démonstration / test

* La base de staging doit être **neuve** (profil « installation vierge ») : ne jamais y copier
  `edusync_claude_fresh`. Cette base contient les écoles et les comptes de certification, dont les identifiants sont
  stockés dans `.local/`.
* Les comptes de démonstration et de recette créés pour le staging doivent utiliser des adresses et des téléphones
  fictifs, et être supprimés ou désactivés avant toute ouverture réelle.
* Les sondes de certification créent des écoles réelles dans la base visée. Les exécuter en staging uniquement sur
  une base jetable, avec `EDUSYNC_RATE_LIMIT_MULTIPLIER` remis à 1 ensuite.
* `sample_import_templates/` et `sample_outputs*` sont des exemples du dépôt. Ils ne sont pas copiés dans les images.

## 15. Dépendances externes encore absentes

| Dépendance | Usage | État |
|---|---|---|
| Hébergeur (VPS ou cloud) et domaine, DNS | exécution, HTTPS | `BLOCKED_EXTERNAL` |
| Certificat TLS | HTTPS, HSTS, PWA | `BLOCKED_EXTERNAL` |
| Stockage objet (si externe) | documents | `BLOCKED_EXTERNAL` |
| Opérateur SMS (Orange RDC ou autre) | rappels, codes | `BLOCKED_EXTERNAL` (fournisseur `disabled`) |
| E-mail transactionnel | invitations par lien, récupération de compte | **absent du code** (aucun fournisseur SMTP) : `BLOCKED_EXTERNAL` et décision produit |
| Push (VAPID ou Firebase) | notifications sur téléphone | `BLOCKED_EXTERNAL` (fournisseur `disabled`) |
| Collecte des logs, supervision, alertes | exploitation | `BLOCKED_EXTERNAL` |
| Stockage hors site des sauvegardes | reprise après sinistre | `BLOCKED_EXTERNAL` |
| `pip-audit` et SBOM depuis l'image | vulnérabilités Python | à exécuter en staging (réseau) |

## 16. Points nécessitant un appareil physique ou un service externe

* **Appareil** :
  * installation de la PWA sur Android (Chrome) et iOS (Safari, ajout à l'écran d'accueil) ;
  * comportement hors ligne réel (perte de réseau, reprise) ;
  * impression des reçus et rapports PDF sur l'imprimante de l'école ;
  * application d'authentification TOTP du Manager Système ;
  * performance sur un téléphone d'entrée de gamme avec une connexion 3G de RDC.
* **Service externe** :
  * envoi réel de SMS et accusés de livraison ;
  * push ;
  * e-mail ;
  * certificat TLS et HSTS ;
  * sauvegarde hors site ;
  * supervision externe ;
  * test de charge depuis Internet (le test de charge local est documenté dans POINT10H6).

## 17. Ordre proposé (après validation du propriétaire)

1. Corriger les écarts d'infrastructure S1 à S9 : configuration, compose, nginx, Dockerfile. Ce sont des petits
   commits séparés, sans règle métier. Rejouer la certification sur le SHA obtenu.
2. Choisir l'hébergeur, le domaine, le stockage objet et le service de logs (`BLOCKED_EXTERNAL`).
3. Construire les images, régénérer le SBOM et lancer `pip-audit` depuis les images.
4. Déployer le staging sur une base vierge, créer le premier Manager Système avec le jeton de setup, puis activer la
   MFA.
5. Faire la recette en staging : sondes sur l'école de recette, PWA sur appareils réels, sauvegarde puis
   restauration, rollback à blanc.
