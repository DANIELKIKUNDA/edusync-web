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
