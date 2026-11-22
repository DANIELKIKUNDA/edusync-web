-- Rollback of 0125_pedagogy_calendar_programmes (manual, owner decision only). The calendars and programmes of the
-- schools are lost: export them first if they matter.
DELETE FROM rbac_role_capabilities WHERE capability_code IN ('pedagogy.calendar.manage','pedagogy.programmes.manage');
DELETE FROM capability_catalog WHERE code IN ('pedagogy.calendar.manage','pedagogy.programmes.manage');
DROP TABLE IF EXISTS pedagogy_programme_lines;
DROP TABLE IF EXISTS pedagogy_programmes;
DROP TABLE IF EXISTS pedagogy_calendar_periods;
DROP TABLE IF EXISTS pedagogy_calendars;
DELETE FROM schema_migrations WHERE version='0125_pedagogy_calendar_programmes';
