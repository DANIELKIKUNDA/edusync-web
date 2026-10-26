# Certification finale du rôle GESTIONNAIRE — EduSync Web

Date : 26/10/2026 · Branche : `chatgpt/gestionnaire-certification` · PR : DANIELKIKUNDA/edusync-web#24
Environnement de recette : pile locale (PostgreSQL, API, interface compilée), école C, compte Gestionnaire **standard**
créé par l'administrateur via l'écran « Ajouter un membre » (`frontend/browser-tests/local_role_prepare.mjs`).

Statuts : **PASS** · **FAIL** · **BLOCKED** · **NOT APPLICABLE**. Niveaux : A audit statique · B tests et CI ·
C staging · D UX réelle (navigateur) · E production.

## 1. État initial

- PR #24 : 63 commits propres (travail ChatGPT), dernier commit `372114f`, **en conflit** avec `main`.
- `main` avait avancé d'un commit, `1d297c7` (caisse, reçus officiels, rapports, documents, hors ligne : 49 fichiers).
- Sauvegarde créée et poussée avant toute opération : branche `backup/gestionnaire-372114f`.

## 2. Analyse des conflits Git

Base commune `f8d840a`. 9 fichiers modifiés des deux côtés, dont 6 en conflit textuel (une partie due aux fins de ligne
CRLF/LF : fusion à trois voies refaite après normalisation).

| Fichier | Intention `main` | Intention Gestionnaire | Résolution |
|---|---|---|---|
| `frontend/src/offline/outbox.ts` | ordre FIFO `enqueueOrder` calculé dans une seule transaction IndexedDB | compteur local `order` (même défaut) | version `main`, plus robuste ; compteur retiré |
| `frontend/src/documents.tsx` | visionneuse PDF intégrée, filtre « mes documents / toute l'école » | ouverture via `previewPdfUrl` | version `main` + libellé d'export du Gestionnaire |
| `frontend/src/finance.tsx` | file des reçus, panier caissier, formatage FC/USD | onglets selon les droits, onglet initial par rôle, « Vue de supervision » | **fusion des deux** ; les deux liens profonds lus |
| `frontend/src/home.tsx` | carte caisse → onglet Caisse | cartes décisions / rapports / documents, `openWidget` | version Gestionnaire (couvre le cas `main`) ; salutation en double retirée |
| `backend/tests/test_point8_actor_dashboards.py` | — | — | fusion automatique après normalisation |
| `frontend/browser-tests/school_premium.spec.ts` | — | — | fusion automatique après normalisation |

## 3. Résolution effectuée

Commit de fusion `7c355a4`, poussé sans `--force`. Vérifié : 0 marqueur de conflit, `tsc` OK, build OK, pytest 982
passed, vitest 80/80. GitHub : PR à nouveau fusionnable.

## 4. Contrat RBAC retenu

- Le registre canonique `contracts/CAPABILITY_REGISTRY.json` (statut `CANONICAL`, décision du 23/10/2026) est la
  source de vérité ; il déclare lui-même `POINT3B_ROLE_DECISIONS_FINAL.json` **historique**.
- Gestionnaire : **143** capacités au registre = les **118** de POINT3B (toutes présentes, aucune manquante) + **25**
  issues de décisions ultérieures : fusion des formats d'export (23/10), imports (24/10), gestion du personnel.
- **Contradiction relevée et tranchée par le propriétaire (26/10/2026)** : le document de décision 04 disait Personnel
  en lecture seule ; le registre et la base donnaient l'écriture. Décision : **le Gestionnaire gère le personnel**.
  Amendement consigné dans `docs/rbac/POINT3B_DECISION_04_GESTIONNAIRE.md`. Aucun droit ajouté ni retiré.

## 5. Matrice des capacités (A — calculée)

Matrice complète : [`docs/certification/gestionnaire/MATRICE_CAPACITES.md`](gestionnaire/MATRICE_CAPACITES.md), produite
par `tools/rbac/role_capability_matrix.py GESTIONNAIRE` (calcul, pas déclaration).

