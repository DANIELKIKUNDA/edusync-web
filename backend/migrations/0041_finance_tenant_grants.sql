-- Certification 2026-09-30 — least-privilege tenant grants for the canonical Finance ledger.
-- Defect reproduced on a fresh install: finance_payments & co. had RLS/FORCE RLS but no GRANT to
-- edusync_tenant, so cash opening and checkout failed with InsufficientPrivilege (HTTP 500).
-- Grants are derived from the statements the API actually executes. RLS policies are unchanged.
-- Payments and allocations stay append-only: no UPDATE/DELETE for the tenant role.
GRANT SELECT, INSERT ON finance_payments, finance_payment_allocations TO edusync_tenant;
REVOKE UPDATE, DELETE ON finance_payments, finance_payment_allocations FROM edusync_tenant;

-- Allocation only moves the paid counter; the official tariff/net amount is never writable here.
GRANT UPDATE (paid_amount, updated_at) ON finance_charges TO edusync_tenant;

GRANT SELECT, INSERT ON finance_advance_allocations, finance_advance_targets TO edusync_tenant;
REVOKE UPDATE, DELETE ON finance_advance_allocations, finance_advance_targets FROM edusync_tenant;
GRANT SELECT ON finance_anticipation_plans TO edusync_tenant;
GRANT SELECT, INSERT ON finance_anticipation_memberships TO edusync_tenant;
GRANT UPDATE (status, decided_at, decided_by) ON finance_anticipation_memberships TO edusync_tenant;

-- Financial decisions are cancelled (traceable), never deleted.
GRANT INSERT ON finance_decisions TO edusync_tenant;
GRANT UPDATE (status, cancelled_by, cancelled_at, cancel_reason) ON finance_decisions TO edusync_tenant;
GRANT SELECT, INSERT ON finance_responsibilities, finance_report_templates TO edusync_tenant;
GRANT SELECT ON finance_credits TO edusync_tenant;
