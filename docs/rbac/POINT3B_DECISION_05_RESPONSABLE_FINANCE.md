# Décision Point 3B — Responsable chargé des finances

**Statut: LOCKED_OWNER_APPROVED**  
**Capacités: 67**

Contrôle financier global en lecture/rapports; pas d’encaissement ni de manipulation quotidienne de caisse.

## Capacités finales

- `audit.entity.history.read`
- `audit.school.export`
- `audit.school.filter`
- `audit.school.read`
- `dashboard.school.drilldown`
- `dashboard.school.export`
- `dashboard.school.print`
- `dashboard.school.read`
- `documents.history.read`
- `documents.open`
- `documents.print`
- `enrollments.arrears.read`
- `enrollments.read`
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
- `finance.receipts.print`
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
- `notifications.internal.read`
- `notifications.internal.read_all`
- `settings.benefits.read`
- `settings.contributions.read`
- `settings.enrollment_policy.read`
- `settings.fee_types.read`
- `settings.payment_policy.read`
- `settings.products.read`
- `settings.tariffs.read`
- `students.account.export_pdf`
- `students.account.print`
- `students.account.read`
- `students.read`

## Amendement du propriétaire (28/10/2026)

Reprise de l'historique financier : le Responsable chargé des finances **analyse** (`migration.finance_history.analyze`) mais n'**exécute** pas (`migration.finance_history.execute` retiré, migration `0097_promoteur_finance_no_history_execute.sql`). L'exécution écrit d'anciens paiements et dettes dans les comptes ; elle reste au Gestionnaire et au Caissier. Certification : `docs/certification/RESPONSABLE_FINANCE_PROMOTEUR_CERTIFICATION.md`.

Effectifs (décision du propriétaire, 28/10/2026) : le Responsable chargé des finances **lit** les effectifs — total, filles / garçons et par section — sur son tableau de bord (`headcounts.read`, `headcounts.by_section.read`, migration `0098_responsable_finance_headcounts.sql`). Lecture seule : ni mouvements, ni export, ni détail par classe.
