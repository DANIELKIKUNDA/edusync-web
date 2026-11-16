# EduSync — mise en production (lot 2026-10)

## 1. Règle

Rien ne part en production automatiquement. Une version ne peut aller en production que si, **pour ce SHA exact** :
la CI est verte, le déploiement staging a réussi, le parcours de bout en bout staging (*E2E staging*) est vert.
Le workflow `.github/workflows/deploy-production.yml` le vérifie avant le moindre changement.

## 2. Une fois, par le propriétaire (réglages GitHub)

1. Settings → Environments → **New environment** → `production`.
2. **Required reviewers** : vous (et le second Manager). Chaque mise en production attendra votre clic « Approve ».
3. **Deployment branches** : `main` uniquement.
4. Quand le serveur de production existera : secrets `PRODUCTION_SSH_HOST`, `PRODUCTION_SSH_USER`,
   `PRODUCTION_SSH_KEY`, `PRODUCTION_SSH_KNOWN_HOSTS` (même modèle à moindre privilège que staging, CICD.md §3).
   Sans eux, le workflow s'arrête : « Production non configurée », aucun changement.

## 3. Mettre en production

Actions → *Deploy production* → **Run workflow** → SHA complet + confirmation `PRODUCTION <8 premiers caractères>`
→ contrôles automatiques → votre approbation → déploiement par la commande forcée `deploy <SHA>` : le contrôleur
sauvegarde, migre, teste, et **revient tout seul en arrière** si les tests échouent (CICD.md §6).

## 4. Revenir en arrière

Relancer *Deploy production* avec le SHA précédent. Exercice réel sur staging le 19/10/2026 par le pipeline officiel :
07ffcf6 → 09d9f48 en 76 s (ancienne version vérifiée servie), puis retour à 07ffcf6 en 74 s (vérifications PASS).
Règle des migrations : une migration ne fait qu'**ajouter** (tables, colonnes nullables, index) ; jamais de
suppression ni de renommage dans la même version que le code qui en dépend. Sinon le retour arrière s'arrête de façon
sûre (SAFE_STOP_MIGRATION_CHANGED) et passe en restauration supervisée (CICD.md §7). La certification CD le vérifie à
chaque CI (version précédente compatible).

## 5. Sécurité et capacité

* Scan passif OWASP ZAP de staging chaque semaine (*Security scan staging*). **Ne remplace pas** un audit de
  sécurité externe (pentest) avant l'ouverture au public : BUSINESS_DECISION_REQUIRED (prestataire, budget, date).
* Test de charge local (`tools/local/load_test.py`, 1 000 écoles) : voir docs/architecture/PLATFORM_DONE.md §Charge.
  L'API démarre `WEB_CONCURRENCY` processus (2 par défaut) : à ajuster au nombre de cœurs du serveur de production.

## 6. Livraison de l’application Docker Compose Coolify

Le workflow **Production Coolify**, lancé sur `main`, choisit le premier SHA admissible
parmi les 50 dernières CI réussies sur cette branche. Il présente le SHA exact avant
l’approbation. La sélection exige la publication des images, une exécution réelle du
déploiement staging et les deux étapes authentifiées de l’E2E pour ce même SHA.
Les anciens runs et étapes ignorées ne constituent aucune preuve.

Configuration à effectuer par le propriétaire, après essai sur une application Coolify isolée :

1. GitHub → Settings → Environments → `production` → **Required reviewers** :
   ajouter `DANIELKIKUNDA` et réserver les déploiements à `main`. Si le propriétaire doit
   lancer et approuver lui-même, laisser la possibilité d’approuver sa propre demande.
   Le workflow vérifie l’existence de son approbation explicite dans l’historique du run.
2. Dans Coolify, garder l’application production fixée au Compose prévu et désactiver
   le déploiement sur push. Créer un jeton limité à la lecture des déploiements,
   à la modification de la variable et au déclenchement sur l’application cible,
   selon les permissions disponibles dans la version installée. Si l’instance
   n’est joignable que depuis le réseau privé, utiliser un runner autorisé sur ce réseau.
3. Ajouter `COOLIFY_API_ORIGIN` (origine HTTPS, sans `/api/v1`), `COOLIFY_APP_UUID`
   et `COOLIFY_API_TOKEN` comme secrets de l’environnement `production`.
   L’application doit déjà disposer de sa variable `EDUSYNC_RELEASE_SHA`.
4. Actions → **Production Coolify** → **Run workflow** avec les champs vides.
   Contrôler le SHA proposé et le dernier état de sauvegarde avant d’approuver.
   Le job modifie uniquement `EDUSYNC_RELEASE_SHA`, déclenche l’application par UUID,
   attend la fin Coolify et contrôle le SHA public et `/health-api`.
5. En cas d’échec, attendre que Coolify ait terminé toute opération en cours.
   Pour revenir à un SHA certifié, lancer une nouvelle demande avec `rollback_sha`
   et `rollback_from` (SHA actuellement servi). Le retour exige une nouvelle approbation
   et des migrations, un script migrateur et un Compose identiques. Si le SHA public
   est illisible ou si ces fichiers diffèrent, appliquer la procédure de restauration
   supervisée de CICD.md, avec validation de la sauvegarde. Aucune restauration
   de données et aucun second déploiement ne sont déclenchés automatiquement.
