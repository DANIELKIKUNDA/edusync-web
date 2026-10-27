# EduSync Web — CI/CD de secours avant le 01/11/2026

**Date : 27/10/2026.** Objectif : préserver les contrôles techniques en cas de blocage de facturation de GitHub Actions. **Aucun contournement des règles de sécurité, aucun déploiement automatique, aucune mise en production sans décision du propriétaire.**

## Diagnostic constaté sur GitHub

- Dépôt : `DANIELKIKUNDA/edusync-web` (privé), branche principale `main`.
- Au 27/10 à 13:11 UTC : la CI des PR remonte `failure` pour les jobs backend, frontend, RBAC et sécurité. Les workflows `Deploy staging`, `E2E staging` et `CD certification` sont majoritairement `skipped`.
- La facturation GitHub Actions bloquée est **signalée par le propriétaire**. L'origine précise de chaque run défaillant n'a pas encore été certifiée par les journaux.
- Le pipeline existant requiert des runs CI `success` sur le SHA **exact**, des images GHCR `amd64+arm64`, une validation staging et un E2E staging vert avant production.
- Le contrôleur de déploiement installé sur le VPS **vérifie lui-même ces preuves**. Une simple commande SSH ou un exécuteur local ne les remplace pas. **Ne pas supprimer ces vérifications.**

## Nouveau constat d'infrastructure (diagnostic utilisateur du 27/10)

Observations sur le VPS `ubuntu-8gb-nbg1-2` :

- ARM64, 4 CPU, **7,5 Gio de RAM totale, 5,8 Gio disponibles**, **0 swap**.
- Disque : **53 Go libres** sur le volume racine.
- Docker accessible en lecture avec `sudo`, mais pas directement sous `edusyncadmin`.
- **13 conteneurs actifs** comprenant `edusync-staging-*`, PostgreSQL/Redis, Coolify et ses dépendances.
- Le backend staging a été observé `healthy` ; cela ne certifie pas les flux métier complets.

**Décision de sécurité : serveur partagé = PAS de CI lourde ici.** La RAM disponible à un instant donné n'est pas une réservation. Avec 0 swap, Chromium et les migrations pourraient affecter staging/Coolify. Ne pas ajouter `edusyncadmin` au groupe `docker` du VPS : cet accès est pratiquement équivalent à root.

Le nouveau `tools/ci/fallback_assert_ci_host.sh` est appelé par `fallback_local.sh`, `fallback_poll.sh` et `fallback_build_images.sh`. Il **refuse** les opérations lourdes si Docker n'est pas accessible au compte CI non-root ou si au moins un conteneur fonctionne déjà sur cet hôte. En particulier, les 13 conteneurs staging/Coolify provoqueront un refus sûr, **sans tentative de les arrêter**.

Ce garde-fou protège le serveur contre une erreur d'installation. Utiliser un hôte CI exclusif pour exécuter les suites, et le VPS actuel uniquement comme destination staging du mécanisme CD déjà certifié.

## 1. Premier secours : tests locaux isolés, sans GitHub Actions

`tools/ci/fallback_local.sh` reproduit sur une machine Linux de test autorisée :

- Python 3.13 : dépendances verrouillées, compilation et tests backend ;
- PostgreSQL 16 éphémère : migrations 0084/0085, snapshots RBAC, registre et intégration caisse ;
- contrôles de sécurité : empreintes, licences/SBOM, `pip-audit` ;
- Node.js 24 : installation `npm ci`, TypeScript, Vitest, navigateur Chromium et build, `npm audit`.

Il utilise des **conteneurs Docker temporaires** limités en CPU/RAM, un réseau Docker propre, **aucun port publié**, **aucune base ni volume de production** et n'effectue jamais `docker prune`. Il refuse de commencer si moins de 4 Gio RAM disponibles ou 12 Gio libres dans `/tmp`. L'architecture ARM64 du VPS peut empêcher les tests Chromium : ce cas doit apparaître **FAIL/BLOCKED**, jamais PASS. Les images, dépendances et navigateurs téléchargés consomment de l'espace disque et de la bande passante.

**Privilégier un hôte de CI dédié.** Sur le VPS de staging 8 Gio partagé avec Coolify et d'autres services, auditer d'abord la charge réelle : le script ne garantit pas l'absence de perturbation. Docker donne des privilèges élevés aux membres du groupe Docker ; seul du code relu provenant du dépôt officiel doit être exécuté.

Préparation par l'exploitant, **sans sudo** (SSH et accès privé GitHub déjà configurés) :

