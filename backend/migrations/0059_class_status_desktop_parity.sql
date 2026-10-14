-- Desktop parity (owner decision 2026-10-14, golden master app/db/configuration.py::set_class_status):
--  * a class is ACTIVE, INACTIVE ("en pause") or ARCHIVED;
--  * INACTIVE is allowed while the class still has students: they stay counted, visible and attached to it;
--  * ARCHIVED is refused while the class has validated enrollments; an archived class is read-only;
--  * `enabled` is kept as the "open for new enrollments / normal destination" flag (= status ACTIVE) so that every
--    existing selection list keeps its meaning.

ALTER TABLE school_classes ADD COLUMN IF NOT EXISTS status varchar(16);
UPDATE school_classes SET status = CASE WHEN enabled THEN 'ACTIVE' ELSE 'INACTIVE' END WHERE status IS NULL;
ALTER TABLE school_classes ALTER COLUMN status SET DEFAULT 'ACTIVE';
ALTER TABLE school_classes ALTER COLUMN status SET NOT NULL;
ALTER TABLE school_classes ADD COLUMN IF NOT EXISTS archived_at timestamptz;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'school_classes_status_ck') THEN
    ALTER TABLE school_classes ADD CONSTRAINT school_classes_status_ck CHECK (status IN ('ACTIVE', 'INACTIVE', 'ARCHIVED'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'school_classes_enabled_matches_status_ck') THEN
    ALTER TABLE school_classes ADD CONSTRAINT school_classes_enabled_matches_status_ck CHECK (enabled = (status = 'ACTIVE'));
  END IF;
END $$;
