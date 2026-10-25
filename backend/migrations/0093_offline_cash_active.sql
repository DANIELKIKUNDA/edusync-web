-- Owner decision 2026-10-25: « au niveau école, le système doit fonctionner sans internet puis synchroniser ».
-- finance.checkout.offline_cash (already held by the CAISSIER standard role) becomes ACTIVE: it guards the offline pack
-- (/finance/checkout/offline-pack) that lets the cash desk keep collecting without network; offline payments are replayed
-- later with their Idempotency-Key and re-checked by the server. Lifecycle change only: no role gains or loses a right.
UPDATE capability_catalog SET lifecycle = 'ACTIVE', updated_at = now()
 WHERE code = 'finance.checkout.offline_cash' AND lifecycle = 'PLANNED';
