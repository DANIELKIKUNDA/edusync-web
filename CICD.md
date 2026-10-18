# EduSync — CI/CD (intégration continue et déploiement staging à moindre privilège)

État au 2026-10-18. La CD staging repose sur une commande forcée OpenSSH, une seule règle sudo sans argument et un
contrôleur root installé administrativement. Cette version corrige les six défauts bloquants relevés par la revue
préinstallation de Codex sur 077bc1c (§10). Aucun code métier modifié : `git diff 2ad66ef -- backend/src frontend/src`
est vide.

Fichiers : `.github/workflows/{ci.yml,deploy-staging.yml,cd-certification.yml}`, `deploy/staging/privileged/`
(`deploy-gate.sh`, `deploy_controller.py`, `compose.staging.yml`, `install_deploy_controller.sh`), harnais Linux
`tools/ci/cd_linux/`, tests `backend/tests/test_deploy_least_privilege.py` et `backend/tests/test_cicd_contracts.py`.

## 1. Modèle de menace et frontière de confiance

| Menace | Réponse |
|---|---|
| Vol de la clé SSH de GitHub Actions, runner ou workflow compromis | La clé ne permet **que** `deploy <SHA>` : `ForceCommand` côté sshd **et** `restrict,command=` dans la clé, aucun shell, SCP, SFTP, redirection ni TTY. Seul un SHA du dépôt dont la CI a réussi sur `main` ou un tag `edusync-*` est accepté, avec les images de cette CI. Pire cas : redéployer une version déjà validée (§7). |
| `deploy` modifie sa propre restriction (renommer ou remplacer `.ssh`, lien symbolique, autre clé) | La clé autorisée est hors du répertoire personnel, dans `/etc/ssh/edusync-deploy/authorized_keys` ; toute la chaîne `/`, `/etc`, `/etc/ssh`, `/etc/ssh/edusync-deploy` est root-owned. Le répertoire personnel et `~/.ssh` deviennent root-owned, et sshd ignore les clés qui y sont déposées. |
| Accès Docker = root | `deploy` n'est **pas** dans le groupe `docker` et n'a aucun sudo général. Seul le contrôleur root parle à Docker, avec des arguments qu'il construit lui-même. |
| Injection dans la commande SSH | `SSH_ORIGINAL_COMMAND` est seulement comparé à `^deploy [0-9a-f]{40}$`, jamais exécuté ni évalué. |
| Image substituée, `latest` ou mauvaise architecture | Images applicatives : trois dépôts GHCR fixés dans le code, référence = SHA, index multi-architecture avec `linux/arm64` (le VPS), résolution en **digest**. Images d'infrastructure : liste fixe dans le contrôleur, version **et** digest. Compose ne télécharge ni ne construit jamais (`pull_policy: never`, `--no-build`). |
| Script ou fichier d'un commit exécuté par root | L'installateur est lancé par un administrateur depuis un checkout relu. Le contrôleur n'exécute rien venant du commit déployé et refuse un compose installé qui ne correspond pas exactement à la pile attendue (§2). |
| Fuite du jeton de registre | `GITHUB_TOKEN` éphémère du run (lecture seule) transmis par l'entrée standard. Il n'apparaît jamais dans les arguments ni dans les journaux, et ne quitte jamais un `DOCKER_CONFIG` temporaire root 0700, supprimé dans tous les cas. |
| Atteinte à Coolify, Tailscale, AtelierPro ou un autre projet | Projet compose fixé à `edusync-staging`, aucun `prune`, aucune action hors de ce projet. Seuls les ports `127.0.0.1:18080` et `<IP publique>:80/443` (périphérie) sont publiés. Le contrôleur refuse si un port ou le sous-réseau est déjà pris (§4). |
| Mise à jour qui casse la base | Sur une installation existante : PostgreSQL, registre des migrations valide et sauvegarde vérifiée **obligatoires** avant tout changement (fail closed). Rollback seulement si le registre est **exactement** identique, sinon arrêt sûr. |

