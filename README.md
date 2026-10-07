# EduSync Web — clôture locale (octobre 2026)

État courant et preuves : `CLOTURE_LOCALE_EDUSYNC.md`. Lanceur local : `tools/local/README.md`.

# EduSync Web — Point 4D Effectifs & Dépôts

Checkpoint preservation-first du 12 septembre 2026. Le module Desktop certifié reste l'oracle : périmètres, KPI, F/G/T, tableaux, mouvements, dépôts, PDF/Excel et total général sont copiés avant tout enrichissement. Voir `POINT4D_IMPLEMENTATION_REPORT.md`, `POINT4D_PRESERVATION_MATRIX.md` et `POINT4D_GATE.md`.

# EduSync Web — Point 4A Paramètres

Checkpoint après ajout des rôles Secondaire et démarrage du Point 4 preservation-first. Voir `POINT4A_IMPLEMENTATION_REPORT.md`.

# EduSync — Point 3B RBAC industriel / mapping propriétaire

État courant : **moteur RBAC prêt, décisions de rôles en cours**.

Nouveautés : registre de 258 capacités, rôles standard/personnalisés, périmètres école/cycle/section/classe, RLS, exceptions temporaires, et premier rôle `MANAGER_SYSTEME` préparé en `DRAFT`. Aucun rôle métier école n'est activé sans validation de Daniel.

Documents principaux :
- `POINT3B_IMPLEMENTATION_REPORT.md`
- `POINT3B_GATE.md`
- `POINT3B_TEST_RESULTS.md`
- `docs/rbac/POINT3B_DECISION_01_MANAGER_SYSTEME.md`
- `contracts/POINT3B_ROLE_DECISIONS_DRAFT.json`
- `contracts/CAPABILITY_REGISTRY.json`

---

# EduSync Web — Point 2 Finance offline multi-caissier

Checkpoint du 11 septembre 2026.

Ce dépôt dérive du Point 1 verrouillé et implémente le Point 2 de la feuille de route officielle : **Finance offline multi-caissier**.

Protocole courant : `AUTHORIZED_PARTITIONED_CASH_V2`.

Principe : plusieurs caissiers peuvent continuer à encaisser du CASH hors connexion dans la même école, avec autorité financière partitionnée par charge, reçus préalloués, idempotence, hash-chain, checkpoint de sync, Web Locks, RLS, quarantaine incident et réconciliation.

Le Desktop certifié reste l'oracle métier. Le ledger Finance Web canonique sera porté au Point 6 ; ce checkpoint fournit déjà le port hexagonal et tous les invariants offline auxquels il devra se conformer.

Documents principaux :

- `POINT2_FINANCE_OFFLINE_MULTI_CAISSIER.md`
- `POINT2_IMPLEMENTATION_REPORT.md`
- `POINT2_GATE.md`
- `POINT2_RUNBOOK.md`
- `POINT2_TEST_RESULTS.md`

Pour la certification Windows : `RUN_POINT2_WINDOWS.ps1`.

## Point 3B — décisions propriétaire (mise à jour)
- `MANAGER_SYSTEME`: **VALIDÉ** par Daniel, 10 capacités plateforme incluant `platform.notifications.system.send`.
- `ADMIN_SYSTEME_ECOLE`: proposition V1 **DRAFT**, 84 capacités techniques, validation propriétaire requise.
- Aucun autre rôle métier n’est finalisé.


## Point 3B final role baseline (2026-09-12)
See `contracts/POINT3B_ROLE_DECISIONS_FINAL.json`, `docs/rbac/POINT3B_STANDARD_ROLES_FINAL.md`, and migration `0008_owner_approved_school_roles.sql`.

## 2026-09-12 — Point 4C preservation correction

The initial Point 4C document samples were superseded after direct comparison with the certified Desktop exports. The current authoritative state is described in `POINT4C_PRESERVATION_CORRECTION.md`: exact Desktop student/family document columns and school identity header were restored, sex is mandatory at enrollment, birth date/place remain non-blocking by default, and backend regression is 206 PASS / 0 FAIL.
