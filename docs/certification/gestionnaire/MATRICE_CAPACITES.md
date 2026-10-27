Rôle GESTIONNAIRE : 141 capacités — PASS 90 · FAIL 0 · NOT APPLICABLE 51

| Capacité | Cycle | Backend (contrôle) | Frontend | Tests | Résultat |
|---|---|---|---|---|---|
| `audit.entity.history.read` | ACTIVE | router.py | — | 1 | **PASS** — API seulement (pas d'écran dédié) |
| `audit.school.export` | PLANNED | — | — | 1 | **NOT APPLICABLE** — PLANNED : fonctionnalité non construite, masquée à l'écran |
| `audit.school.filter` | ACTIVE | router.py | — | 1 | **PASS** — API seulement (pas d'écran dédié) |
| `audit.school.read` | ACTIVE | memory.py, router.py +2 | access.tsx | 4 | **PASS** |
| `communications.history.read` | ACTIVE | router.py | communications.tsx | 1 | **PASS** |
| `communications.read` | ACTIVE | projection.py, router.py | communications.tsx | 1 | **PASS** |
| `contributions.read` | ACTIVE | projection.py, router.py | — | 1 | **PASS** — API seulement (pas d'écran dédié) |
| `contributions.register.export_xlsx` | ACTIVE | router.py | effectifs.tsx | 1 | **PASS** |
| `contributions.register.read` | ACTIVE | projection.py, catalog.py +1 | effectifs.tsx | 1 | **PASS** |
| `dashboard.school.drilldown` | DEPRECATED | — | — | — | **NOT APPLICABLE** — DEPRECATED → canonique |
| `dashboard.school.export` | DEPRECATED | — | — | 1 | **NOT APPLICABLE** — DEPRECATED → canonique |
| `dashboard.school.print` | DEPRECATED | — | — | 1 | **NOT APPLICABLE** — DEPRECATED → canonique |
| `dashboard.school.read` | DEPRECATED | — | — | 1 | **NOT APPLICABLE** — DEPRECATED → canonique |
| `documents.history.read` | ACTIVE | projection.py, router.py | documents.tsx | 2 | **PASS** |
| `documents.open` | ACTIVE | projection.py, router.py | documents.tsx | 1 | **PASS** |
| `documents.print` | PLANNED | — | — | 1 | **NOT APPLICABLE** — PLANNED : fonctionnalité non construite, masquée à l'écran |
| `enrollments.arrears.read` | DEPRECATED | — | — | — | **NOT APPLICABLE** — DEPRECATED → students.account.read |
| `enrollments.export` | PLANNED | — | — | — | **NOT APPLICABLE** — PLANNED : fonctionnalité non construite, masquée à l'écran |
| `enrollments.export_pdf` | ALIAS | — | — | — | **NOT APPLICABLE** — ALIAS → enrollments.export |
| `enrollments.export_xlsx` | ALIAS | — | — | — | **NOT APPLICABLE** — ALIAS → enrollments.export |
| `enrollments.print` | ALIAS | — | — | — | **NOT APPLICABLE** — ALIAS → enrollments.export |
| `enrollments.read` | DEPRECATED | — | — | — | **NOT APPLICABLE** — DEPRECATED → canonique |
| `families.children.read` | DEPRECATED | — | — | — | **NOT APPLICABLE** — DEPRECATED → canonique |
| `families.directory.export` | ACTIVE | projection.py, router.py | schooling.tsx | 1 | **PASS** |
| `families.directory.export_xlsx` | ALIAS | — | — | 2 | **NOT APPLICABLE** — ALIAS → families.directory.export |
| `families.directory.print_pdf` | ALIAS | — | — | 2 | **NOT APPLICABLE** — ALIAS → families.directory.export |
| `families.read` | ACTIVE | projection.py, catalog.py +1 | schooling.tsx | 1 | **PASS** |
| `families.responsibles.read` | DEPRECATED | — | — | — | **NOT APPLICABLE** — DEPRECATED → canonique |
| `finance.advance_funds.read` | ACTIVE | projection.py, router.py | funds_ui.tsx | 1 | **PASS** |
| `finance.advance_funds.receipt.print` | ACTIVE | router.py | finance.tsx, funds_ui.tsx | 1 | **PASS** |
| `finance.advance_funds.refund` | ACTIVE | router.py | finance.tsx | 2 | **PASS** |
| `finance.analysis.advance.read` | ACTIVE | router.py | reports_hub.tsx, reports_ui.tsx | 1 | **PASS** |
| `finance.analysis.by_cashier.read` | ACTIVE | router.py | reports_hub.tsx, reports_ui.tsx | 1 | **PASS** |
| `finance.analysis.by_fee.read` | ACTIVE | projection.py, router.py +1 | finance.tsx, reports_hub.tsx +2 | 2 | **PASS** |
| `finance.anticipation_plans.read` | ACTIVE | projection.py, router.py +1 | App.tsx, finance.tsx | 2 | **PASS** |
| `finance.cash.journal.export` | ACTIVE | router.py | cash_controls.tsx, cash_desk.tsx | 1 | **PASS** |
| `finance.cash.journal.export_pdf` | ALIAS | — | — | — | **NOT APPLICABLE** — ALIAS → finance.cash.journal.export |
| `finance.cash.journal.print` | ALIAS | — | — | — | **NOT APPLICABLE** — ALIAS → finance.cash.journal.export |
| `finance.cash.other.read` | ACTIVE | projection.py, router.py +2 | cash_desk.tsx | 8 | **PASS** |
| `finance.cash.read` | ACTIVE | projection.py, router.py | finance.tsx | 2 | **PASS** |
| `finance.checkout.allocate.preview` | DEPRECATED | — | — | — | **NOT APPLICABLE** — DEPRECATED → canonique |
| `finance.checkout.balance.read` | ACTIVE | router.py | — | 3 | **PASS** — API seulement (pas d'écran dédié) |
| `finance.checkout.recommend` | DEPRECATED | — | — | — | **NOT APPLICABLE** — DEPRECATED → canonique |
| `finance.checkout.search` | ACTIVE | projection.py, router.py | — | 2 | **PASS** — API seulement (pas d'écran dédié) |
| `finance.credits.read` | ACTIVE | router.py | finance.tsx | 3 | **PASS** |
| `finance.dashboard.read` | DEPRECATED | — | — | 1 | **NOT APPLICABLE** — DEPRECATED → canonique |
| `finance.decisions.cancel` | ACTIVE | router.py | finance.tsx | 1 | **PASS** |
| `finance.decisions.create` | ACTIVE | router.py | decisions_ui.tsx | 2 | **PASS** |
| `finance.decisions.read` | ACTIVE | projection.py, router.py | App.tsx, finance.tsx | 1 | **PASS** |
| `finance.old_debt.read` | ACTIVE | router.py | finance.tsx | 1 | **PASS** |
| `finance.payments.history.read` | PLANNED | — | — | — | **NOT APPLICABLE** — PLANNED : fonctionnalité non construite, masquée à l'écran |
| `finance.payments.reverse.supervisor` | ACTIVE | router.py | cash_controls.tsx | 3 | **PASS** |
| `finance.products.read` | ACTIVE | projection.py, router.py | finance.tsx | 1 | **PASS** |
| `finance.products.sales_report.read` | ACTIVE | router.py | finance.tsx, reports_hub.tsx +1 | 1 | **PASS** |
| `finance.receipts.read` | ACTIVE | projection.py, router.py | finance.tsx | 1 | **PASS** |
| `finance.recovery.historical.read` | PLANNED | — | — | — | **NOT APPLICABLE** — PLANNED : fonctionnalité non construite, masquée à l'écran |
| `finance.recovery.monthly.read` | ACTIVE | projection.py, router.py +1 | finance.tsx | 3 | **PASS** |
| `finance.reports.daily.generate` | ACTIVE | router.py | cash_controls.tsx, finance.tsx +1 | 1 | **PASS** |
| `finance.reports.history.read` | ACTIVE | projection.py, router.py | finance.tsx, reports_hub.tsx +1 | 2 | **PASS** |
| `finance.reports.periodic.export` | ACTIVE | projection.py, router.py | reports_ui.tsx | 1 | **PASS** |
| `finance.reports.periodic.export_pdf` | ALIAS | — | — | — | **NOT APPLICABLE** — ALIAS → finance.reports.periodic.export |
| `finance.reports.periodic.export_xlsx` | ALIAS | — | — | 1 | **NOT APPLICABLE** — ALIAS → finance.reports.periodic.export |
| `finance.reports.periodic.generate` | ACTIVE | router.py | finance.tsx, reports_hub.tsx +1 | 3 | **PASS** |
| `finance.responsibility.read` | ACTIVE | router.py | finance.tsx | 2 | **PASS** |
| `finance.responsibility.set` | ACTIVE | router.py | decisions_ui.tsx | 1 | **PASS** |
| `finance.views.summaries.export_xlsx` | PLANNED | — | — | — | **NOT APPLICABLE** — PLANNED : fonctionnalité non construite, masquée à l'écran |
| `finance.views.vf01.export` | ACTIVE | projection.py, router.py | finance_followup.tsx, recovery.tsx | 1 | **PASS** |
| `finance.views.vf01.export_pdf` | ALIAS | — | — | — | **NOT APPLICABLE** — ALIAS → finance.views.vf01.export |
| `finance.views.vf01.export_xlsx` | ALIAS | — | — | — | **NOT APPLICABLE** — ALIAS → finance.views.vf01.export |
| `finance.views.vf01.print` | ALIAS | — | — | — | **NOT APPLICABLE** — ALIAS → finance.views.vf01.export |
| `finance.views.vf01.read` | PLANNED | — | — | — | **NOT APPLICABLE** — PLANNED : fonctionnalité non construite, masquée à l'écran |
| `finance.views.vf02.read` | PLANNED | — | — | — | **NOT APPLICABLE** — PLANNED : fonctionnalité non construite, masquée à l'écran |
| `finance.views.vf03.read` | PLANNED | — | — | — | **NOT APPLICABLE** — PLANNED : fonctionnalité non construite, masquée à l'écran |
| `finance.views.vf04.read` | PLANNED | — | — | — | **NOT APPLICABLE** — PLANNED : fonctionnalité non construite, masquée à l'écran |
| `headcounts.by_class.read` | ACTIVE | router.py | — | 1 | **PASS** — API seulement (pas d'écran dédié) |
| `headcounts.by_option.read` | ACTIVE | router.py | — | 1 | **PASS** — API seulement (pas d'écran dédié) |
| `headcounts.by_section.read` | ACTIVE | router.py | — | 1 | **PASS** — API seulement (pas d'écran dédié) |
| `headcounts.export` | ACTIVE | projection.py, router.py | effectifs.tsx | 1 | **PASS** |
| `headcounts.export_pdf` | ALIAS | — | — | — | **NOT APPLICABLE** — ALIAS → headcounts.export |
| `headcounts.export_xlsx` | ALIAS | — | — | — | **NOT APPLICABLE** — ALIAS → headcounts.export |
| `headcounts.movements.read` | ACTIVE | projection.py, router.py | effectifs.tsx | 2 | **PASS** |
| `headcounts.print` | ALIAS | — | — | — | **NOT APPLICABLE** — ALIAS → headcounts.export |
| `headcounts.read` | ACTIVE | projection.py, catalog.py +1 | — | 3 | **PASS** — API seulement (pas d'écran dédié) |
| `inventory.assets.history.read` | ACTIVE | router.py | — | 1 | **PASS** — API seulement (pas d'écran dédié) |
| `inventory.assets.read` | ACTIVE | projection.py, router.py | stewardship.tsx | 1 | **PASS** |
| `inventory.counts.export` | PLANNED | — | — | — | **NOT APPLICABLE** — PLANNED : fonctionnalité non construite, masquée à l'écran |
| `inventory.counts.export_xlsx` | ALIAS | — | — | — | **NOT APPLICABLE** — ALIAS → inventory.counts.export |
| `inventory.counts.print` | ALIAS | — | — | — | **NOT APPLICABLE** — ALIAS → inventory.counts.export |
| `inventory.counts.read` | ACTIVE | projection.py, router.py | stewardship.tsx | 1 | **PASS** |
| `inventory.stock.export_xlsx` | PLANNED | — | — | 1 | **NOT APPLICABLE** — PLANNED : fonctionnalité non construite, masquée à l'écran |
| `inventory.stock.low_alerts.read` | PLANNED | — | — | — | **NOT APPLICABLE** — PLANNED : fonctionnalité non construite, masquée à l'écran |
| `inventory.stock.movements.read` | ACTIVE | router.py | stewardship.tsx | 1 | **PASS** |
| `inventory.stock.read` | ACTIVE | projection.py, router.py | stewardship.tsx | 3 | **PASS** |
| `inventory.stock.sheet.print` | PLANNED | — | — | 1 | **NOT APPLICABLE** — PLANNED : fonctionnalité non construite, masquée à l'écran |
| `migration.finance_history.analyze` | ACTIVE | router.py | finance.tsx | 1 | **PASS** |
| `migration.finance_history.execute` | ACTIVE | router.py | finance.tsx | 1 | **PASS** |
| `migration.staff.analyze` | ACTIVE | router.py | personnel.tsx | 2 | **PASS** |
| `migration.staff.execute` | ACTIVE | router.py | personnel.tsx | 2 | **PASS** |
| `notifications.internal.read` | ACTIVE | router.py, router.py +1 | App.tsx | 2 | **PASS** |
| `notifications.internal.read_all` | PLANNED | — | — | — | **NOT APPLICABLE** — PLANNED : fonctionnalité non construite, masquée à l'écran |
| `personnel.assignments.add` | ACTIVE | router.py | personnel.tsx | 2 | **PASS** |
| `personnel.assignments.end` | ACTIVE | router.py | personnel.tsx | 2 | **PASS** |
| `personnel.assignments.read` | ACTIVE | router.py | personnel.tsx | 1 | **PASS** |
| `personnel.create` | ACTIVE | router.py | personnel.tsx | 5 | **PASS** |
| `personnel.directory.export` | ACTIVE | projection.py, router.py | personnel.tsx | 1 | **PASS** |
| `personnel.directory.export_xlsx` | ALIAS | — | — | 1 | **NOT APPLICABLE** — ALIAS → personnel.directory.export |
| `personnel.directory.print_pdf` | ALIAS | — | — | 2 | **NOT APPLICABLE** — ALIAS → personnel.directory.export |
| `personnel.exit` | ACTIVE | router.py | personnel.tsx | 4 | **PASS** |
| `personnel.functions.manage` | ACTIVE | router.py | personnel.tsx | 2 | **PASS** |
| `personnel.functions.read` | ACTIVE | router.py | personnel.tsx | 1 | **PASS** |
| `personnel.history.read` | ACTIVE | router.py | personnel.tsx | 1 | **PASS** |
| `personnel.payroll_deduction.cancel` | ACTIVE | router.py | staff_finance_ui.tsx | 1 | **PASS** |
| `personnel.payroll_deduction.confirm` | ACTIVE | router.py | staff_finance_ui.tsx | 2 | **PASS** |
| `personnel.profile.print_pdf` | ACTIVE | router.py | personnel.tsx | 1 | **PASS** |
| `personnel.read` | ACTIVE | projection.py, router.py | personnel.tsx | 6 | **PASS** |
| `personnel.staff_children.finance_mode` | ACTIVE | router.py | staff_finance_ui.tsx | 1 | **PASS** |
| `personnel.staff_children.read` | ACTIVE | router.py | — | 1 | **PASS** — API seulement (pas d'écran dédié) |
| `personnel.summary.read` | ACTIVE | projection.py, router.py | personnel.tsx | 5 | **PASS** |
| `personnel.update` | ACTIVE | router.py | personnel.tsx | 3 | **PASS** |
| `settings.academic_year.read` | ACTIVE | memory.py, router.py +2 | App.tsx | 3 | **PASS** |
| `settings.benefits.read` | ACTIVE | projection.py, router.py | App.tsx | 1 | **PASS** |
| `settings.contributions.read` | ACTIVE | projection.py, router.py | App.tsx | 2 | **PASS** |
| `settings.documents.history.read` | DEPRECATED | — | — | — | **NOT APPLICABLE** — DEPRECATED → documents.history.read |
| `settings.documents.read` | ACTIVE | projection.py, router.py | App.tsx | 1 | **PASS** |
| `settings.enrollment_policy.read` | ACTIVE | projection.py, router.py | App.tsx | 1 | **PASS** |
| `settings.fee_types.read` | ACTIVE | memory.py, projection.py +1 | App.tsx, settings_wizards.tsx | 2 | **PASS** |
| `settings.payment_policy.read` | ACTIVE | projection.py, router.py | App.tsx | 1 | **PASS** |
| `settings.products.read` | ACTIVE | projection.py, router.py | App.tsx | 2 | **PASS** |
| `settings.school_identity.read` | ACTIVE | memory.py, projection.py +1 | App.tsx | 3 | **PASS** |
| `settings.structure.read` | ACTIVE | memory.py, router.py +2 | App.tsx | 2 | **PASS** |
| `settings.tariffs.read` | ACTIVE | memory.py, projection.py +1 | App.tsx, settings_tariffs.tsx +1 | 2 | **PASS** |
| `students.account.export` | ACTIVE | projection.py, router.py | decisions_ui.tsx, student_finance.tsx | 1 | **PASS** |
| `students.account.export_pdf` | ALIAS | — | — | — | **NOT APPLICABLE** — ALIAS → students.account.export |
| `students.account.print` | ALIAS | — | — | — | **NOT APPLICABLE** — ALIAS → students.account.export |
| `students.account.read` | ACTIVE | router.py, router.py | schooling.tsx | 1 | **PASS** |
| `students.directory.export` | ACTIVE | projection.py, router.py | schooling.tsx, schooling_kit.tsx | 1 | **PASS** |
| `students.directory.export_xlsx` | ALIAS | — | — | 2 | **NOT APPLICABLE** — ALIAS → students.directory.export |
| `students.directory.print_pdf` | ALIAS | — | — | 3 | **NOT APPLICABLE** — ALIAS → students.directory.export |
| `students.lifecycle.history.read` | PLANNED | — | — | — | **NOT APPLICABLE** — PLANNED : fonctionnalité non construite, masquée à l'écran |
| `students.profile.print_pdf` | ACTIVE | router.py | schooling.tsx | 3 | **PASS** |
| `students.read` | ACTIVE | projection.py, router.py | — | 4 | **PASS** — API seulement (pas d'écran dédié) |