```
GitHub Actions (non fiable pour le serveur)            Serveur staging
──────────────────────────────────────────            ───────────────────────────────────────────────────────────────
ssh deploy@staging "deploy <SHA>"  ── clé dédiée ──▶  sshd : drop-in « Match User deploy » (root-owned)
   + GITHUB_TOKEN sur stdin                              AuthorizedKeysFile /etc/ssh/edusync-deploy/authorized_keys
                                                         ForceCommand /usr/local/libexec/edusync/deploy-gate
                                                         │ compte deploy : aucun groupe docker, aucun sudo général,
                                                         │ répertoire personnel root-owned
                                                         ▼
                                                      deploy-gate (root:root 0755) : analyse, ne s'exécute jamais
                                                         │ sudo -n <contrôleur>  — sans argument, données sur stdin
                                ═══════════ élévation unique ═══════════
                                                         ▼
                                                      deploy-controller (root, #!/usr/bin/python3 -IS, environnement
                                                      vidé, verrou exclusif) → API GitHub, GHCR, Docker Hub (images
                                                      épinglées), docker compose -p edusync-staging, /etc, /var/lib
```

## 2. Commande forcée, sudo et contrôleur

**Commande forcée** (`deploy-gate`). Elle accepte exactement `deploy <SHA de 40 caractères hexadécimaux minuscules>`,
et répond 64 à tout le reste : SHA court, majuscules, espaces, arguments en plus, `;`, `&&`, `|`, `$( )`, accents
graves, retour à la ligne, autre verbe, chemin. Elle lit une seule ligne bornée sur l'entrée standard (300 octets,
15 s) : le jeton. Puis elle lance `exec /usr/bin/sudo -n deploy-controller`, avec `PATH` fixé, et transmet le SHA et
le jeton sur l'entrée standard.

**Règle sudo** (`/etc/sudoers.d/edusync-deploy`, vérifiée par `visudo`). `""` interdit tout argument ; aucun autre droit :

```
Defaults!/usr/local/libexec/edusync/deploy-controller env_reset, !setenv, secure_path="/usr/sbin:/usr/bin:/sbin:/bin", !requiretty
deploy ALL=(root) NOPASSWD: /usr/local/libexec/edusync/deploy-controller ""
```

**Shebang** : `#!/usr/bin/python3 -IS`. Linux transmet tout ce qui suit l'interpréteur comme **un seul** argument, donc
l'ancien `-I -S` ne démarrait pas. `-IS` est une seule option combinée : mode isolé (ni `PYTHON*` ni répertoire du
script dans le chemin) et pas de `site` (pas de `.pth`). Le harnais Linux vérifie ce comportement sur le fichier
installé (§9).

**Contrôleur**, étapes dans l'ordre :

