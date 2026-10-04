from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def test_staff_import_migration_rls_and_capabilities():
 s=(ROOT/'backend/migrations/0034_staff_import_staging.sql').read_text()
 for x in ['staff_import_batches','staff_import_rows','FORCE ROW LEVEL SECURITY','migration.staff.analyze','migration.staff.execute','personnel.create'] : assert x in s
def test_staff_import_backend_contract():
 s=(ROOT/'backend/src/edusync/modules/migration_import/api/router.py').read_text()
 for x in ["/staff/template.xlsx","/staff/analyze","/staff/batches/{batch_id}/execute","FOR UPDATE","Idempotency-Key obligatoire","STAFF_IMPORT_ANALYZED","STAFF_IMPORT_EXECUTED","Maximum 5 000 agents"]: assert x in s
 assert "employee_no" in s and "POSSIBLE_DUPLICATE" in s and "EMPLOYEE_NO_EXISTS" in s
def test_staff_import_frontend_contract():
 s=(ROOT/'frontend/src/personnel.tsx').read_text();a=(ROOT/'frontend/src/api.ts').read_text()
 for x in ['migration.staff.analyze','migration.staff.execute','Import du personnel','Télécharger le modèle','Importer définitivement']: assert x in s
 for x in ['staffImportTemplate','analyzeStaffImport','executeStaffImport']: assert x in a
def test_provisioner_includes_0034():
 assert '0034_staff_import_staging.sql' in (ROOT/'backend/scripts/provision_database.py').read_text()
