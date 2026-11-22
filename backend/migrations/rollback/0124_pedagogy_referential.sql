-- Rollback of 0124_pedagogy_referential (manual, owner decision only). The class links of the schools are lost: export
-- them first if they matter. The referential itself is rebuilt from the repository at the next provisioning.
DELETE FROM rbac_role_capabilities WHERE capability_code IN ('pedagogy.referential.read','pedagogy.class_links.manage');
DELETE FROM capability_catalog WHERE code IN ('pedagogy.referential.read','pedagogy.class_links.manage');
DROP TABLE IF EXISTS pedagogy_class_links;
DROP TABLE IF EXISTS ref_programme_lines;
DROP TABLE IF EXISTS ref_courses;
DROP TABLE IF EXISTS ref_classes;
DROP TABLE IF EXISTS ref_options;
DROP TABLE IF EXISTS ref_sections;
DROP TABLE IF EXISTS ref_programme_versions;
DELETE FROM schema_migrations WHERE version='0124_pedagogy_referential';