1. **Requête.** Le contrôleur refuse tout argument, vide l'environnement, applique `umask 077` et prend le verrou
   exclusif `/run/edusync-deploy.lock` (75 s'il est déjà pris). L'entrée standard doit faire au plus 1 Kio et contenir
   exactement deux lignes ASCII (64 sinon).
2. **Installation.** Tout ce que root exécute ou lit doit appartenir à root et n'être modifiable par aucun autre
   compte, et `staging.env` doit être en 0600 (78 sinon). `staging.env` doit contenir `EDUSYNC_ENV=staging`. Avec le
   profil TLS, il faut aussi une `EDUSYNC_PUBLIC_BIND_ADDRESS` valide et un `EDUSYNC_DOMAIN`.
3. **Commit et CI.** Par l'API GitHub, le SHA doit être un commit de `DANIELKIKUNDA/edusync-web`. Il faut aussi un
   run du workflow `.github/workflows/ci.yml`, déclenché par un `push`, sur `main` ou un tag `edusync-*` de ce dépôt,
   réussi pour ce SHA exact (65 sinon).
4. **Images applicatives.** `ghcr.io/danielkikunda/{edusync-backend,edusync-frontend,edusync-backup}:<SHA>` doivent
   être des index multi-architecture contenant `linux/arm64` et la plateforme de l'hôte (65 sinon). Leurs digests sont
   conservés.
5. **Contrôles préalables**, en lecture seule :
   - le compose installé, résolu avec `staging.env` (`docker compose config`), doit contenir **exactement** les
     services attendus, avec les images choisies par le contrôleur ;
   - aucun service privilégié ni `network_mode: host`, aucun montage hôte hors de `/etc/edusync-deploy/compose` ;
   - ports publiés exactement conformes au §4 (78 sinon) ;
   - ports et sous-réseau `172.30.57.0/24` libres ou déjà tenus par EduSync (73 sinon).
6. **Hôte vierge ou installation existante** (§5).
7. **Téléchargement** par digest, à la plateforme de l'hôte, avec `docker login --password-stdin` puis `logout` :
   - les images de la nouvelle version, **et** celles de la version précédente (cible du rollback) ;
   - les images d'infrastructure épinglées ;
   - vérification de la présence et de la plateforme de chaque image.

   Échec : 70, rien n'a changé.
8. **Sauvegarde** vérifiée juste avant le changement, si l'installation existe (71 sinon). Écriture de `attempt.json`.
9. **Changement** : `docker compose --project-name edusync-staging --project-directory /etc/edusync-deploy/compose
   --env-file /etc/edusync-deploy/staging.env -f docker-compose.yml -f compose.staging.yml up --detach --no-build
   --pull never --remove-orphans`. Le migrateur s'exécute avant l'API, en une transaction.
10. **Smoke tests** :
    - API saine et migrateur terminé avec le code 0 ;
    - tous les services en marche, aucun en boucle de redémarrage (vérifié encore 20 s plus tard) ;
    - `assert_runtime_safe` en staging, dans le conteneur ;
    - `/`, `/health-api` et `/api/v1/setup/status` servis via `127.0.0.1:18080` ;
    - puis lecture du registre des migrations.
11. **Verdict** (§6).

Journal : `/var/log/edusync-deploy/deploy.log`, sans jeton, avec une ligne `VERDICT=<NOM>`. État :
`/var/lib/edusync-deploy/` contient `current.json`, `previous.json`, `ledger.json` (dernier registre observé),
`attempt.json`, `failed.json` et `last_result.json`.

## 3. Installation administrative (une fois, par edusyncadmin)

Prérequis déjà en place : compte `deploy` sans mot de passe, shell `/bin/bash`, hors du groupe `docker`, sans sudo. Son
`~deploy/.ssh/authorized_keys` contient **une seule** clé publique, celle de GitHub Actions. Il faut aussi
`docker compose` ≥ 2.24.4 et un sshd qui inclut `/etc/ssh/sshd_config.d/*.conf` (par défaut sur Debian et Ubuntu).

**À ne lancer qu'après l'accord explicite de Codex sur ce commit.**

```bash
git clone https://github.com/DANIELKIKUNDA/edusync-web.git ~/edusync-infra      # checkout relu
git -C ~/edusync-infra checkout --detach <SHA approuvé pour l'infrastructure>
sudo bash ~/edusync-infra/deploy/staging/privileged/install_deploy_controller.sh
sudoedit /etc/edusync-deploy/staging.env       # secrets générés (CODEX_STAGING_HANDOFF.md §3), EDUSYNC_ENV=staging, §4
```

L'installateur est idempotent et n'embarque aucun secret. Il refuse un état inattendu :
- `deploy` dans le groupe `docker`, ou shell absent ;
- plusieurs clés, ou une commande forcée étrangère ;
- `python3 -IS` indisponible, ou compose trop ancien.

| Chemin | Propriétaire / mode |
|---|---|
| `/usr/local/libexec/edusync/{deploy-gate,deploy-controller}` | root:root 0755 |
| `/etc/edusync-deploy/` (`INSTALLED_FROM` = SHA de l'infrastructure) | root:root 0700 |
| `/etc/edusync-deploy/compose/` (`docker-compose.yml`, `compose.staging.yml`, `deploy/seaweedfs/entrypoint.sh`, `deploy/caddy/Caddyfile`) | root:root 0755 / 0644 |
| `/etc/edusync-deploy/staging.env` (créé depuis `.env.example`, conservé s'il existe) | root:root 0600 |
| `/var/lib/edusync-deploy/` (état), `/var/log/edusync-deploy/` (journaux) | root:root 0700 / 0750 |
| `/etc/sudoers.d/edusync-deploy` | root:root 0440 |
| `/etc/ssh/edusync-deploy/authorized_keys` : `restrict,command="/usr/local/libexec/edusync/deploy-gate",<options existantes> <clé>` | root:root 0644 (répertoire 0755) |
| `/etc/ssh/sshd_config.d/edusync-deploy.conf` (`Match User deploy` : `AuthorizedKeysFile`, `ForceCommand`, `DisableForwarding`, `PermitTTY no`, `PermitUserRC no`, `AuthenticationMethods publickey`…) | root:root 0644 |
| `~deploy`, `~deploy/.ssh` (l'ancien `authorized_keys` est remplacé par un commentaire ignoré) | root:root 0755 |

**SSH sans modification globale.** Le fichier principal `sshd_config` n'est jamais touché, et le drop-in ne s'applique
qu'à `deploy`. L'installateur compare la configuration effective de `root`, `nobody` et de l'administrateur
(`sshd -T -C user=…`) avant et après : à la moindre différence, `sshd -t` en échec ou directive non effective pour
`deploy`, le drop-in est retiré et l'installation refusée. sshd est ensuite rechargé
(`systemctl try-reload-or-restart ssh`), ce qui ne coupe pas les sessions ouvertes.

Changer l'infrastructure (compose, contrôleur, versions des images d'infrastructure) revient à relancer l'installateur
depuis un checkout relu. Un commit applicatif ne la modifie jamais.

## 4. Ports, HTTPS public et cohabitation avec le VPS

Audit du VPS : `127.0.0.1:8000` = Coolify, Tailscale = `100.120.8.56:443`, aucune écoute publique 80/443.

| Service | Publication sur l'hôte |
|---|---|
| `tls-proxy` (Caddy, profil `tls`) — **seul propriétaire du HTTPS public** | `<EDUSYNC_PUBLIC_BIND_ADDRESS>:80` et `:443` uniquement |
| `frontend` (nginx) | `127.0.0.1:18080` (boucle locale, smoke tests du contrôleur) |
| `backend`, `postgres`, `redis`, `object-storage`, `backup`, workers | **aucune** (réseau interne `172.30.57.0/24`) |

- `staging.myeducsync.com` → DNS A vers l'IP publique → Caddy EduSync (Let's Encrypt, HSTS) → `frontend:80` → API.
  Dans `staging.env` :
  ```
  EDUSYNC_DEPLOY_TLS_PROFILE=true
  EDUSYNC_DOMAIN=staging.myeducsync.com
  EDUSYNC_PUBLIC_BIND_ADDRESS=<IPv4 de l'interface publique, souvent l'adresse privée de la carte si l'hébergeur fait du NAT 1:1>
  ```
  Ajouter `staging.myeducsync.com` en tête de `EDUSYNC_TRUSTED_HOSTS` et `https://staging.myeducsync.com` dans
  `EDUSYNC_CORS_ORIGINS` et `EDUSYNC_PUBLIC_APP_URL`.
- **Jamais `0.0.0.0:443`.** Docker redirigerait (DNAT) le 443 de *toutes* les adresses, dont celle de Tailscale. Le
  contrôleur refuse `0.0.0.0`, la boucle locale, `100.64.0.0/10` (Tailscale) et le lien local. Il refuse aussi une
  adresse absente de l'hôte.
- **Coolify** : `127.0.0.1:8000` n'est plus utilisé par EduSync (l'API ne publie plus rien). Coolify ne doit pas
  démarrer son proxy sur 80/443 de l'adresse publique : si c'était le cas, le contrôleur refuserait avec
  `PORT_CONFLICT` sans rien toucher.
- **Contrôle préalable à chaque déploiement.** Un port nécessaire déjà publié par un conteneur d'un autre projet, ou
  tenu par un processus qui n'est pas EduSync, donne `PORT_CONFLICT` (73). Il en va de même pour un réseau Docker d'un
  autre projet qui chevauche `172.30.57.0/24`.

## 5. Hôte vierge, sauvegarde et registre des migrations (fail closed)

- **Hôte vierge, reconnu explicitement** : aucun volume Docker du projet `edusync-staging`, aucun conteneur du projet,
  aucun état enregistré (`current`, `ledger`, `attempt`). C'est le seul cas sans sauvegarde ni registre préalables.
  Toutes les images (EduSync et infrastructure) sont téléchargées par le contrôleur avant le premier `compose up`.
- **Installation existante** (tout autre cas, y compris des volumes sans état, ou un état sans volume) :

  | Situation | Refus |
  |---|---|
  | PostgreSQL arrêté | `LEDGER_REQUIRED_FAILED` (72) |
  | Registre absent, vide, illisible, doublonné ou désordonné | 72 |
  | Registre différent du dernier registre enregistré par le contrôleur | 72 |
  | Service de sauvegarde indisponible | `BACKUP_REQUIRED_FAILED` (71) |
  | Sauvegarde en échec | 71 |
  | Restauration de contrôle absente ou en échec (`last.json` sans `ok` et `restore_verified`) | 71 |

  Dans chacun de ces cas, rien n'a changé.

## 6. Verdicts, codes de sortie et rollback

| Code | Verdict | Signification |
|---|---|---|
| 0 | `DEPLOY_SUCCESS` | déployé et vérifié |
| 2 | `ROLLBACK_SUCCESS` | échec, registre **exactement** identique : retour aux digests précédents (sans reconstruction), smoke tests du rollback PASS, registre inchangé |
| 3 | `SAFE_STOP_MIGRATION_CHANGED` | échec, registre différent (ajout, suppression, modification, ordre) ou illisible : API, workers et frontend arrêtés ; base, volumes et sauvegarde intacts |
| 4 | `ROLLBACK_FAILED` | rollback effectué **mais** ses smoke tests ont échoué (ou registre modifié pendant le rollback) : application arrêtée, données intactes — jamais présenté comme un succès |
| 5 | `SAFE_STOP_NO_ROLLBACK_TARGET` | échec du premier déploiement, ou installation sans version précédente connue : arrêt sûr |
| 64 | `REQUEST_REFUSED` | requête refusée (commande forcée ou contrôleur) |
| 65 | `VERIFICATION_REFUSED` | dépôt, CI ou images refusés |
| 70 | `PRE_CHANGE_FAILED` | échec avant tout changement (téléchargement, plateforme) |
| 71 | `BACKUP_REQUIRED_FAILED` | sauvegarde vérifiée impossible sur une installation existante : rien n'a changé |
| 72 | `LEDGER_REQUIRED_FAILED` | registre des migrations absent, illisible, incohérent ou divergent : rien n'a changé |
| 73 | `PORT_CONFLICT` | port ou sous-réseau occupé par un service hors EduSync : rien n'a changé |
| 75 | `DEPLOY_IN_PROGRESS` | un autre déploiement est en cours |
| 78 | `UNSAFE_INSTALLATION` | installation non sûre, environnement non staging ou compose installé inattendu |

Jamais de retour automatique d'images sur un schéma différent : c'est une décision humaine (§7).

## 7. Récupération supervisée (après 3, 4 ou 5)

Sur le serveur, par edusyncadmin (les fichiers sont root-owned) :

```bash
sudo cat /var/lib/edusync-deploy/last_result.json /var/lib/edusync-deploy/failed.json /var/lib/edusync-deploy/current.json
sudo tail -50 /var/log/edusync-deploy/deploy.log
```

- **Redéployer une version saine**, si le registre n'a pas changé (cas 4) : *Actions → Deploy staging → Run
  workflow* avec le SHA voulu.
- **Restaurer la sauvegarde d'avant mise à jour** (cas 3) :

  ```bash
  sudo -i
  P="docker compose --project-name edusync-staging --project-directory /etc/edusync-deploy/compose --env-file /etc/edusync-deploy/staging.env -f /etc/edusync-deploy/compose/docker-compose.yml -f /etc/edusync-deploy/compose/compose.staging.yml"
  # images : digests de current.json pour EduSync, liste INFRA_IMAGES de /usr/local/libexec/edusync/deploy-controller
  export EDUSYNC_BACKEND_IMAGE=ghcr.io/danielkikunda/edusync-backend@sha256:<...> EDUSYNC_FRONTEND_IMAGE=... EDUSYNC_BACKUP_IMAGE=... \
         EDUSYNC_POSTGRES_IMAGE=... EDUSYNC_REDIS_IMAGE=... EDUSYNC_OBJECT_STORAGE_IMAGE=... EDUSYNC_TLS_PROXY_IMAGE=... EDUSYNC_PUBLIC_BIND_ADDRESS=...
  $P exec backup ls /backups                                   # dossier horodaté pris juste avant la mise à jour
  $P exec postgres sh -c 'dropdb -U "$POSTGRES_USER" --if-exists edusync_restore && createdb -U "$POSTGRES_USER" edusync_restore'
  $P exec backup sh -c 'pg_restore --exit-on-error --no-owner -d edusync_restore /backups/<horodatage>/db.dump'
  # vérifier edusync_restore, basculer (renommer les bases), recopier /backups/<horodatage>/objects si besoin, puis :
  $P up --detach --no-build --pull never
  ```

  Ensuite, mettre `ledger.json` en accord avec la base restaurée :
  `{"versions": [...]}` = sortie de `SELECT version FROM schema_migrations ORDER BY version`. Sans cela, le
  contrôleur refusera le déploiement suivant (72), et c'est voulu.
- **Correctif vers l'avant** après un arrêt sûr dû à une migration nouvelle : `ledger.json` contient déjà le registre
  observé. Un nouveau SHA incluant ces migrations se déploie normalement, avec une sauvegarde obligatoire.

## 8. Rotation et révocation de la clé de déploiement

- **Révocation immédiate** (clé compromise) :
  ```bash
  sudo truncate -s 0 /etc/ssh/edusync-deploy/authorized_keys
  ```
  Ou bien `sudo usermod --expiredate 1 deploy`. Ensuite, supprimer `STAGING_SSH_KEY` sur GitHub et lire
  `/var/log/edusync-deploy/deploy.log` et `journalctl -u ssh`.
- **Rotation** :
  1. Générer une nouvelle paire hors du serveur :
     ```bash
     ssh-keygen -t ed25519 -C github-actions-edusync-staging
     ```
  2. Écrire la seule nouvelle clé publique, sans options, dans `/etc/ssh/edusync-deploy/authorized_keys`.
  3. Relancer l'installateur : il remet `restrict,command=…` en root:root 0644.
  4. Remplacer `STAGING_SSH_KEY` sur GitHub, puis lancer un *Run workflow* de contrôle.
  5. Détruire l'ancienne clé privée.
- **Désinstallation** :
  - supprimer `/etc/sudoers.d/edusync-deploy` (puis `visudo -c`) et `/etc/ssh/sshd_config.d/edusync-deploy.conf` ;
  - vider `/etc/ssh/edusync-deploy/authorized_keys` ;
  - recharger sshd.

  Les conteneurs, volumes et sauvegardes du projet `edusync-staging` ne sont pas touchés.

## 9. Certification

| Niveau | Où | Ce qui est réellement exercé |
|---|---|---|
| Tests unitaires | `backend/tests/test_deploy_least_privilege.py` (CI `backend`) | Commande forcée exécutée par bash : refus et chemin positif. Contrôleur contre un hôte Docker, l'API GitHub et GHCR simulés avec état : hôte vierge, images d'infrastructure, ports et réseau, sauvegarde et registre en fail closed, rollback avec registre exact, `ROLLBACK_FAILED`, verdicts |
| Linux réel, à chaque CI | job `cd-privileged`, `tools/ci/cd_linux/privileged_checks.sh` | Installation réelle et idempotente. Propriétaires et modes, sudoers effectif. Exécution du contrôleur installé par son shebang (`/proc/<pid>/cmdline` = `/usr/bin/python3 -IS …`), PYTHONPATH piégé et `.pth` ignorés, ancien shebang défaillant. sshd effectif. Via le vrai sshd : refus (sans commande, `id`, SHA invalide, argument en plus, injections, jeton absent, SCP, SFTP, `-L`, `-R`) et chemin positif jusqu'au contrôleur root. Tentatives de `deploy` (renommer ou remplacer `.ssh`, `authorized_keys`, liens symboliques, fichiers privilégiés). Clé plantée dans `~/.ssh` ignorée. `ForceCommand` actif même sans options dans la clé. Verrou concurrent. Installation altérée et production refusées |
| Linux réel, pile complète, après chaque CI réussie sur `main` | `cd-certification.yml`, `tools/ci/cd_linux/stack_scenarios.sh` | Images réelles de deux commits certifiés, vrais PostgreSQL, Redis, SeaweedFS et sauvegarde : hôte vierge → `PORT_CONFLICT` → premier déploiement → `ROLLBACK_SUCCESS` → `BACKUP_REQUIRED_FAILED` → registre divergent, illisible ou absent (72) → `ROLLBACK_FAILED` → reprise. Un conteneur témoin « Coolify » sur `127.0.0.1:8000` reste intact |

Non exercé en CI, faute de VPS : `linux/arm64` natif (les images arm64 sont construites et vérifiées dans l'index ; les
scénarios tournent en amd64 natif) et un vrai certificat Let's Encrypt (profil `tls`, couvert par les contrôles de
configuration).

