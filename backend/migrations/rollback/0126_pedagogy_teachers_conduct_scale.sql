-- Rollback of 0126 (manual, owner decision only). Assignments, titulars and conduct scales of the schools are lost;
-- the ENSEIGNANT role is archived (never deleted: members may still hold it).
DELETE FROM rbac_role_capabilities WHERE capability_code IN ('pedagogy.teaching.own.read','pedagogy.teaching.manage','pedagogy.conduct.configure');
DELETE FROM rbac_role_capabilities rc USING rbac_roles r WHERE rc.role_id=r.id AND r.code='ENSEIGNANT' AND r.kind='SCHOOL_STANDARD';
UPDATE rbac_roles SET status='ARCHIVED', version=version+1, updated_at=now() WHERE code='ENSEIGNANT' AND kind='SCHOOL_STANDARD';
DELETE FROM capability_catalog WHERE code IN ('pedagogy.teaching.own.read','pedagogy.teaching.manage','pedagogy.conduct.configure');
DROP TABLE IF EXISTS pedagogy_conduct_settings;
DROP TABLE IF EXISTS pedagogy_conduct_rules;
DROP TABLE IF EXISTS pedagogy_class_titulars;
DROP TABLE IF EXISTS pedagogy_teaching_assignments;
DELETE FROM schema_migrations WHERE version='0126_pedagogy_teachers_conduct_scale';
