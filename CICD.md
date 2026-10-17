# EduSync — CI/CD (intégration continue et déploiement staging à moindre privilège)

État au 2026-10-17. La CI (`.github/workflows/ci.yml`) est inchangée depuis 56ccbcf. La CD staging de 56ccbcf
(script `remote_deploy.sh` transféré par SCP et exécuté par un compte membre du groupe `docker`) est **remplacée** par
le modèle ci-dessous : commande forcée OpenSSH, une seule règle sudo sans argument, contrôleur root installé
administrativement. Aucun code métier modifié ; la certification de `2ad66ef` reste valable.

Fichiers : `.github/workflows/deploy-staging.yml`, `deploy/staging/privileged/` (`deploy-gate.sh`,
`deploy_controller.py`, `compose.digests.yml`, `install_deploy_controller.sh`), tests
`backend/tests/test_deploy_least_privilege.py` et `backend/tests/test_cicd_contracts.py`.

## 1. Modèle de menace et frontière de confiance

| Menace | Réponse |
|---|---|
| Vol de la clé SSH de GitHub Actions (ou compromission du runner / d'un workflow) | La clé ne permet **que** `deploy <SHA>` : pas de shell, pas de SCP/SFTP, pas de redirection (`restrict`). Elle ne peut déployer qu'un SHA du dépôt dont la CI a réussi sur `main` ou un tag `edusync-*`, avec les images construites par cette CI. Pire cas : redéployer une version déjà validée (dont une ancienne, voir §7). |
| Commit malveillant poussé sur une branche | Pas de CI réussie sur `main` / tag → refus. Sur `main`, la CI et la revue restent la protection du code applicatif ; l'**infrastructure** (compose, contrôleur, configuration) ne vient jamais du commit déployé. |
| Accès Docker = root | Le compte `deploy` n'est **pas** dans le groupe `docker` et n'a aucun sudo général. Seul le contrôleur root parle à Docker, avec des arguments construits par lui. |
| Injection dans la commande SSH | `SSH_ORIGINAL_COMMAND` est seulement comparé à `^deploy [0-9a-f]{40}$`, jamais exécuté ni évalué. |
| Image substituée / `latest` / mauvaise architecture | Trois dépôts GHCR fixés dans le code, référence = SHA, index multi-architecture avec `linux/arm64`, résolution en **digest** puis `pull` et `up` par digest (`pull_policy: never`). |
| Fuite du jeton de registre | Jeton éphémère du run (`GITHUB_TOKEN`, lecture seule, expire à la fin du job), transmis par l'entrée standard, jamais en argument, ni journalisé, ni écrit hors d'un `DOCKER_CONFIG` temporaire root 0700 supprimé dans tous les cas. |
| Atteinte à d'autres projets (AtelierPro, Coolify, Tailscale…) | Projet compose fixé à `edusync-staging`, répertoire `/etc/edusync-deploy/compose`, aucune commande `prune`, aucune action hors de ce projet. |
| Mise à jour qui casse la base | Sauvegarde vérifiée (restauration testée) avant tout changement ; registre exact des migrations avant / après ; rollback seulement s'il n'y a aucune migration nouvelle, sinon arrêt sûr. |

Frontière de confiance :

```
GitHub Actions (non fiable pour le serveur)            Serveur staging
──────────────────────────────────────────            ───────────────────────────────────────────────────────────────
ssh deploy@staging "deploy <SHA>"  ── clé dédiée ──▶  sshd → authorized_keys (root:root 0644)
   + GITHUB_TOKEN sur stdin                              restrict,command="/usr/local/libexec/edusync/deploy-gate"
                                                         │ compte deploy : aucun groupe docker, aucun sudo général
                                                         ▼
                                                      deploy-gate (root:root 0755) : analyse, ne s'exécute jamais
                                                         │ sudo -n <contrôleur>  — sans argument, données sur stdin
                                ═══════════ élévation unique ═══════════
                                                         ▼
                                                      deploy-controller (root, python3 -I -S, environnement vidé,
                                                      verrou exclusif) → API GitHub, GHCR, docker compose
                                                      -p edusync-staging, fichiers root-owned de /etc et /var/lib
```

## 2. Commande forcée et contrôleur

**Commande forcée** (`deploy-gate`) : accepte exactement `deploy <SHA de 40 caractères hexadécimaux minuscules>`
(code 64 sinon : SHA court, majuscules, espaces, arguments en plus, `;`, `&&`, `|`, `$( )`, accents graves, retour à
la ligne, autre verbe, chemin). Lit une seule ligne bornée (300 octets, 15 s) sur l'entrée standard : le jeton.
`PATH` fixé, `sudo` et le contrôleur en chemins absolus, puis `exec /usr/bin/sudo -n deploy-controller` avec le SHA
et le jeton sur l'entrée standard.

**Règle sudo** (`/etc/sudoers.d/edusync-deploy`, vérifiée par `visudo`) :

```
Defaults!/usr/local/libexec/edusync/deploy-controller env_reset, !setenv, secure_path="/usr/sbin:/usr/bin:/sbin:/bin", !requiretty
deploy ALL=(root) NOPASSWD: /usr/local/libexec/edusync/deploy-controller ""
```

`""` interdit tout argument ; aucun autre droit.

**Contrôleur** (`deploy-controller`, Python de la distribution en mode isolé `-I -S`) :

1. refuse tout argument ; vide l'environnement ; `umask 077` ; verrou exclusif `/run/edusync-deploy.lock` (75 si
   un déploiement est en cours) ; entrée standard ≤ 1 Kio, exactement deux lignes ASCII (64 sinon) ;
