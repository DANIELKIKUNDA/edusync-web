# Préfet des études / Direction de section — audit initial (27/10/2026)

## Référence de départ
- Base : `main` au commit `21eb5cc2d71e892c542f345316fd62b4a162e29a`.
- Branche : `chatgpt/prefet-directeur-certification`.
- Source normative : `contracts/POINT3B_ROLE_DECISIONS_FINAL.json`, statut `LOCKED_OWNER_APPROVED`.

## Décision métier confirmée dans le contrat
Il existe **deux codes RBAC distincts** : `PREFET_ETUDES` et `DIRECTION_SECTION`. Ils possèdent chacun **84 capacités**, avec des ensembles identiques dans le contrat actuel, mais des **périmètres distincts**.
- Préfet : section **Secondaire**.
- Direction de section : **Primaire**, **Maternelle** ou les deux selon affectation.
- La politique `docs/rbac/POINT3B_SCOPE_OWNERSHIP_POLICIES.md` exige un résolveur de périmètre métier avant IAM pour élèves, personnel, finances en lecture et communications.
- L'accès à plusieurs sections ne doit jamais être déduit du seul intitulé de rôle.

## Anomalie documentaire identifiée
`docs/rbac/POINT3B_DECISION_06_PREFET.md` et `POINT3B_DECISION_07_DIRECTION_SECTION.md` indiquent encore **79 capacités** ; le contrat final en définit **84** par rôle. Ces documents sont historiques : ne pas rétrograder le contrat. Mettre la documentation à jour avec traçabilité après vérification des amendements.

## Fonctions à vérifier (non certifiées à ce stade)
1. Résolution et propagation des scopes SECTION (API, requêtes SQL, exports, PDF, historique).
2. Écrans élèves : lecture, identité, changement de classe, abandon, suspension, réintégration, transfert et historique.
3. Effectifs par classe/option/section, mouvements, export et impression.
4. Personnel : lecture, affectations, synthèse et documents.
5. Communications aux parents : individuelle, classe, section, SMS et historique.
6. Finance **lecture et rapports uniquement selon contrat**, avec filtre de section ; aucun encaissement ou contrôle de caisse implicite.
7. Tableau de bord, documents, notifications, session et navigation mobile.
8. Tests d'autorisation positive/négative, isolation inter-écoles et inter-sections, non-régression Gestionnaire/Caissier.

## Contrôles de certification
- A — Contrat statique : **PARTIEL** (deux rôles et 84 capacités vérifiés).
- B — Tests et CI : **NON EXÉCUTÉS** sur cette branche.
- C — Staging : **NON EXÉCUTÉ**.
- D — Navigateur authentifié : **NON EXÉCUTÉ**.
- E — Production : **HORS PÉRIMÈTRE**.

## Prochaines actions
Construire la matrice 84 × 2 capacités/routes/écrans/scopes/tests ; examiner le résolveur SECTION ; corriger les écarts démontrés ; ajouter tests ; faire valider la CI et les parcours navigateur avant toute fusion. Ne pas modifier `main` sans accord.
