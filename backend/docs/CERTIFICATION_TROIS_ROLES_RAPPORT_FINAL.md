# Rapport final — certification backend : Intendant, Directeur des études, Directeur de discipline

Date : 30/10/2026 · Branche `chatgpt/intendant-etudes-discipline-certification` · Python 3.13.14 · PostgreSQL local isolé.
Aucune fusion, aucun déploiement, aucune GitHub Action déclenchée (seule une poussée sur `main` ou une PR lance la CI ;
aucune PR n'a été ouverte). Aucun fichier frontend modifié.

Livrables : ce rapport (sections 1 à 8) et la matrice générée `backend/docs/CERTIFICATION_TROIS_ROLES_MATRICE_FINALE.md`.
Preuves brutes : `backend/docs/evidence/three_roles_postgres_run.txt`, `backend/docs/evidence/three_roles_perf.txt`.

## 1. Matrice des attributions (résumé)

| Rôle | Attributions (registre canonique) | PASS (exécuté) | N/A justifié | NON TESTÉ | FAIL |
|---|---:|---:|---:|---:|---:|
| INTENDANT | 29 | 29 | 0 | 0 | 0 |
| DIRECTEUR_ETUDES | 49 | 41 | 8 | 0 | 0 |
| DIRECTEUR_DISCIPLINE | 43 | 35 | 8 | 0 | 0 |
| **Total** | **121** | **105** | **16** | **0** | **0** |

N/A : 14 capacités DEPRECATED (tableau de bord remplacé par `/access/me`, inscriptions / familles lues par `students.read` /
`families.read`) et `students.lifecycle.history.read` (reporté à la version des points, décision du 30/10).
Rapprochement 108 ↔ 121 : section « Rapprochement » de la matrice.

### Fermeture des réserves (décisions du propriétaire du 30/10/2026)

| Réserve initiale | Décision | Fermeture | Preuve |
|---|---|---|---|
| R2 — personnel des directeurs (contradiction addendum / registre) | Lecture, agents de leur section seulement | Migration 0102 + isolation de la PR #27 fusionnée (agents transversaux et autres sections invisibles, aucune écriture ni export) | PG « personnel du secondaire lisible », « primaire et toute l'école invisibles », « aucune création (403) » |
| R3 — agents de toute l'école visibles | Décision du 28/10 étendue | PR #27 fusionnée dans la branche (`df568db`) | PG ci-dessus ; test d'isolation des sections PostgreSQL PASS |
| R4 — « Ajouter un membre » en erreur 500 pour ces rôles | — | Correctif de la PR #27 fusionné : section obligatoire | PG « ajout sans section → 422 », « PRIMAIRE → 422 », « SECONDAIRE → 201 » |
| R5 — trois capacités PLANNED | Export des inscriptions maintenant ; parcours plus tard ; impression retirée | `GET /schooling/exports/enrollments.pdf|.xlsx` (0104) ; `documents.print` retiré (0103) | PG « registre = secondaire seulement », « Gestionnaire : toute l'école » |
| R6 — SMS de bout en bout non exécuté | — | Fournisseur simulé (refusé en production), worker réel en processus | PG « SMS de bout en bout » : aperçu, confirmation, envoi, livraison, historique, crédit consommé |
| R8 — numéros de migration | — | 0099 à 0104 uniques entre branches | — |

## 2. Audit de sécurité — anomalies et correctifs

| # | Gravité | Anomalie (reproduite) | Correctif | Preuve |
|---|---|---|---|---|
| S1 | **Critique** | `GET /audit/entities/{type}/{id}` : la capacité seule ouvrait `old_json`/`new_json` de toute entité de l'école (élève du primaire, paiement, compte) à un acteur limité au secondaire — réserve du dossier de passage | Domaine requis (lire l'entité) + périmètre : un acteur section/classe n'atteint que les élèves, familles, agents de ses sections ; sinon 404 | 10 tests HTTP (8 échouent sur l'ancien code) ; PG « primaire → 404 », « paiement → 404 » |
| S2 | **Haute** | Lien documentaire signé encore valable après retrait du droit ou désactivation du compte (jusqu'à l'expiration) — réserve du dossier | Droits, compte et appartenance réévalués à l'ouverture, comme chaque requête | PG : 2 contrôles échouent sur l'ancien code ; 7 contrôles (retrait, appartenance, compte, autre école, expiré, altéré) |
| S3 | **Haute** | Historique des communications : le détail des livraisons (noms et **numéros** des parents) d'un message du primaire était lisible par un directeur limité au secondaire | Historique et livraisons limités aux messages de l'auteur ou dont l'audience est dans ses sections ; sinon 404 | PG : 3 contrôles échouent sur l'ancien code |
| S4 | Moyenne | Audience hors périmètre (section/classe/élève du primaire, section d'une autre école) : audience vide silencieuse (409) au lieu d'un refus | Refus explicite (403) avant toute lecture des responsables | PG : 4 contrôles échouent sur l'ancien code |
| S5 | Info | Message d'une autre école : liste de livraisons vide renvoyée (200) | 404 (cohérent, aucune donnée exposée auparavant) | PG « école B : message de A introuvable » |

Vérifiés sans défaut : isolation multi-écoles du stock, des comptages, des biens, des exports, des élèves, des familles ;
déduplication des parents multi-enfants et multi-sections ; notifications lisibles et acquittables par le seul
destinataire de la bonne école ; 401 sans jeton ou jeton falsifié ; 403 sans capacité ; aucune mutation financière,
d'inscription ou de réglage pour les trois rôles.

## 3. Défauts fonctionnels corrigés (Intendant)

| # | Défaut | Correctif |
|---|---|---|
| F1 | Migration de l'événement `UPDATE` jamais appliquée (absente du provisionneur ; test de provisionnement en échec) | Renumérotée `0099` (0097 déjà pris sur une autre branche) et enregistrée |
| F2 | Routes construites mais capacités PLANNED (test du registre en échec) | `0100` : 6 capacités ACTIVE (cycle de vie seulement, aucun droit ajouté ; détenteurs = contrats verrouillés) |
| F3 | Export / impression d'un comptage contrôlés par des alias | Capacité métier `inventory.counts.export` (Excel et PDF sont ses alias) |
| F4 | Un bien sorti du patrimoine restait modifiable | 409 |
| F5 | Changement d'état d'un bien sans local : **erreur 500** (paramètre NULL non typé ; défaut aussi présent sur `main`) | Paramètres typés `CAST(… AS uuid)` |
| F6 | Droit « alertes de stock faible » sans route | `GET /stewardship/stock/low-alerts` |
| F7 | Création d'un bien ou d'un comptage non idempotente | `Idempotency-Key` facultative (rejeu = même résultat ; autre contenu = 409) |
| F8 | Liste des mouvements récents : parcours et tri de tout le grand livre | Index `0101` (13,5 ms → 0,05 ms sur 50 000 mouvements) |

## 4. Exécution des tests (commandes et résultats)

| Suite | Commande | Résultat |
|---|---|---|
| Base de départ (avant correctifs) | `cd backend && python -m pytest -q -p no:cacheprovider` | 1098 passed, **2 failed** (provisionneur, capacités PLANNED vérifiées) |
| Backend complet (final, après fusion des branches PR #27 et Responsable financier) | `PYTHONUTF8=1 python -m pytest -q -p no:cacheprovider` | **1375 passed**, 1 skipped, 0 échec |
| Application réelle + PostgreSQL réel | `python tools/local/isolated_db.py create edusync_cert_3roles` puis `python tools/local/isolated_db.py env edusync_cert_3roles -- ../.venv/Scripts/python.exe ../tools/ci/three_roles_postgres_integration.py` | **178/178 PASS** |
| Isolation des sections (PR #27, fusionnée) | `… env edusync_cert_3roles -- ../.venv/Scripts/python.exe ../tools/ci/section_isolation_postgres_integration.py` | **PASS** |
| Registre canonique | `… env edusync_cert_3roles -- ../.venv/Scripts/python.exe ../tools/ci/rbac_registry.py check` | **0 dérive** |
| Caissier PostgreSQL (non-régression) | `… env edusync_cert_3roles -- ../.venv/Scripts/python.exe ../tools/ci/cashier_postgres_integration.py` | **PASS** |
| Frontend (après la phase frontend) | `cd frontend && npx vitest run tests --maxWorkers=4` | **83/83** (dont `tests/three_roles_ui.test.tsx`, 3 nouveaux) |
| Recette navigateur des trois rôles | `cd frontend && node browser-tests/local_three_roles_certification.mjs` | **33/33 PASS** |
| Matrice | `python tools/rbac/three_roles_matrix.py` | 121 attributions, 105 PASS, 16 N/A, 0 NON TESTÉ |

Codes HTTP couverts : 200, 201, 401, 403, 404, 409, 422 (le 400 « clé d'idempotence trop longue » est couvert par le code
existant des routes de stock).

## 5. PostgreSQL réel, transactions et concurrence

Base isolée créée et migrée de zéro par le provisionneur officiel (`POINT-4A database provisioning: PASS`), migrations
jusqu'à `0101` incluses, contraintes et clés étrangères actives, rôle tenant avec RLS. Scénarios :

- deux sorties de stock **simultanées** de 4 sur un stock de 5 → une seule réussit (verrou `FOR UPDATE`), stock jamais négatif ;
- deux validations **simultanées** d'un même comptage → 200 + 409, un seul ajustement d'inventaire ;
- idempotence (même clé → même résultat, une ligne ; autre contenu → 409) pour articles, biens, mouvements, messages ;
- crédit SMS : réservation réelle par la fonction de portefeuille (verrou, clé, pas de solde négatif) ; crédit insuffisant → refus, rien enregistré ;
- grand livre de stock cohérent (somme des mouvements = quantité) après réception, sortie, ajustement et inventaire.

Performance (mesures sur cette machine, sans seuil revendiqué — `backend/docs/evidence/three_roles_perf.txt`, 5 000 articles,
50 000 mouvements, 2 000 biens, 3 000 élèves) : listes Intendance 16 à 53 ms (médiane), export Excel du stock ≈ 0,7 s,
élèves du secondaire 75 ms (0,4 s au premier passage à froid), effectifs par section ≈ 175 ms.

## 6. Fichiers modifiés et commits

`5074ac7` intendance (0099, 0100, routes) · `b687739` sécurité audit + liens signés · `a5a8371` sécurité communications ·
`4334007` tests PostgreSQL étendus · `ce1e336` performance (0101) · commit de ce rapport et de la matrice (voir `git log`).
Fichiers : `backend/migrations/0099…`, `0100…`, `0101…`, `backend/scripts/provision_database.py`, `contracts/CAPABILITY_REGISTRY.json`,
`backend/src/edusync/modules/{stewardship,audit,documents,communications}/…`, tests `test_audit_entity_history_scope.py`,
`test_communications_history_scope.py`, tests de la branche adaptés (`test_intendant_backend_exports_regression.py`,
`test_secondary_leadership_backend_regression.py`), outils `tools/ci/three_roles_postgres_integration.py`,
`tools/local/isolated_db.py`, `tools/local/three_roles_perf.py`, `tools/rbac/route_capability_map.py`, `tools/rbac/three_roles_matrix.py`.

## 7. Non-régression

Suite backend complète verte (1375), registre sans dérive, caissier PostgreSQL PASS, tests frontend 83/83. Les tests de la
branche qui lisaient l'ancien texte (`0097`, alias de comptage, audience vide) ont été alignés sur les correctifs sans
retirer ce qu'ils vérifient.

## 8. Réserves restantes

| # | Réserve | Nature |
|---|---|---|
| R1 | CI GitHub non exécutée (facturation du compte bloquée) ; le test PostgreSQL réel n'est pas branché dans `ci.yml` (base isolée et configuration complète de l'application nécessaires) | Hors de portée du code — bloquant pour la fusion |

Toutes les autres réserves (R2 à R8) sont **fermées** (section 1 ; R7, erreurs TypeScript, fermée dans la phase frontend — section 9).

## 9. Phase frontend (30/10/2026)

| Constat | Correctif |
|---|---|
| « Le point du jour » réservé aux rôles qui supervisent les caisses : l'Intendant et les directeurs arrivaient sur un accueil muet | Affiché pour tout rôle de pilotage (pas pour les guichets) ; nouveaux constats : mouvements d'élèves des 30 derniers jours, personnel en service, matériel hors d'usage, inventaires en cours à valider. Chaque constat ouvre son module |
| Alerte de stock bas jamais affichée : le serveur renvoie une **liste**, l'écran la lisait comme un nombre | Lecture de la liste (consommables et articles vendus), rupture signalée en premier avec le nom des articles |
| `inventory.stock.export_xlsx`, `inventory.stock.sheet.print`, `inventory.counts.export` : droits actifs sans aucun bouton | « Exporter en Excel », « Imprimer la fiche de stock », PDF / Excel de chaque inventaire — chacun visible seulement avec son droit |
| `enrollments.export` (registre des inscriptions, activé le 30/10) : aucun bouton | « Registre des inscriptions » PDF / Excel dans l'annuaire, avec les filtres année / section / classe ; le périmètre est appliqué par le serveur |
| Onglet « Inscription / Réinscription » affiché (vide) aux directeurs, qui n'ont ni `enrollments.create` ni `enrollments.reenroll` | Onglet masqué sans l'un de ces droits ; contrôlé par la recette |
| `src/stewardship.tsx` : 3 erreurs TypeScript (R7) | Corrigées (`tsc --noEmit` propre) |

Recette navigateur (`browser-tests/local_three_roles_certification.mjs`, Edge, pile locale) : connexion, accueil sans bouton
hors droits, chaque constat du point du jour cliqué, exports réels (téléchargement Excel vérifié), chaque module et chaque
onglet ouverts, responsive 320 → 1440 px avec la vraie navigation mobile (barre du bas et menu), aucun refus serveur, aucun
« CDF » affiché : **33/33 PASS**. Limite : aucun inventaire physique dans la base de démonstration, l'export d'un inventaire
est donc couvert par le test unitaire et non par la recette.

## Conclusion

**Backend certifié en local** pour les trois rôles, sans réserve applicative ouverte : 121 attributions vérifiées (105 PASS
exécutés, 16 N/A justifiés, 0 non testé), 4 failles de sécurité reproduites et corrigées (dont une critique), 8 défauts
fonctionnels corrigés, décisions du propriétaire du 30/10 appliquées, isolation des sections de la PR #27 intégrée,
178 contrôles sur PostgreSQL réel. Frontend des trois rôles livré et recetté (section 9). Reste : la CI GitHub (facturation).