2. vérifie l'installation : contrôleur, commande forcée, compose, configuration, état et journaux appartenant à
   root et non modifiables par un autre compte, `staging.env` en 0600 (78 sinon) ; `EDUSYNC_ENV=staging` (jamais la
   production) ;
3. vérifie via l'API GitHub que le SHA est un commit de `DANIELKIKUNDA/edusync-web` et qu'un run du workflow
   `.github/workflows/ci.yml`, événement `push`, sur `main` ou un tag `edusync-*`, de ce dépôt, a réussi pour ce SHA
   exact (65 sinon) ;
4. résout `ghcr.io/danielkikunda/{edusync-backend,edusync-frontend,edusync-backup}:<SHA>` : index
   multi-architecture contenant `linux/arm64`, digest `sha256:` conservé (65 sinon) ;
5. `docker login --password-stdin` dans un `DOCKER_CONFIG` temporaire, `docker pull --platform linux/arm64` par
   digest, `logout`, suppression du répertoire (également en cas d'erreur) ;
6. avant tout changement : registre exact des migrations (`schema_migrations`), sauvegarde vérifiée
   (`edusync-backup once`, `last.json` avec `ok` et `restore_verified`) — en cas d'échec, code 70 et rien n'a changé ;
   état `attempt.json` (SHA, digests et registre précédents) ;
7. `docker compose --project-name edusync-staging --project-directory /etc/edusync-deploy/compose --env-file
   /etc/edusync-deploy/staging.env -f docker-compose.yml -f compose.digests.yml up --detach --no-build --pull never
   --remove-orphans` (le migrateur s'exécute avant l'API, en une transaction) ;
8. smoke tests : API saine, migrateur au code 0, 8 services en marche et aucun en boucle de redémarrage (20 s plus
   tard), `assert_runtime_safe` en staging dans le conteneur, `/`, `/health-api` et `/api/v1/setup/status` via nginx ;
9. PASS → `current.json` (SHA, digests, registre) et `previous.json` ; FAIL → §6.

Journal : `/var/log/edusync-deploy/deploy.log` (sans jeton). État : `/var/lib/edusync-deploy/*.json`.

| Code | Signification |
|---|---|
| 0 | déployé et vérifié |
| 2 | échec, rollback automatique vers les digests précédents |
| 3 | échec, arrêt sûr (migration nouvelle ou premier déploiement) |
| 64 | requête refusée (commande forcée ou contrôleur) |
| 65 | vérification refusée (dépôt, CI, images) |
| 70 | échec avant tout changement (registre, sauvegarde, téléchargement) |
| 75 | un autre déploiement est en cours |
| 78 | installation serveur non sûre ou environnement non staging |

## 3. Installation administrative (une fois, par edusyncadmin)

Prérequis déjà en place : compte `deploy` sans mot de passe, hors du groupe `docker`, sans sudo, dont
`~deploy/.ssh/authorized_keys` contient **une seule** clé publique, celle de GitHub Actions.

```bash
git clone https://github.com/DANIELKIKUNDA/edusync-web.git ~/edusync-infra      # checkout relu
git -C ~/edusync-infra checkout --detach <SHA ou tag approuvé pour l'infrastructure>
sudo bash ~/edusync-infra/deploy/staging/privileged/install_deploy_controller.sh
sudoedit /etc/edusync-deploy/staging.env       # secrets générés (CODEX_STAGING_HANDOFF.md §3), EDUSYNC_ENV=staging
```

L'installateur est idempotent et n'embarque aucun secret. Il refuse un état inattendu (`deploy` dans le groupe
`docker`, plusieurs clés, commande forcée étrangère) et ne modifie ni `sshd_config` ni aucune configuration SSH
globale. Il installe :

| Chemin | Propriétaire / mode |
|---|---|
| `/usr/local/libexec/edusync/{deploy-gate,deploy-controller}` | root:root 0755 |
| `/etc/edusync-deploy/` (`INSTALLED_FROM` = SHA de l'infrastructure) | root:root 0700 |
| `/etc/edusync-deploy/compose/` (`docker-compose.yml`, `compose.digests.yml`, `deploy/seaweedfs/entrypoint.sh`, `deploy/caddy/Caddyfile`) | root:root 0755 / 0644 |
| `/etc/edusync-deploy/staging.env` (créé depuis `.env.example`, conservé s'il existe) | root:root 0600 |
| `/var/lib/edusync-deploy/` (état), `/var/log/edusync-deploy/` (journaux) | root:root 0700 / 0750 |
| `/etc/sudoers.d/edusync-deploy` | root:root 0440 |
| `~deploy/.ssh/authorized_keys` : `restrict,command="/usr/local/libexec/edusync/deploy-gate",<options existantes> <clé>` | root:root 0644 (`.ssh` root 0755) |

TLS : `EDUSYNC_DEPLOY_TLS_PROFILE=true` dans `staging.env` si le service Caddy du compose assure le TLS ; à omettre si
l'hébergeur le fait. Changer l'infrastructure (compose, contrôleur) = relancer l'installateur depuis un checkout
relu ; un commit applicatif ne la modifie jamais.

> **Coolify** : ce pipeline n'utilise pas Coolify et n'agit sur aucun autre projet. Ne pas faire gérer la même pile
> par les deux.

## 4. Configuration GitHub (une fois)

Environnement **`staging`** (facultatif : approbation requise, branches `main` et tags `edusync-*`). Secrets de
l'environnement, noms seulement :

| Secret | Contenu |
|---|---|
| `STAGING_SSH_HOST` | nom ou adresse du serveur staging |
| `STAGING_SSH_USER` | `deploy` |
| `STAGING_SSH_KEY` | clé privée ed25519 **dédiée**, dont la clé publique est la seule de `deploy` |
| `STAGING_SSH_KNOWN_HOSTS` | `ssh-keyscan -t ed25519 <hôte>` dont l'empreinte a été comparée hors bande |

Variables facultatives : `STAGING_PUBLIC_URL` (vérification HTTPS externe), `STAGING_SSH_PORT` (22). Aucun autre
secret : le jeton du registre et de l'API est le `GITHUB_TOKEN` du run (`contents: read`, `actions: read`,
`packages: read`). Sans les quatre secrets, le workflow s'arrête avec « Staging non configuré ».

## 5. Processus normal

```
push main / tag edusync-*  →  CI (pytest, compileall, tsc, build, pip-audit, npm audit, licences, secrets)
   →  images linux/amd64 + linux/arm64 → GHCR, étiquetées par le SHA complet (jamais latest)
   →  Deploy staging (environnement « staging ») : SHA validé, puis uniquement
        printf '%s\n' "$GITHUB_TOKEN" | ssh -T -o StrictHostKeyChecking=yes -o BatchMode=yes deploy@staging "deploy <SHA>"
   →  contrôleur (§2) → code de sortie traduit dans le résumé du job → HTTPS public (si STAGING_PUBLIC_URL)
```

Aucun checkout, aucun transfert de fichier, aucune commande Docker depuis GitHub. Jamais deux déploiements en même
temps (`concurrency` côté GitHub, verrou côté serveur). Aucun workflow ne déploie la production. Déploiement manuel
d'un SHA déjà construit : *Actions → Deploy staging → Run workflow*.

## 6. Rollback

| Situation | Effet | Code |
|---|---|---|
| Refus ou échec avant changement (vérifications, téléchargement, sauvegarde) | rien n'a changé | 64 / 65 / 70 / 78 |
| Échec **sans migration nouvelle** (registre après = registre avant ; un migrateur en erreur annule sa transaction) | **rollback automatique** : `up` avec les **digests précédents** (`current.json`), sans reconstruction, puis smoke tests ; `failed.json` | 2 |
| Échec **avec migration nouvelle**, premier déploiement, ou registre illisible | **arrêt sûr** : `backend`, workers et `frontend` arrêtés ; PostgreSQL, Redis, stockage et sauvegardes intacts ; `failed.json` | 3 |

Jamais de retour automatique d'images sur un schéma plus récent : c'est une décision humaine (§7).

## 7. Récupération supervisée (après un arrêt sûr)

Sur le serveur, par edusyncadmin (les fichiers sont root-owned) :

```bash
sudo cat /var/lib/edusync-deploy/failed.json /var/lib/edusync-deploy/current.json     # SHA, digests, migrations nouvelles
P="sudo docker compose --project-name edusync-staging --project-directory /etc/edusync-deploy/compose --env-file /etc/edusync-deploy/staging.env -f /etc/edusync-deploy/compose/docker-compose.yml -f /etc/edusync-deploy/compose/compose.digests.yml"
# digests précédents (current.json) :
export EDUSYNC_BACKEND_IMAGE=ghcr.io/danielkikunda/edusync-backend@sha256:<...> EDUSYNC_FRONTEND_IMAGE=ghcr.io/danielkikunda/edusync-frontend@sha256:<...> EDUSYNC_BACKUP_IMAGE=ghcr.io/danielkikunda/edusync-backup@sha256:<...>
$P exec backup ls /backups                                   # dossier horodaté pris juste avant la mise à jour
$P exec postgres sh -c 'dropdb -U "$POSTGRES_USER" --if-exists edusync_restore && createdb -U "$POSTGRES_USER" edusync_restore'
$P exec backup sh -c 'pg_restore --exit-on-error --no-owner -d edusync_restore /backups/<horodatage>/db.dump'
# vérifier edusync_restore, basculer (renommer les bases), recopier /backups/<horodatage>/objects si besoin, puis :
$P up --detach --no-build --pull never
```

Revenir volontairement à une version : *Run workflow* avec ce SHA, seulement s'il n'existe pas de migration plus
récente ; sinon cette procédure. `sudo -E` n'est pas nécessaire : exporter les variables dans un shell root
(`sudo -i`) si la politique sudo de l'administrateur les filtre.

## 8. Rotation et révocation de la clé de déploiement

* **Révocation immédiate** (clé compromise) : `sudo truncate -s 0 ~deploy/.ssh/authorized_keys` (le fichier est
  root-owned) ou `sudo usermod --expiredate 1 deploy` ; supprimer le secret `STAGING_SSH_KEY` sur GitHub ; lire
  `/var/log/edusync-deploy/deploy.log` et `journalctl -u ssh` pour vérifier les usages.
* **Rotation** : générer une nouvelle paire hors du serveur (`ssh-keygen -t ed25519 -C github-actions-edusync-staging`),
  remplacer le contenu de `authorized_keys` par la seule nouvelle clé publique (sans options), relancer
  l'installateur (il remet `restrict,command=…` et root:root 0644), remplacer `STAGING_SSH_KEY` sur GitHub, lancer un
  *Run workflow* de contrôle, détruire l'ancienne clé privée.
* **Désinstallation** : supprimer `/etc/sudoers.d/edusync-deploy` (puis `visudo -c`) et vider `authorized_keys` ;
  les conteneurs, volumes et sauvegardes du projet `edusync-staging` ne sont pas touchés.

## 9. Sécurité de la chaîne

Actions officielles `actions/*` et `docker/*` ; permissions minimales ; `StrictHostKeyChecking=yes`, clé supprimée
en fin de job ; aucun secret dans Git (`tools/ci/secret_patterns.py` à chaque CI) ; images reproductibles
(`requirements.lock`, `npm ci`). Tests : `test_deploy_least_privilege.py` exécute la vraie commande forcée sous bash
(refus d'injection, d'arguments, de SHA invalides, de jeton invalide, chemin positif) et le contrôleur contre un
serveur simulé (dépôt / CI / image / arm64 refusés, installation modifiable refusée, production refusée, verrou,
rollback sans migration, arrêt sûr avec migration, échec de sauvegarde sans changement, chemin PASS par digests).
Amélioration possible : épingler les actions par SHA de commit.
