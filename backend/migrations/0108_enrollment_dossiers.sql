-- Atomic enrollment (owner report 2026-11-06): a pupil is enrolled only when the school's enrollment conditions are paid,
-- in the same transaction as the payment. When the person who fills in the form cannot collect money, the form is kept
-- as a DOSSIER « en attente de paiement »: nothing is enrolled, no pupil, no family, no charge. The cashier opens it,
-- collects and the enrollment happens in that one operation (status COMPLETED). A direction waiver (« dérogation ») is
-- recorded on the dossier, per child, with its reason and author.
CREATE TABLE IF NOT EXISTS enrollment_dossiers (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  academic_year_id uuid NOT NULL REFERENCES academic_years(id),
  status varchar(12) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','COMPLETED','CANCELLED')),
  label varchar(200) NOT NULL,
  children_count integer NOT NULL CHECK (children_count BETWEEN 1 AND 20),
  payload jsonb NOT NULL,
  totals jsonb NOT NULL DEFAULT '{}'::jsonb,
  waivers jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_by uuid NOT NULL REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  completed_by uuid REFERENCES users(id),
  completed_at timestamptz,
  family_id uuid,
  cancelled_by uuid REFERENCES users(id),
  cancelled_at timestamptz,
  cancel_reason text,
  version integer NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_enrollment_dossiers_pending ON enrollment_dossiers(school_id, created_at DESC) WHERE status = 'PENDING';
ALTER TABLE enrollment_dossiers ENABLE ROW LEVEL SECURITY;
ALTER TABLE enrollment_dossiers FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS enrollment_dossiers_tenant ON enrollment_dossiers;
CREATE POLICY enrollment_dossiers_tenant ON enrollment_dossiers
  USING (school_id = current_setting('app.school_id', true)::uuid)
  WITH CHECK (school_id = current_setting('app.school_id', true)::uuid);
GRANT SELECT, INSERT, UPDATE ON enrollment_dossiers TO edusync_tenant;
