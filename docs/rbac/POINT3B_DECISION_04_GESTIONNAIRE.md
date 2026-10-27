# Décision Point 3B — Gestionnaire

**Statut: LOCKED_OWNER_APPROVED**  
**Capacités: 104**

Promoteur à miniature en gouvernance locale: consulter et contrôler. Les décisions administratives sont traduites dans EduSync par un utilisateur techniquement autorisé.

## Capacités finales

- `audit.entity.history.read`
- `audit.school.export`
- `audit.school.filter`
- `audit.school.read`
- `communications.history.read`
- `communications.read`
- `contributions.read`
- `contributions.register.export_xlsx`
- `contributions.register.read`
- `dashboard.school.drilldown`
- `dashboard.school.export`
- `dashboard.school.print`
- `dashboard.school.read`
- `documents.history.read`
- `documents.open`
- `documents.print`
- `enrollments.arrears.read`
- `enrollments.export_pdf`
- `enrollments.export_xlsx`
- `enrollments.print`
- `enrollments.read`
- `families.children.read`
- `families.read`
- `families.responsibles.read`
- `finance.advance_funds.read`
- `finance.advance_funds.receipt.print`
- `finance.analysis.advance.read`
- `finance.analysis.by_cashier.read`
- `finance.analysis.by_fee.read`
- `finance.anticipation_plans.read`
- `finance.cash.journal.export_pdf`
- `finance.cash.journal.print`
- `finance.cash.other.read`
- `finance.cash.read`
- `finance.checkout.allocate.preview`
- `finance.checkout.balance.read`
- `finance.checkout.recommend`
- `finance.checkout.search`
- `finance.credits.read`
- `finance.dashboard.read`
- `finance.decisions.read`
- `finance.old_debt.read`
- `finance.payments.history.read`
- `finance.products.read`
- `finance.products.sales_report.read`
- `finance.receipts.read`
- `finance.recovery.historical.read`
- `finance.recovery.monthly.read`
- `finance.reports.daily.generate`
- `finance.reports.history.read`
- `finance.reports.periodic.export_pdf`
- `finance.reports.periodic.export_xlsx`
- `finance.reports.periodic.generate`
- `finance.responsibility.read`
- `finance.views.summaries.export_xlsx`
- `finance.views.vf01.export_pdf`
- `finance.views.vf01.export_xlsx`
- `finance.views.vf01.print`
- `finance.views.vf01.read`
- `finance.views.vf02.read`
- `finance.views.vf03.read`
- `finance.views.vf04.read`
- `headcounts.by_class.read`
- `headcounts.by_option.read`
- `headcounts.by_section.read`
- `headcounts.export_pdf`
- `headcounts.export_xlsx`
- `headcounts.movements.read`
- `headcounts.print`
- `headcounts.read`
- `inventory.assets.history.read`
- `inventory.assets.read`
- `inventory.counts.export_xlsx`
- `inventory.counts.print`
- `inventory.counts.read`
- `inventory.stock.export_xlsx`
- `inventory.stock.low_alerts.read`
- `inventory.stock.movements.read`
- `inventory.stock.read`
- `inventory.stock.sheet.print`
- `notifications.internal.read`
- `notifications.internal.read_all`
- `personnel.assignments.read`
- `personnel.functions.read`
- `personnel.read`
- `personnel.staff_children.read`
- `personnel.summary.read`
- `settings.academic_year.read`
- `settings.benefits.read`
- `settings.contributions.read`
- `settings.documents.history.read`
- `settings.documents.read`
- `settings.enrollment_policy.read`
- `settings.fee_types.read`
- `settings.payment_policy.read`
- `settings.products.read`
- `settings.school_identity.read`
- `settings.structure.read`
- `settings.tariffs.read`
- `students.account.export_pdf`
- `students.account.print`
- `students.account.read`
- `students.lifecycle.history.read`
- `students.read`

## Amendement du 26/10/2026 — gestion du personnel (décision du propriétaire)

Question posée lors de la certification du rôle : la décision initiale listait le Personnel en **lecture seule**, alors
que le registre canonique (`contracts/CAPABILITY_REGISTRY.json`, source de vérité depuis le 23/10/2026, reconstitué
depuis la base provisionnée) attribue au Gestionnaire les droits d'écriture du personnel, et que la décision du
24/10/2026 lui confie l'import du personnel (un import crée des agents).

**Décision du propriétaire (26/10/2026) : le Gestionnaire gère le personnel.** Il conserve :
`personnel.create`, `personnel.update`, `personnel.exit`, `personnel.assignments.add`, `personnel.assignments.end`,
`personnel.functions.manage`, `personnel.directory.export`, en plus des droits de lecture ci-dessus, et l'import
(`migration.staff.analyze`, `migration.staff.execute`).

Le Gestionnaire reste un rôle de **supervision financière sans opération de caisse** : pas d'encaissement
(`finance.checkout.collect`), pas de caisse personnelle (`finance.cash.open` / `close`), pas d'inscription, pas de
modification des paramètres de l'école. Ces interdictions sont vérifiées par le serveur (403) dans la recette
`frontend/browser-tests/local_gestionnaire_certification.mjs` et par `backend/tests/test_rbac_every_active_right_is_enforced.py`.

Le contrat `contracts/POINT3B_ROLE_DECISIONS_FINAL.json` (118 capacités) est **historique** ; le contrat en vigueur est
le registre canonique (141 capacités pour le Gestionnaire depuis l'amendement du 27/10 ; 143 auparavant, dont 25 issues des décisions du 23/10 — fusion des formats
d'export —, du 24/10 — imports — et de cet amendement).

**Amendement du propriétaire (27/10/2026) : pas de clôture de la journée.** « Le Gestionnaire n'est pas un opérateur
permanent, c'est un chef. » Lui imposer la clôture bloquerait la journée des caissiers. `finance.cash.day.close` et
`finance.cash.reopen` sont retirés du rôle standard (migration `0096_gestionnaire_no_cash_day_close.sql`) ; aucun rôle
standard ne les détient ; une école peut les attribuer au rôle de son choix. Chaque caissier clôture sa propre caisse.
