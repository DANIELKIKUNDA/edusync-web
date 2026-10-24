-- 0086 — A school can save its own identity (Paramètres → École & identité). Defect found 2026-10-24: the tenant role
-- only had SELECT on schools, so every save failed with « droit refusé pour la table schools » (HTTP 500) although
-- row-level security (schools_tenant, 0003) already limits the role to its own school.
-- Column-level grant: identity columns only. The code and the status of a school stay platform decisions.
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_tenant') THEN
    GRANT UPDATE (name, logo_url, email, phone, address, city, province, updated_at, version) ON schools TO edusync_tenant;
  END IF;
END $$;