```bash
git clone git@github.com:DANIELKIKUNDA/edusync-web.git edusync-web-ci
cd edusync-web-ci
git fetch origin
git checkout infra/fallback-ci-20261027
# LECTURE SEULE : RAM, stockage, architecture, droit Docker :
bash tools/ci/fallback_preflight.sh
# Tester le SHA exact de main ; source immuable extraite avec git archive :
TARGET_SHA="$(git rev-parse origin/main)"
bash tools/ci/fallback_local.sh "$TARGET_SHA"
# Tester INDEPENDAMMENT le travail Prefet/Direction non fusionne :
git fetch origin chatgpt/prefet-directeur-certification
PREFET_SHA="$(git rev-parse origin/chatgpt/prefet-directeur-certification)"
bash tools/ci/fallback_local.sh "$PREFET_SHA"
```

Le test de la branche Préfet/Direction porte sur la version exacte du travail en cours et ne doit pas être confondu avec la certification de `main`. Le script marque explicitement `NOT_APPLICABLE` l'intégration d'isolation de sections lorsqu'un ancien SHA ne la contient pas ; il ne s'agit pas d'une preuve de réussite de cette intégration. Les rapports sont sous `~/edusync-ci-reports/<sha>-<date UTC>/` (fichiers en accès privé, à vérifier avant tout partage). Le répertoire contient `summary.txt`, `resultats.txt`, les journaux de chaque étape et les **résultats JSON/captures Playwright** conservés sous `ci-evidence/browser-dev` et `ci-evidence/browser-compiled` (ou `playwright-last-results` lorsque le test échoue avant la copie). Ces preuves sont privées sur la machine CI ; le seul statut GitHub n'en contient pas les fichiers.


### Autotests du publisher

Avant de lancer Docker, `fallback_local.sh` exécute le module `tools/ci/tests/test_fallback_github_status.py` en mode **hors réseau**. Ces tests vérifient notamment l'identifiant du commit, le contexte `external/edusync-ci`, le refus des jetons lisibles par d'autres utilisateurs et le comportement en cas de coupure réseau. Ils ne constituent **pas** des tests réels de l'API GitHub.

## 1 bis. Exécution périodique sans GitHub Actions (uniquement machine CI dédiée)

Pour obtenir une véritable vérification automatique **indépendante des minutes GitHub Actions**, le dépôt fournit maintenant `tools/ci/fallback_poll.sh` et des modèles systemd dans `tools/ci/systemd/`.

Le timer contrôle toutes les 10 minutes les changements approuvés sur `origin/main`, prend un verrou `flock`, puis lance `fallback_local.sh` **une fois par SHA**. Il conserve `~/edusync-ci-control/main.last_sha`, `main.last_result`, ainsi que les rapports `~/edusync-ci-reports/`. Les vérifications manuelles de la branche Préfet/Direction utilisent `chatgpt_prefet-directeur-certification.last_sha` et son propre `last_result` ; elles n'écrasent jamais l'état de `main`. Le même verrou empêche les deux contrôles de monopoliser simultanément la machine. Les exécutions qui échouent ne deviennent jamais PASS. Une interruption reste `IN_PROGRESS` jusqu'à un examen manuel ; il n'y a pas de redémarrage incontrôlé sur le même SHA.

**Prérequis et avertissements :**

- Machine Linux **dédiée à la CI**, indépendante du staging/production ; ne pas installer ce service sur le VPS Hetzner partagé sans analyse de capacité et décision explicite.
- SSH GitHub en **lecture seule** pour `edusync-ci` et accès au dépôt privé ; ne jamais enregistrer de token dans le dépôt ou l'unité systemd.
- Docker avec accès au démon depuis `edusync-ci`. **L'accès au groupe docker est équivalent à root sur la machine** : compte isolé sur hôte dédié uniquement. Aucune PR extérieure n'est exécutée par le poller.
- Chemin du checkout prévu par les unités : `/srv/edusync-ci/edusync-web`. Il faut créer le compte et le répertoire avec les bonnes permissions, y cloner le dépôt et sélectionner `infra/fallback-ci-20261027` pour les outils tant que la PR est en revue.
- Après installation manuelle par un administrateur du serveur de CI uniquement :

```bash
sudo install -m 0644 tools/ci/systemd/edusync-fallback-ci.service /etc/systemd/system/
sudo install -m 0644 tools/ci/systemd/edusync-fallback-ci.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now edusync-fallback-ci.timer
# Consultation des journaux (aucun effet sur les applications) :
sudo systemctl status edusync-fallback-ci.timer
sudo journalctl -u edusync-fallback-ci.service -n 50 --no-pager
```

La commande systemd ci-dessus ne doit être utilisée qu'une fois le compte de service et son checkout en place, sur un serveur de CI séparé, après revue. Aucun de ces services n'a été installé sur Hetzner dans cette session.

