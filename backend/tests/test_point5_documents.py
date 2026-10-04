from io import BytesIO
from openpyxl import load_workbook
from edusync.modules.documents.domain.catalog import CATALOG
from edusync.modules.documents.application.templates import student_import_template_xlsx,HEADERS

def test_canonical_catalog_has_exactly_16_families_and_no_duplicate_codes():
    assert len(CATALOG)==16
    assert len({x.code for x in CATALOG})==16
    assert all(x.preservation=="MAXIMUM" for x in CATALOG)

def test_import_template_is_real_xlsx_with_mandatory_columns_and_instructions():
    data=student_import_template_xlsx(school_name="École Démo")
    assert data[:2]==b"PK"
    wb=load_workbook(BytesIO(data)); ws=wb["Import élèves"]
    assert [ws.cell(5,i).value for i in range(1,len(HEADERS)+1)]==HEADERS
    assert {"Nom*","Postnom*","Prénom*","Sexe*","Classe*"}.issubset(HEADERS)
    assert "Instructions" in wb.sheetnames

def test_financial_document_families_are_not_falsely_marked_web_certified():
    finance=[x for x in CATALOG if x.module=="Finance"]
    assert finance
    assert all(x.status=="DESKTOP_GOLDEN_REQUIRED" for x in finance)

def test_document_history_migration_is_append_only_rls():
    sql=open('migrations/0016_documents_domain.sql',encoding='utf-8').read()
    for token in ['ENABLE ROW LEVEL SECURITY','FORCE ROW LEVEL SECURITY','REVOKE UPDATE,DELETE','regeneration_of','sha256','object_key']:
        assert token in sql
