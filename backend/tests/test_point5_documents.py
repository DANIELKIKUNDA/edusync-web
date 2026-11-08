from io import BytesIO
from openpyxl import load_workbook
from edusync.modules.documents.domain.catalog import CATALOG
from edusync.modules.documents.application.templates import student_import_template_xlsx,HEADERS

def test_canonical_catalog_has_exactly_20_families_and_no_duplicate_codes():
    # 16 Desktop families + fiches élèves, registre des inscriptions, recouvrement, fiches agents (2026-11-08)
    assert len(CATALOG)==20
    assert len({x.code for x in CATALOG})==20
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


def test_every_archived_document_code_has_its_catalog_folder():
    """Owner report 2026-11-08: every document the server archives lands in a named catalog folder."""
    from edusync.modules.documents.domain.catalog import catalog_family
    codes={'students.directory':'schooling.student_directory','families.directory':'schooling.family_directory','students.profile':'schooling.student_profile',
           'enrollments.register':'schooling.enrollment_register','students.account':'finance.student_statement','personnel.register':'personnel.staff_register',
           'personnel.profile.123':'personnel.staff_profile','finance.cash.session_journal':'cash.journal','finance.cash.journal':'cash.journal','finance.cash.sessions':'cash.journal',
           'finance.reports.periodic.CONSOLIDE':'finance.periodic_report','finance.reports.daily':'finance.daily_report','finance.recovery.monthly.CDF':'finance.recovery',
           'finance.recovery.class_register.x.USD':'finance.recovery','finance.recovery.summary.school.CDF':'finance.recovery','finance.recovery.followup':'finance.recovery',
           'headcounts.section':'effectifs.headcounts','contributions.register':'effectifs.contributions'}
    for code,family in codes.items():
        assert catalog_family(code) is not None and catalog_family(code).code==family, code