**Limite architecturale critique :** le poller est un **contrôle CI**. Il ne construit pas d'images multiarch, ne publie pas de statuts de réussite GitHub Actions et ne déclenche **aucun déploiement**. Le contrôleur staging officiel exige une CI GitHub réussie ; l'automate indépendant ne doit pas fabriquer ou contourner cette preuve. Pour une CD indépendante il faut spécifier une nouvelle chaîne de confiance auditable et tester un contrôleur compatible sur un hôte jetable, avant toute adoption.


## 1 ter. Préparation locale des images ARM64/AMD64 (facultative, après CI PASS)

`tools/ci/fallback_build_images.sh` peut construire les trois images backend/frontend/sauvegarde depuis le SHA exact après un **rapport de tests PASS**. Il n'accepte que `main` ou la branche officielle Préfet/Direction, n'utilise jamais de jeton de registre et n'effectue ni `docker push` ni déploiement. Il ne construit que pour **l'architecture native du démon Docker** ; ce n'est donc pas la sortie multi-architecture exigée par la CD officielle.

À exécuter **sur le même hôte CI dédié**, uniquement si le rapport du SHA est authentique, après audit de capacité disque (≥ 16 Gio libres) :

```bash
SHA="$(git rev-parse origin/main)"
# Prendre le chemin du dernier rapport PASS de ce SHA, sans fabriquer de résultat :
# Exemple de chemin réel : ~/edusync-ci-reports/0123456789ab-20261027T150000Z/summary.txt
bash tools/ci/fallback_build_images.sh "$SHA" "/chemin/reel/vers/summary.txt"
```

Le rapport contient les identifiants immuables locaux (`docker image inspect .Id`) et le SHA source. Aucune image issue de ce script ne doit être substituée manuellement aux images certifiées GHCR du contrôleur staging.

## 1 quater. Suivi depuis Claude, Codex et l'interface GitHub sans Actions

**Problème résolu au niveau protocole (non installé/testé sur Hetzner)** : pour qu'un assistant ou un développeur voie le résultat de la CI de secours **dans GitHub**, le poller peut publier un **statut de commit externe** via l'API REST GitHub. Cette API ne consomme pas de minutes GitHub Actions.

- Script : `tools/ci/fallback_github_status.py`.
- Contexte explicite : `external/edusync-ci` (distinct de la CI GitHub Actions officielle).
- Statuts : `pending` au début, puis `success` ou `failure` uniquement sur la base de l'exécution réelle de `fallback_local.sh` pour le SHA testé. En cas d'échec de publication, le poller enregistre `PASS_LOCAL_STATUS_UNPUBLISHED` ou `FAIL` ; jamais de faux succès distant.
- Les assistants Claude/Codex disposant d'accès GitHub au dépôt privé peuvent consulter ces statuts sur le commit SHA, dans la PR associée si GitHub les affiche, ou avec la ressource `GET /repos/DANIELKIKUNDA/edusync-web/commits/{sha}/status`. Les **journaux détaillés restent sur l'hôte CI** ; ne pas prétendre qu'ils sont accessibles dans GitHub. Un accès SSH autorisé ou une solution d'archivage de preuves privée est nécessaire pour lire les logs, captures et traces complets.
- **États reportés localement :** `PASS_LOCAL_UNPUBLISHED` (jeton absent), `PASS_LOCAL_REPORTED` (statut externe accepté par GitHub), `PASS_LOCAL_STATUS_UNPUBLISHED` (tests passés mais publication échouée), `FAIL` (tests échoués), `IN_PROGRESS` (tests commencés ou interrompus). Ces états ne représentent jamais la réussite du déploiement staging.

