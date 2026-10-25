from pathlib import Path
ROOT=Path(__file__).parents[2]
def test_import_migration_is_tenant_safe_and_staged():
 s=(ROOT/'backend/migrations/0033_student_import_staging.sql').read_text()
 assert 'student_import_batches' in s and 'student_import_rows' in s
 assert s.count('FORCE ROW LEVEL SECURITY')>=2
 assert "nullif(current_setting('app.current_school_id', true), '')::uuid" in s
 assert 'current_school_id()' not in s
def test_import_api_requires_capabilities_and_explicit_confirmation():
 s=(ROOT/'backend/src/edusync/modules/migration_import/api/router.py').read_text()
 for x in ['migration.students.analyze','migration.students.execute','Idempotency-Key obligatoire','confirm_separate_households','POSSIBLE_DUPLICATE','FOR UPDATE'] : assert x in s
 assert "len(parsed)>5000" in s and "status='IMPORTED'" in s
def test_import_ui_is_preview_first_and_permissioned():
 # 2026-10-25: the import screen moved to schooling_import.tsx (guided stepper), still mounted by schooling.tsx.
 s=(ROOT/'frontend/src/schooling.tsx').read_text(encoding='utf-8')+(ROOT/'frontend/src/schooling_import.tsx').read_text(encoding='utf-8')
 for x in ['migration.students.analyze','migration.students.execute','Analyser le fichier','Importer définitivement','Aucun foyer n’est fusionné silencieusement'] : assert x in s
def test_provisioner_includes_import_migration():
 s=(ROOT/'backend/scripts/provision_database.py').read_text(); assert '0033_student_import_staging.sql' in s
