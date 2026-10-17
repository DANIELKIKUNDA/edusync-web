# EduSync — CI/CD (intégration continue et déploiement staging)

État au 2026-10-17 : aucun workflow n'existait (`.github/` absent, aucun environnement, secret ni variable GitHub,
aucun script SSH ou Coolify). Ajouté : `.github/workflows/ci.yml`, `.github/workflows/deploy-staging.yml`,
`deploy/staging/` (surcharge compose « images », script de déploiement, smoke tests), `tools/ci/secret_patterns.py`,
tests `backend/tests/test_cicd_contracts.py`. Aucun code métier modifié ; la certification de `2ad66ef` reste valable.

## 1. Flux

```
push main / tag edusync-* | v*      PR / autre branche
          │                                 │
          ▼                                 ▼
CI : backend (pytest, compileall) ─ frontend (npm ci, tsc, build) ─ sécurité (pip-audit, npm audit, licences/SBOM, secrets)
          │ tout PASS (main ou tag uniquement)
          ▼
images linux/amd64 + linux/arm64 → GHCR : edusync-backend / edusync-frontend / edusync-backup : <SHA> (+ nom du tag)
          │ CI = success
          ▼
Deploy staging (environnement GitHub « staging », jamais production)
   SSH → remote_deploy.sh du commit déployé :
   pull des images du SHA → sauvegarde vérifiée → migrations (migrator code 0) → démarrage → smoke tests
          ├─ PASS → version conservée (state/current = SHA)
          ├─ FAIL sans migration nouvelle → rollback automatique vers state/current précédent + smoke tests
          └─ FAIL avec migration nouvelle → arrêt sûr (API, workers, frontend arrêtés ; base et volumes intacts)
   → vérification HTTPS publique (si STAGING_PUBLIC_URL est défini)
```

* **CI** : à chaque push et pull request. Les images ne sont construites qu'après les trois contrôles, uniquement sur
  `main` et les tags, étiquetées par le **SHA complet** (jamais `latest`).
* **CD** : uniquement le staging, automatiquement après une CI réussie sur un push de `main` ou d'un tag `edusync-*`,
  ou à la main (*Run workflow* avec un SHA déjà construit). Jamais de déploiement concurrent (`concurrency`).
* **Production** : aucun workflow ne la déploie ; le script refuse un fichier d'environnement `EDUSYNC_ENV=production`.

## 2. Configuration GitHub à faire une fois (propriétaire / Codex)

Environnement **`staging`** (Settings → Environments ; facultatif : approbation requise, branches `main` et tags
`edusync-*`). Secrets **de l'environnement** (noms seulement) :

| Secret | Contenu |
|---|---|
| `STAGING_SSH_HOST` | nom ou adresse du serveur staging |
| `STAGING_SSH_USER` | compte de déploiement (membre du groupe `docker`, sans sudo) |
| `STAGING_SSH_KEY` | clé privée **dédiée** au déploiement (ed25519), dont la clé publique est seule autorisée sur ce compte |
| `STAGING_SSH_KNOWN_HOSTS` | sortie de `ssh-keyscan -t ed25519 <hôte>` vérifiée (empreinte comparée hors bande) |

Variables (facultatives) : `STAGING_PUBLIC_URL` (`https://<domaine-staging>`, active la vérification externe),
`STAGING_SSH_PORT` (22), `STAGING_APP_DIR` (`/opt/edusync`).

Aucun autre secret : le jeton GHCR est le `GITHUB_TOKEN` éphémère du run (`packages: read`), passé par l'entrée
standard SSH, utilisé pour `docker login` puis oublié. Tant que les quatre secrets SSH manquent, le workflow s'arrête
proprement avec « Staging non configuré » (la CI reste verte).

## 3. Préparation unique du serveur

```bash
# compte de déploiement : docker + git, aucune clé ni secret dans le dépôt
sudo mkdir -p /opt/edusync/{env,state} && sudo chown -R deploy:deploy /opt/edusync
git clone https://github.com/DANIELKIKUNDA/edusync-web.git /opt/edusync/repo      # dépôt privé : clé de lecture / jeton du serveur
cp /opt/edusync/repo/.env.example /opt/edusync/env/staging.env && chmod 600 /opt/edusync/env/staging.env
# remplir staging.env (EDUSYNC_ENV=staging, secrets générés : voir CODEX_STAGING_HANDOFF.md §3)
```

