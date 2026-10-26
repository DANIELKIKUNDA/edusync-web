# Gestionnaire — audit d'intégration et reprise (26 octobre 2026)

## Statut

**Remplacé par `docs/certification/GESTIONNAIRE_CERTIFICATION_FINALE.md` (26/10/2026).** Historique : Ce document est une matrice de traçabilité issue de l'inspection du code sur `chatgpt/gestionnaire-certification`, et non un procès-verbal de recette fonctionnelle. Aucune fusion ou mise en production n'est autorisée par ce document.

## Source de vérité et conflit à résoudre

- Contrat: `contracts/POINT3B_ROLE_DECISIONS_FINAL.json`, rôle `GESTIONNAIRE`, `status=LOCKED_OWNER_APPROVED`.
- Contrat observé: **118** capacités finales, avec amendement propriétaire du **15/10/2026**. Des tests plus anciens imposaient **104** capacités. Vérifier et consigner la décision propriétaire avant toute modification de droits; ne pas ramener arbitrairement la liste à 104.
- La projection `backend/src/edusync/modules/access/application/projection.py` filtre navigation, cartes et raccourcis à partir des capacités effectives. Le backend reste l'autorité pour les routes.
- La PR #24 doit être réconciliée avec la branche `main` avant fusion si GitHub indique un conflit. Ne pas forcer la fusion.

## Matrice fonctionnelle — état du code, non recette

| Parcours Gestionnaire | Contrôle de visibilité | Composant / route repéré | Preuve disponible | Reste à vérifier |
|---|---|---|---|---|
| Accueil supervision | Projection `/access/me` | `frontend/src/home.tsx`, `projection.py` | Test `test_gestionnaire_projection_contract.py` | Rendu réel desktop/mobile, états chargement/erreur |
| Supervision des caisses | `finance.cash.other.read` | Carte `CashSupervision`, API `/finance/cash/day-summary` | Contrôle permission route; test de projection | Chiffres réels FC/USD, périmètre école, caisses multiples |
| Encaissement opérationnel interdit | Absence de `finance.checkout.collect` et `finance.cash.open` | `frontend/src/finance.tsx` et projection | `finance_supervision_role.test.tsx`, test projection | Tentatives directes API, navigation clavier/mobile |
| Personnel en consultation | `personnel.summary.read`, `personnel.read` | `frontend/src/personnel.tsx`, API `/personnel/summary` | `gestionnaire_personnel_readonly.test.tsx` | Lecture et périmètres sur base multi-établissement |
| Effectifs | `headcounts.read` | `Headcounts`, `/effectifs/counts` | Carte déclarée dans projection | Années, sections, données réelles |
| Recouvrement | `finance.recovery.monthly.read` | `RecoveryChart` | Carte déclarée dans projection | Validation réelle sans modifier le module Recouvrement |
| Rapports | `finance.reports.history.read` | `LatestReports` | Carte déclarée dans projection | Exports et impression réels |
| Documents | `documents.history.read` | `RecentDocuments` | Carte déclarée dans projection | Droits, téléchargement et historique |
| Intendance | `inventory.stock.read`, `inventory.counts.read` | `Stock`, `Counts` | Cartes déclarées dans projection | Lecture seule, portée des données |

## Critères de sortie

1. Réconcilier la branche avec `main` sans perte de commits.
2. Exécuter `python -m pytest -q -p no:cacheprovider` dans `backend` avec `PYTHONPATH=src` et les tests frontend du dépôt.
3. Obtenir la CI verte sur le **SHA final de la PR**, pas sur un ancien commit ni sur `main`.
4. Exécuter une session réelle Gestionnaire sur staging et produire des captures authentiques desktop/mobile.
5. Vérifier les interdictions d'accès côté API et l'isolation multi-tenant.
6. Signaler séparément les niveaux de certification statique, CI, staging, UX et production.
7. Demander l'accord du propriétaire avant fusion et avant tout déploiement.

## Invariants

Conserver les libellés UI **FC** et **USD** (le code interne peut utiliser `CDF`). Préserver le fonctionnement offline-first, le module Recouvrement stabilisé et les permissions approuvées. Ne pas confondre un test vert avec la couverture fonctionnelle exhaustive.