## 10. Corrections de la revue Codex sur 077bc1c

| # | Défaut | Correction |
|---|---|---|
| 1 | `~deploy` modifiable par `deploy` : substitution de `.ssh` possible | Clé dans `/etc/ssh/edusync-deploy/` (chaîne root-owned), drop-in `Match User deploy` (`AuthorizedKeysFile`, `ForceCommand`…), répertoire personnel root-owned, configuration des autres comptes vérifiée identique |
| 2 | Shebang `-I -S` non exécutable sous Linux | `#!/usr/bin/python3 -IS`, vérifié sur le fichier installé |
| 3 | Images d'infrastructure absentes sur un VPS vierge (`--pull never`) | Liste fixe version + digest (`linux/arm64` vérifié) pour PostgreSQL, Redis, SeaweedFS et Caddy, téléchargées par le contrôleur avant le premier `up` ; compose installé vérifié image par image |
| 4 | Collisions 127.0.0.1:8000 (Coolify) et 0.0.0.0:443 (Tailscale) | API non publiée, nginx sur `127.0.0.1:18080`, HTTPS public uniquement par Caddy sur l'adresse publique ; refus préalable des ports et sous-réseaux occupés |
| 5 | Sauvegarde et registre non obligatoires | Fail closed (§5) ; hôte vierge reconnu séparément |
| 6 | Rollback sur « pas de nouvelle migration » et `ROLLBACK_SUCCESS` même si le rollback échoue | Égalité exacte du registre ; verdicts distincts, dont `ROLLBACK_FAILED` (§6) |

## 11. Sécurité de la chaîne

- Actions officielles `actions/*` et `docker/*`, permissions minimales.
- `StrictHostKeyChecking=yes` ; la clé est supprimée en fin de job.
- Aucun secret dans Git : `tools/ci/secret_patterns.py` à chaque CI. Les harnais génèrent leurs secrets de test sur
  le runner sans les afficher.
- Images reproductibles : `requirements.lock`, `npm ci`.
- Amélioration possible : épingler les actions par SHA de commit.
