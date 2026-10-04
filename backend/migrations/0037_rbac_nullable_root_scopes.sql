-- Root PLATFORM/SCHOOL scopes have a NULL value by domain contract.
-- A primary key implicitly made this column NOT NULL, blocking all root grants.
ALTER TABLE rbac_assignment_scopes DROP CONSTRAINT IF EXISTS rbac_assignment_scopes_pkey;
ALTER TABLE rbac_assignment_scopes ALTER COLUMN scope_value DROP NOT NULL;
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid='rbac_assignment_scopes'::regclass AND conname='uq_rbac_assignment_scopes'
  ) THEN
    ALTER TABLE rbac_assignment_scopes ADD CONSTRAINT uq_rbac_assignment_scopes
      UNIQUE NULLS NOT DISTINCT (assignment_id,scope_type,scope_value);
  END IF;
END $$;
