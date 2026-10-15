# N3-A — Correspondance des droits Desktop → Web (G-PLAN-1, G-ROLE-1)

Date : 2026-10-15. Sources : golden master Desktop (`require_roles` de chaque opération de `app/db/*.py`, extrait en
lecture seule par `.local/closure/desktop_roles.py`) ; Web : registre `capability_catalog` et rôles standards
(`rbac_role_capabilities`, rôles `SCHOOL_STANDARD`) relevés sur la base de certification après la migration 0067
(`.local/closure/role_map.py`).

Rôles Desktop : ADMIN, DIRECTION, SECRETARIAT, CAISSIER. Rôles standards Web : matrice approuvée par le propriétaire
(migration 0008 : PROMOTEUR, GESTIONNAIRE, RESPONSABLE_FINANCE, PREFET_ETUDES, DIRECTION_SECTION, CAISSIER, …) plus
`ADMIN_SYSTEME_ECOLE`. Une école peut toujours déléguer un droit par un rôle `SCHOOL_CUSTOM`.

## 1. G-PLAN-1 — appliqué

| Opération Desktop | Rôles Desktop | Droit Web | Rôles standards Web (après 0067) |
|-------------------|---------------|-----------|-----------------------------------|
| `save_anticipation_plan`, `set_anticipation_plan_active` | ADMIN, DIRECTION | `finance.anticipation_plans.manage` | **ADMIN_SYSTEME_ECOLE** (décision du 2026-10-15) |
| consultation des plans | — | `finance.anticipation_plans.read` | ADMIN_SYSTEME_ECOLE, CAISSIER, DIRECTION_SECTION, GESTIONNAIRE, PREFET_ETUDES, PROMOTEUR, RESPONSABLE_FINANCE |
| `set_anticipation_membership` | ADMIN, DIRECTION, CAISSIER, SECRETARIAT | `finance.anticipation_membership.set` | CAISSIER |
| encaissement selon le plan | ADMIN, CAISSIER | `finance.anticipation.collect` | CAISSIER |

Migration `0067_admin_school_anticipation_plans.sql` : seul `ADMIN_SYSTEME_ECOLE` est étendu (gestion + lecture
nécessaire pour voir les plans). Aucun autre rôle standard n'est modifié.

## 2. G-ROLE-1 — opérations N3 et droits Web (état relevé avant la migration 0068 ; état final au §3)

Chaque opération du Desktop a un droit au registre Web (aucun droit manquant). La colonne « Écart » compare **qui**
peut agir.