Le premier déploiement crée la base (migrations) ; le premier Manager Système se crée ensuite par le jeton de setup
(CODEX_STAGING_HANDOFF.md §5). Si le TLS est assuré par le service Caddy du compose, ajouter `EDUSYNC_DEPLOY_TLS_PROFILE=true` dans
`staging.env` (le script ajoute alors `--profile tls`) ; si l'hébergeur (Coolify / Traefik) assure le TLS, ne pas le mettre.

> **Coolify** : ce pipeline n'utilise pas Coolify (aucune intégration n'existait). Si le staging est géré par Coolify,
> ne pas faire tourner les deux sur le même projet : soit Coolify déploie les images GHCR par SHA (ce workflow
> désactivé), soit ce workflow déploie par SSH (Coolify ne gère alors pas cette pile).

## 4. Smoke tests (`deploy/staging/smoke.sh`)

API saine (healthcheck Docker, ≤ 5 min) ; migrateur terminé avec le code 0 ; les 8 services en marche, aucun en
boucle de redémarrage (vérifié à nouveau 20 s plus tard) ; contrôles de sécurité staging actifs dans le conteneur
(`assert_runtime_safe`) ; PWA (`/`), santé (`/health-api`) et API (`/api/v1/setup/status`) servies par nginx.
Puis, depuis GitHub, `https://<domaine>/health-api` → 200 si `STAGING_PUBLIC_URL` est défini.
Les sondes fonctionnelles complètes (N0–N3, pile staging, messagerie) se rejouent sur un staging **de test**
(CODEX_STAGING_HANDOFF.md §8), pas à chaque déploiement : elles créent des écoles et des comptes.

## 5. Rollback réel

| Situation | Ce qui se passe | Code |
|---|---|---|
| Échec avant toute modification (pull, sauvegarde d'avant mise à jour) | rien n'a changé, l'ancienne version tourne | 1 |
| Déploiement en échec **sans migration nouvelle** (même nombre de lignes dans `schema_migrations` ; migration en erreur = transaction annulée) | **rollback automatique** : fichiers compose et images du SHA précédent (`state/current`), redémarrage, smoke tests | 2 |
| Déploiement en échec **avec migration nouvelle**, ou premier déploiement | **arrêt sûr** : `frontend`, `backend` et workers arrêtés ; PostgreSQL, Redis, stockage et sauvegardes intacts | 3 |

Restauration après un arrêt sûr (décision humaine, sur le serveur, sauvegarde prise juste avant la mise à jour) :

```bash
cd /opt/edusync/repo
P="docker compose --env-file /opt/edusync/env/staging.env -p edusync-staging -f docker-compose.yml -f deploy/staging/docker-compose.images.yml"
export EDUSYNC_IMAGE_REGISTRY=ghcr.io/danielkikunda EDUSYNC_IMAGE_TAG=$(cat /opt/edusync/state/current)
git checkout --detach "$EDUSYNC_IMAGE_TAG"
$P exec backup ls /backups                          # repérer le dossier horodaté d'avant la mise à jour
$P exec postgres sh -c 'dropdb -U "$POSTGRES_USER" --if-exists edusync_restore && createdb -U "$POSTGRES_USER" edusync_restore'
$P exec backup sh -c 'pg_restore --exit-on-error --no-owner -d edusync_restore /backups/<horodatage>/db.dump'
# vérifier edusync_restore, puis basculer (renommer les bases) et `$P up -d` ; documents : recopier /backups/<horodatage>/objects
```

Revenir volontairement à une version connue : *Actions → Deploy staging → Run workflow* avec le SHA voulu (s'il n'y a
pas de migration plus récente que ce SHA ; sinon, restauration ci-dessus).

## 6. Sécurité de la chaîne

Actions officielles `actions/*` et `docker/*` (versions majeures) ; permissions minimales (`contents: read`, `packages:
write` seulement pour publier) ; clé SSH écrite dans le runner, `StrictHostKeyChecking=yes`, supprimée en fin de job ;
aucun secret dans Git (scan `tools/ci/secret_patterns.py` à chaque CI) ; images reproductibles (`requirements.lock`,
`npm ci`). Amélioration possible : épingler les actions par SHA de commit.
