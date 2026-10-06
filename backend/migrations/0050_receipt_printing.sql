-- Local closure 2026-10: receipt printing, decoupled from the payment commit (Point 5B rule 2).
-- Print policy per school (Point 5B): NONE (default) | PROPOSE (offer after validation) | AUTO_PREVIEW
-- (open the preview automatically; browsers never print silently). Direct printing to a device needs a
-- local print bridge and is documented separately; it is not simulated here.
CREATE TABLE IF NOT EXISTS school_print_settings (
 school_id uuid PRIMARY KEY REFERENCES schools(id) ON DELETE CASCADE,
 receipt_policy varchar(16) NOT NULL DEFAULT 'NONE' CHECK (receipt_policy IN ('NONE','PROPOSE','AUTO_PREVIEW')),
 receipt_format varchar(8) NOT NULL DEFAULT 'A5' CHECK (receipt_format IN ('A5','80MM')),
 updated_by uuid REFERENCES users(id), updated_at timestamptz NOT NULL DEFAULT now(), version integer NOT NULL DEFAULT 1
);
-- Every receipt print is evidence: the first is the ORIGINAL, every later one a DUPLICATA.
CREATE TABLE IF NOT EXISTS finance_receipt_prints (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 school_id uuid NOT NULL REFERENCES schools(id),
 payment_id uuid NOT NULL REFERENCES finance_payments(id),
 copy_no integer NOT NULL CHECK (copy_no >= 1),
 kind varchar(12) NOT NULL CHECK (kind IN ('ORIGINAL','DUPLICATA')),
 printed_by uuid NOT NULL REFERENCES users(id),
 printed_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (payment_id, copy_no)
);
ALTER TABLE school_print_settings ENABLE ROW LEVEL SECURITY; ALTER TABLE school_print_settings FORCE ROW LEVEL SECURITY;
ALTER TABLE finance_receipt_prints ENABLE ROW LEVEL SECURITY; ALTER TABLE finance_receipt_prints FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS school_print_settings_tenant ON school_print_settings;
CREATE POLICY school_print_settings_tenant ON school_print_settings USING (school_id=current_setting('app.current_school_id',true)::uuid) WITH CHECK (school_id=current_setting('app.current_school_id',true)::uuid);
DROP POLICY IF EXISTS finance_receipt_prints_tenant ON finance_receipt_prints;
CREATE POLICY finance_receipt_prints_tenant ON finance_receipt_prints USING (school_id=current_setting('app.current_school_id',true)::uuid) WITH CHECK (school_id=current_setting('app.current_school_id',true)::uuid);
GRANT SELECT, INSERT, UPDATE ON school_print_settings TO edusync_tenant;
REVOKE DELETE ON school_print_settings FROM edusync_tenant;
GRANT SELECT, INSERT ON finance_receipt_prints TO edusync_tenant;
REVOKE UPDATE, DELETE ON finance_receipt_prints FROM edusync_tenant;
