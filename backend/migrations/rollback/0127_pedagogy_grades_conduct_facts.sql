-- Rollback of 0127 (manual, owner decision only). ALL grades and conduct facts of the schools are lost: export them first.
DELETE FROM rbac_role_capabilities WHERE capability_code IN ('pedagogy.grades.enter','pedagogy.grades.read','pedagogy.conduct.report','pedagogy.conduct.manage');
DELETE FROM capability_catalog WHERE code IN ('pedagogy.grades.enter','pedagogy.grades.read','pedagogy.conduct.report','pedagogy.conduct.manage');
DROP TABLE IF EXISTS pedagogy_conduct_adjustments;
DROP TABLE IF EXISTS pedagogy_conduct_facts;
DROP TABLE IF EXISTS pedagogy_grade_history;
DROP TABLE IF EXISTS pedagogy_grades;
DELETE FROM schema_migrations WHERE version='0127_pedagogy_grades_conduct_facts';
