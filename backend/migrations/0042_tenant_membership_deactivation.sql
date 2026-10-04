-- Certification 2026-10-01 — staff exit must revoke the linked access account.
-- Defect reproduced live: personnel exit runs in the tenant transaction and deactivates linked
-- memberships, but edusync_tenant had no UPDATE on school_memberships -> HTTP 500, the whole exit
-- rolled back and the departed agent kept a working account.
-- Narrowest grant: two columns only, and a RESTRICTIVE policy so the tenant role can only ever
-- DEACTIVATE a membership of its own school (reactivation stays a platform operation).
GRANT UPDATE (active, version) ON school_memberships TO edusync_tenant;
DROP POLICY IF EXISTS school_memberships_tenant_deactivate_only ON school_memberships;
CREATE POLICY school_memberships_tenant_deactivate_only ON school_memberships
  AS RESTRICTIVE FOR UPDATE TO edusync_tenant
  USING (true)
  WITH CHECK (active = false);
