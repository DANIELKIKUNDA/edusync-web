-- EduSync Point 4C preservation correction — 2026-09-12
-- Restore certified Desktop school identity fields needed by canonical PDF/XLSX headers.
ALTER TABLE schools ADD COLUMN IF NOT EXISTS address text;
ALTER TABLE schools ADD COLUMN IF NOT EXISTS city varchar(120);
ALTER TABLE schools ADD COLUMN IF NOT EXISTS province varchar(120);

-- Existing historical rows may have NULL gender; no destructive backfill is allowed.
-- New enrollment validation enforces M/F at the application boundary.
