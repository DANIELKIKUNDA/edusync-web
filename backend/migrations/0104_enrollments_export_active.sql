-- Owner decision 2026-10-30: the register of enrollments is built (GET /schooling/exports/enrollments.pdf|.xlsx, section
-- scope applied in SQL, archived). enrollments.export (business capability; *.export_pdf / *.export_xlsx / *.print are its
-- aliases) becomes ACTIVE. Lifecycle change only, like 0093: no role gains or loses a right — the holders are those of
-- the locked contracts (Caissier, Gestionnaire, Promoteur, Préfet, Direction de section, Directeurs des études / discipline).
UPDATE capability_catalog SET lifecycle = 'ACTIVE', updated_at = now() WHERE code = 'enrollments.export' AND lifecycle = 'PLANNED';