**Pour Préfet et Direction en cours de développement :** ne pas activer de timer supplémentaire qui s'exécuterait à chaque petit commit. Lorsque la branche est prête à être prévalidée, exécuter manuellement sur l'hôte CI isolé (après configuration du jeton et récupération du code de PR #30) :

```bash
cd /srv/edusync-ci/edusync-web
bash tools/ci/fallback_poll.sh "$PWD" chatgpt/prefet-directeur-certification
```

Ce déclenchement prend le SHA de la branche à cet instant, exécute la suite de secours, publie `external/edusync-ci` pour **ce SHA** et conserve les rapports. Il ne fusionne pas la PR #27. Sans jeton, l'exécution reste **locale uniquement**, aucun résultat distant n'est annoncé. Une nouvelle exécution au même SHA nécessite une intervention supervisée et l'examen du résultat précédent.

Le compteur GitHub Actions reste bloqué : ceci n'exécute pas les jobs `ci.yml`, ne produit pas les preuves de staging, n'édite pas les règles de protection de branche et **ne déverrouille pas le contrôleur de déploiement actuel**.

**Activation sur le serveur CI dédié UNIQUEMENT après revue du code :**

1. Créer dans GitHub un *fine-grained personal access token* limité au seul dépôt `DANIELKIKUNDA/edusync-web`, avec permission **Commit statuses: Read and write**. Garder la durée de vie minimale compatible avec le dépannage. Le token est destiné uniquement au signalement des statuts ; pas d'accès administration ou déploiement.
2. Créer **sur l'hôte CI**, sous le compte `edusync-ci`, le dossier `/srv/edusync-ci/.secrets/` mode 0700 et le fichier `/srv/edusync-ci/.secrets/github-status-token` mode **0600**, propriétaire `edusync-ci`. Saisir la valeur du token dans ce fichier par un éditeur sécurisé, **jamais dans ChatGPT, GitHub, un argument de commande ou un journal**. Éviter de conserver le jeton dans l'historique Bash.
3. L'unité `tools/ci/systemd/edusync-fallback-ci.service` contient uniquement le **chemin** du fichier, via `EDUSYNC_GITHUB_STATUS_TOKEN_FILE`, jamais le secret lui-même.
4. Installer/démarrer le timer systemd selon §1 bis, contrôler le journal et vérifier sous le SHA testé que GitHub affiche `external/edusync-ci`.

**Pour un contrôle manuel** : le script utilise la même variable d'environnement et reçoit `SHA`, l'état (`pending`, `success`, `failure`, `error`) et une courte description. **Ne jamais appeler directement `success` sans preuve d'une exécution réelle pour le SHA exact.** L'automate seul se charge de la transition d'état normale.

### Ce que Claude / Codex doivent faire

1. Récupérer le SHA exact du commit étudié.
2. Lire le statut `external/edusync-ci`. S'il est absent, afficher **NON EXÉCUTÉ OU NON PUBLIÉ**.
3. Vérifier que le statut correspond à ce SHA et que la couverture de la suite de secours suffit pour la décision demandée.
4. Pour audit complet, récupérer les logs/captures de la machine de CI via un accès autorisé (ou lancer les tests E2E sur leur environnement local).
5. Ne fusionner/déployer que lorsque toutes les exigences spécifiques de `CICD.md` et `PRODUCTION.md` sont elles aussi satisfaites ; le statut externe ne leur est pas équivalent.

## 2. Ce qui n'est pas résolu par le secours local

Le verdict du script ne vaut **pas** une certification de sortie en production. Restent impérativement :

1. Tester les scénarios CD privilégiés (sshd/sudo/contrôleur) **sur hôte Linux jetable** ; ne jamais lancer le harnais `tools/ci/cd_linux/privileged_checks.sh` sur le VPS réel.
2. Construire et publier les images Docker multi-architecture, avec SHA exact et digests GHCR.
3. Reprendre le **chemin de déploiement officiel** ou faire auditer une *voie alternative* apportant les mêmes garanties : origine/version immuable, preuves d'intégrité, contrôles de migrations, sauvegarde vérifiée, rollback, secrets à moindre privilège, staging puis E2E.
4. Configurer **un environnement de production distinct** et les approbations du propriétaire (`PRODUCTION.md`).
5. Tester HTTPS, DNS, sauvegarde/restauration hors-site, monitoring et parcours métier critiques, notamment isolation multi-écoles et caisse.

**Interdit :** transformer un échec de CI en succès artificiel, accepter un `latest`, désactiver la vérification de l'origine des images, pousser des secrets dans Git, lancer les tests privilégiés sur Coolify ou utiliser la base de production pour les migrations de CI.

## 3. Plan d'exécution / décision

| Date | Porte de sortie |
|---|---|
| 27/10 | Identifier la cause de la suspension GitHub, auditer la capacité du runner, exécuter le secours |
| 28/10 | Corriger les vrais tests échoués, certifier RBAC et finance PostgreSQL |
| 29/10 | Finaliser chaîne d'images et preuve de provenance, restaurations et isolation |
| 30/10 | Déployer en staging contrôlé, parcourir E2E et sécurité |
| 31/10 | Revue des preuves et décision **GO / NO-GO** de mise en production |
| 01/11 | Production **uniquement en cas de GO** ; sinon report ciblé |

Si GitHub Actions reste désactivé, établir séparément et **faire auditer** une CI/CD réellement indépendante, au lieu de supprimer les garde-fous du contrôleur existant. Cette PR prépare seulement les tests locaux : elle n'autorise pas le déploiement.

## Références dans le dépôt

- `CICD.md` : modèle de menace et contrôleur de déploiement ;
- `PRODUCTION.md` : gates de mise en production, validation du propriétaire ;
- `.github/workflows/ci.yml`, `deploy-staging.yml`, `e2e-staging.yml`, `deploy-production.yml` ;
- `CODEX_STAGING_HANDOFF.md` : contraintes d'infrastructure et configuration staging.

**État : non exécuté sur Hetzner par l'auteur du correctif.** Exiger les journaux réels avant de déclarer la CI validée.