| Résultat | Nombre | Signification |
|---|---|---|
| PASS | 71 | ACTIVE, contrôlée par le serveur et couverte par un test automatisé |
| FAIL (A) | 21 | ACTIVE et contrôlée par le serveur, mais **aucun test automatisé ne la nomme** |
| NOT APPLICABLE | 51 | ALIAS / DEPRECATED (format fusionné) ou PLANNED (non construite, masquée) |

Aucune capacité active n'est sans contrôle serveur : invariant désormais vérifié pour **tous** les rôles standards par
`backend/tests/test_rbac_every_active_right_is_enforced.py`. Les 21 capacités sans test unitaire (communications,
familles, ouverture de documents, rapport du jour, ventes d'articles, exports, compte élève, mouvements de stock…)
ont toutes été **exercées en navigateur réel** par le robot d'inspection (D, section 13) ; l'absence de test unitaire
dédié reste un risque résiduel (section 16).

## 6. Audit des modules

| Module | Ce qui a été vérifié | Statut |
|---|---|---|
| Accueil | pilotage (caisses, effectifs, personnel, recouvrement, décisions, rapports), données réelles, aucun bloc d'administration, aucun raccourci d'encaissement | PASS (D) |
| Supervision des caisses | « Vue de supervision », aucune ouverture de caisse, situation globale, caisses de **tous** les caissiers, journal PDF + Excel d'une caisse, clôture de la journée disponible | PASS (D) |
| Centre financier | onglets selon les droits, **pas d'onglet Encaissement** ; recouvrement, suivi financier, rapports (périodique, analyses par caissier, générés), décisions | PASS (D) |
| Personnel | synthèse, annuaire, « Nouvel agent » (décision 26/10), import | PASS (D) |
| Effectifs | indicateurs, mouvements, tableaux par classe | PASS (D) |
| Documents | historique, visionneuse PDF intégrée | PASS (D) |
| Intendance | module accessible, stocks consultables | PASS (D) |
| Navigation | menu (10 modules), retour à l'accueil, déconnexion avec confirmation, reconnexion | PASS (D) |
| Monnaies | aucune occurrence de « CDF » visible sur tous les écrans parcourus | PASS (D) |

## 7. Fonctionnalités manquantes identifiées

Aucune fonctionnalité approuvée absente. Les capacités PLANNED (exports d'inventaire, `enrollments.export`, …) restent
non construites **par décision** et sont masquées.

## 8. Fonctionnalités implémentées dans ce lot

- Test d'invariant RBAC « tout droit actif est contrôlé par le serveur » (tous rôles) et test des frontières du rôle.
- Outil de matrice calculée `tools/rbac/role_capability_matrix.py`.
- Recette navigateur complète `frontend/browser-tests/local_gestionnaire_certification.mjs` (18 étapes).

## 9. Anomalies corrigées

| Priorité | Anomalie | Correction |
|---|---|---|
| P2 | « CDF » affiché dans les tableaux de supervision des caisses et de la journée de l'école | libellé FC (`cash_desk.tsx`, `cash_controls.tsx`) |
| P2 | Recouvrement › Suivi mensuel : montants « 468 000 CDF » | libellé FC (`recovery.tsx`) |
| P2 | « CDF » dans le sélecteur de devise du recouvrement, le graphique, les fiches élève/famille, les fonds anticipés | `currencyLabel` (`platform/format.ts`) appliqué |
| — | Conflits de fusion avec `main` | section 2 |

## 10. Tests exécutés

| Suite | Commande | Résultat |
|---|---|---|
| Backend | `cd backend && PYTHONUTF8=1 python -m pytest -q -p no:cacheprovider` | voir section 11 |
| Frontend unitaires | `cd frontend && npx vitest run` | 80 passed (17 fichiers) |
| Typecheck / build | `npx tsc --noEmit -p .` · `npx vite build` | OK |
| Recette Gestionnaire | `node browser-tests/local_gestionnaire_certification.mjs` | **18/18 PASS** |
| Robot d'inspection | `node browser-tests/local_audit_robot.mjs ../.local/gestionnaire/.account.json 1440` | 123 écrans, 0 constat |

## 11. Résultats exacts

- pytest : **984 passed, 1 skipped** (982 avant ajout des 2 tests d'invariant RBAC).
- vitest : **80 passed**.
- Recette : 18/18 (détail ci-dessous), dont les appels interdits avec la session du Gestionnaire :
  `POST /finance/cash/open` → 403 · `POST /finance/checkout/collect` → 403 · `POST /schooling/enrollments/family` → 403 ·
  `PATCH /settings/identity` → 403 ; isolation : élève de l'école A lu depuis l'école C → 404 (fiche et relevé).

## 12. CI et SHA

Résultat des workflows GitHub sur le SHA final de la PR : consigné dans la description de la PR #24 après le dernier
push (le présent fichier fait partie de ce commit ; un SHA ne peut pas se citer lui-même).

## 13. Tests navigateur (D)

01 connexion · 02 accueil de pilotage · 03 menu · 10 supervision des caisses · 11 caisse passée (journal PDF, Excel) ·
12 clôture de la journée disponible · 20 centre financier sans encaissement · 21 rapports · 22 décisions ·
23 recouvrement et suivi financier · 30 personnel · 40 effectifs · 50 documents · 60 intendance ·
70 opérations interdites (403) · 75 isolation entre écoles (404) · 80 responsive 320/360/390/768/1024/1440 px sans
débordement · 90 déconnexion / reconnexion — **tous PASS**.

## 14. Captures d'écran (authentiques, pile locale)

| | |
|---|---|
| Tableau de bord — ordinateur | `gestionnaire/gest_01_tableau_de_bord_ordinateur.png` |
| Tableau de bord — mobile (390 px) | `gestionnaire/gest_02_tableau_de_bord_mobile.png` |
| Supervision des caisses | `gestionnaire/gest_03_supervision_caisses.png` |
| Personnel | `gestionnaire/gest_04_personnel.png` |
| Effectifs | `gestionnaire/gest_05_effectifs.png` |
| Centre financier | `gestionnaire/gest_06_centre_financier.png` |
| Rapports | `gestionnaire/gest_07_rapports.png` |

## 15. Problèmes restants

- 21 capacités actives couvertes en navigateur mais sans test automatisé dédié (section 5).
- Clôture de la journée : présence du bouton vérifiée, l'action elle-même n'a pas été déclenchée (elle fige la journée
  des caissiers ; à exercer sur staging avec l'accord de l'école).

## 16. Risques résiduels

- Recette réalisée sur pile locale avec un jeu de données de démonstration : volumes réels non mesurés.
- Isolation vérifiée sur deux routes représentatives (élève, relevé) ; l'isolation est assurée en base par RLS, non
  ré-éprouvée route par route.
- Staging et production non éprouvés dans ce lot.

## 17. Décision de certification

| Niveau | Statut | Preuve |
|---|---|---|
| A — Audit statique | **PASS** | matrice calculée, contrat tranché, invariant RBAC |
| B — Tests et CI | **PASS** sous réserve de la CI verte sur le SHA final (section 12) | pytest 984, vitest 80, tsc, build |
| C — Staging | **BLOCKED** | non déployé : la fusion dans `main` (qui déclenche le staging) attend l'accord du propriétaire |
| D — UX réelle | **PASS** (pile locale) | recette 18/18, robot 123 écrans, 7 captures |
| E — Production | **BLOCKED** | aucune mise en production sans autorisation |

**Décision : rôle GESTIONNAIRE certifié aux niveaux A, B et D.** C et E restent à valider après fusion autorisée.
`main` n'a pas été modifiée par ce travail.
