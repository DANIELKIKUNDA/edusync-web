# Décision Point 3B — Promoteur

**Statut: LOCKED_OWNER_APPROVED**  
**Capacités: 104**

Consultation de gouvernance uniquement. Aucune opération métier quotidienne et aucune communication aux parents.

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

## Amendement du propriétaire (28/10/2026)

Reprise de l'historique financier : le Promoteur **analyse** (`migration.finance_history.analyze`) mais n'**exécute** pas (`migration.finance_history.execute` retiré, migration `0097_promoteur_finance_no_history_execute.sql`). L'exécution écrit d'anciens paiements et dettes dans les comptes ; elle reste au Gestionnaire et au Caissier. Certification : `docs/certification/RESPONSABLE_FINANCE_PROMOTEUR_CERTIFICATION.md`.