| Opération Desktop | Rôles Desktop | Droit Web | Rôles standards Web | Écart |
|-------------------|---------------|-----------|---------------------|-------|
| `record_payment`, `record_family_checkout` | ADMIN, CAISSIER | `finance.checkout.collect`, `.family.collect` | CAISSIER | conforme |
| `record_product_sale` | ADMIN, CAISSIER | `finance.products.sale` | CAISSIER | conforme |
| `mark_receipt_duplicate` | ADMIN, DIRECTION, CAISSIER | `finance.receipts.reprint` | CAISSIER | conforme (côté caisse) |
| **`reverse_payment`** (annulation / remboursement) | **ADMIN, DIRECTION** | `finance.payments.reverse` | **CAISSIER** | **divergent : le Web donne au caissier une contre-opération que le Desktop lui refuse** |
| `open_cash_day` | ADMIN, CAISSIER, DIRECTION | `finance.cash.open` | CAISSIER | conforme |
| `record_expense` | ADMIN, CAISSIER, DIRECTION | `finance.cash.expense.create` | aucun | **sans titulaire** |
| **`close_cash_day`** (journée de l'école) | **ADMIN, DIRECTION** | `finance.cash.close` | CAISSIER | **divergent** : au Web, ce droit sert à clôturer la **session** du caissier ; la clôture de la **journée de l'école** (G-CAI-4) n'a pas encore de droit propre |
| `reopen_cash_day` | ADMIN | `finance.cash.reopen` | aucun | **sans titulaire** |
| `receive_advance_fund`, `allocate_advance_fund` | ADMIN, CAISSIER | `finance.advance_funds.receive`, `.allocate` | CAISSIER | conforme |
| **`reverse_advance_fund`** | **ADMIN, DIRECTION** | `finance.advance_funds.refund` | **CAISSIER** | **divergent** (même cas que `reverse_payment`) |
| `create_financial_decision`, `cancel_financial_decision` | ADMIN, DIRECTION | `finance.decisions.create`, `.cancel` | aucun | **sans titulaire** |
| `set_charge_responsibility` | ADMIN, DIRECTION | `finance.responsibility.set` | aucun | **sans titulaire** |
| `finalize_historical_financial_import` | ADMIN, DIRECTION | `migration.finance_history.execute` | *à relever* | à vérifier |
| `set_staff_child_finance_mode` | ADMIN, DIRECTION | `personnel.staff_children.finance_mode` | aucun | **sans titulaire** |
| `confirm_staff_payroll_deduction`, `cancel_staff_noncash_settlement` | ADMIN, DIRECTION | `personnel.payroll_deduction.confirm`, `.cancel` | aucun | **sans titulaire** |
| `change_student_status` (abandon, transfert, suspension, réintégration) | ADMIN, SECRETARIAT, CAISSIER, DIRECTION | `students.lifecycle.*` | abandon : CAISSIER, DIRECTION_SECTION, PREFET_ETUDES | conforme pour l'abandon ; la suspension n'a pas encore de route (G-SCO-5) |
| analyses par caissier / par frais | (lecture) | `finance.analysis.by_cashier.read`, `.by_fee.read` | GESTIONNAIRE, PROMOTEUR, RESPONSABLE_FINANCE (+ DIRECTION_SECTION, PREFET_ETUDES pour les frais) | conforme |
| rapport journalier, journal de caisse PDF | (lecture) | `finance.reports.daily.generate`, `finance.cash.journal.export_pdf` | CAISSIER, GESTIONNAIRE, PROMOTEUR, RESPONSABLE_FINANCE | conforme |
| relevé de compte élève | (lecture) | `students.account.read`, `.export_pdf` | CAISSIER et rôles de consultation | conforme |

## 3. Décision du propriétaire du 2026-10-15 (G-ROLE-1) — appliquée

**Il n'existe pas de correspondance 1:1 entre les anciens rôles Desktop et les rôles Web.** Le Desktop utilisait des
rôles composites (ADMIN faisait à la fois la configuration technique, la gouvernance financière et la caisse). Le Web
sépare volontairement :

| Famille de responsabilités | Rôle Web standard |
|----------------------------|-------------------|
| administration et configuration technique (dont la définition des plans anticipés, qui est un paramétrage) | `ADMIN_SYSTEME_ECOLE` |
| gouvernance et décision financière supérieure | `GESTIONNAIRE` |
| encaissement et caisse opérationnelle | `CAISSIER` |
| consultation et contrôle | rôles de lecture déjà approuvés (PROMOTEUR, RESPONSABLE_FINANCE, PREFET_ETUDES, DIRECTION_SECTION…) |

Attribution (migration `0068_n3a_role_governance.sql`, contrats `contracts/CAPABILITY_REGISTRY.json` et
`contracts/POINT3B_ROLE_DECISIONS_FINAL.json` amendés) :

| Opération | Droit Web | Rôle standard | Invariant métier (appliqué par le lot qui porte l'opération) |
|-----------|-----------|---------------|---------------------------------------------------------------|
| Correction de **son propre** paiement | `finance.payments.reverse` | CAISSIER (conservé) | le paiement est le sien, sa session est encore ouverte, contre-opération auditable (jamais UPDATE / DELETE) — N3-B |
| Annulation / remboursement de **tout** paiement (autre caissier, session clôturée) | `finance.payments.reverse.supervisor` (nouveau) | GESTIONNAIRE | motif obligatoire, contre-opération, audit — N3-B |
| Remboursement d'un fonds anticipé | `finance.advance_funds.refund` | GESTIONNAIRE (**retiré au CAISSIER**) | fonds non imputé, motif — N3-D |
| Dépense de caisse | `finance.cash.expense.create` | CAISSIER | session ouverte, motif ≥ 3 caractères — N3-B |
| Clôture individuelle de session | `finance.cash.close` | CAISSIER (inchangé) | — |
| **Clôture globale de la journée de l'école** | `finance.cash.day.close` (nouveau) | GESTIONNAIRE | instantanés par devise, sessions individuelles conservées — N3-B |
| Réouverture de la journée | `finance.cash.reopen` | GESTIONNAIRE | motif obligatoire (≥ 5 caractères au Desktop), audit — N3-B |
| Décisions financières (création, annulation, lecture) | `finance.decisions.*` | GESTIONNAIRE | N3-C |
| Responsabilité d'un frais | `finance.responsibility.set` / `.read` | GESTIONNAIRE | N3-C |
| Mode de prise en charge des enfants du personnel | `personnel.staff_children.finance_mode` | GESTIONNAIRE | N3-F |
| Retenue salariale hors caisse (confirmation, annulation) | `personnel.payroll_deduction.confirm` / `.cancel` | GESTIONNAIRE | aucun reçu ni opération de caisse ; annulation motivée — N3-F |
| Définition des plans anticipés | `finance.anticipation_plans.manage` | ADMIN_SYSTEME_ECOLE (G-PLAN-1) | — |

`ADMIN_SYSTEME_ECOLE` ne reçoit aucune mutation financière opérationnelle. PROMOTEUR, RESPONSABLE_FINANCE,
PREFET_ETUDES et DIRECTION_SECTION restent sur leurs baselines. Une école peut déléguer explicitement par `SCHOOL_CUSTOM`.
