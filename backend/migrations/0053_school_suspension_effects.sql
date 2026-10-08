-- N1 certification 2026-10: a suspended school stops sending SMS. The worker reads only the status of the school
-- owning a delivery (column-level grant id,status in the provisioner); pending deliveries are held, not lost,
-- and resume on reactivation.
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_worker') THEN
    DROP POLICY IF EXISTS schools_worker_status ON schools;
    CREATE POLICY schools_worker_status ON schools FOR SELECT TO edusync_worker USING (true);
  END IF;
END $$;
