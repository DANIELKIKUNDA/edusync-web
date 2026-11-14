from io import BytesIO
from pathlib import Path
import pytest
from openpyxl import load_workbook
from edusync.modules.migration_import.import_contract import build_template,read_official_xlsx,META_SHEET,DATA_SHEET,INSTRUCTIONS_SHEET,REF_SHEET,CONTRACTS
ROOT=Path(__file__).resolve().parents[2]

def test_all_official_templates_have_versioned_hidden_contract_and_guidance():
 for kind in CONTRACTS:
  b=build_template(kind,references={'Classe*':['1A','2A']} if kind=='STUDENTS' else {})
  wb=load_workbook(BytesIO(b),data_only=True)
  assert INSTRUCTIONS_SHEET in wb.sheetnames and REF_SHEET in wb.sheetnames and META_SHEET in wb.sheetnames
  data_sheet={'STUDENTS':'Import élèves','STAFF':'Import personnel','FINANCE_HISTORY':'Historique financier'}[kind]
  assert data_sheet in wb.sheetnames
  assert wb[META_SHEET].sheet_state=='veryHidden'
  assert wb[REF_SHEET].sheet_state=='hidden'
  assert wb[data_sheet]['A5'].value==CONTRACTS[kind]['headers'][0]
  assert wb[data_sheet].freeze_panes=='A6'

def test_parser_rejects_arbitrary_excel_and_tampered_headers():
 from openpyxl import Workbook
 wb=Workbook();bio=BytesIO();wb.save(bio)
 with pytest.raises(ValueError,match='modèle officiel'):read_official_xlsx(bio.getvalue(),'STAFF')
 b=build_template('STAFF');wb=load_workbook(BytesIO(b));ws=wb['Import personnel'];ws.protection.sheet=False;ws['A5']='Mauvaise colonne';bio=BytesIO();wb.save(bio)
 with pytest.raises(ValueError,match='Structure'):read_official_xlsx(bio.getvalue(),'STAFF')

def test_frontend_only_accepts_official_xlsx_and_explains_model_flow():
 # 2026-10-25: pupils and staff share the guided stepper of schooling_import.tsx (personnel.tsx mounts StaffImportPro).
 assert '<StaffImportPro' in (ROOT/'frontend/src/personnel.tsx').read_text(encoding='utf-8')
 for f in ('schooling_import.tsx','finance.tsx'):
  s=(ROOT/'frontend/src'/f).read_text(encoding='utf-8')
  assert 'accept=".xlsx"' in s
 assert 'studentImportTemplate(token, year)' in (ROOT/'frontend/src/schooling_import.tsx').read_text(encoding='utf-8')
 assert '<StudentImportPro' in (ROOT/'frontend/src/schooling.tsx').read_text(encoding='utf-8')

def test_import_api_is_fail_closed_for_non_xlsx_and_contract_parser_is_shared():
 s=(ROOT/'backend/src/edusync/modules/migration_import/api/router.py').read_text(encoding='utf-8')
 assert s.count("ext!='xlsx'")>=3
 assert "read_official_xlsx(data,'STUDENTS')" in s
 assert "read_official_xlsx(data,'STAFF')" in s
 assert "read_official_xlsx(data,'FINANCE_HISTORY')" in s

def test_students_contract_1_1_keeps_the_real_enrollment_date_and_still_reads_1_0_files():
 # Owner, 2026-11-01: « la date d'inscription doit rester la date réelle » — optional last column « Date inscription ».
 from edusync.modules.migration_import import import_contract as ic
 assert CONTRACTS['STUDENTS']['headers'][-1]=='Date inscription' and ic.contract_version('STUDENTS')=='1.1'
 b=build_template('STUDENTS',references={'Classe*':['1A']});wb=load_workbook(BytesIO(b));ws=wb['Import élèves'];ws.protection.sheet=False
 assert wb[META_SHEET]['B3'].value=='1.1' and ws.cell(5,15).value=='Date inscription'
 for j,v in enumerate(['KABEYA','MUKENDI','Grace','F','1A'],1):ws.cell(6,j,v)
 ws.cell(6,15,'07/09/2026');bio=BytesIO();wb.save(bio)
 rows=read_official_xlsx(bio.getvalue(),'STUDENTS')
 assert rows[0][1]['Date inscription']=='07/09/2026' and rows[0][1]['Nom*']=='KABEYA'
 # A 1.0 file (14 columns, former fingerprint) is still accepted: the date is simply absent.
 saved=dict(CONTRACTS['STUDENTS'])
 try:
  CONTRACTS['STUDENTS'].update(version='1.0',headers=ic.STUDENTS_V1_0)
  old=build_template('STUDENTS',references={'Classe*':['1A']})
 finally:
  CONTRACTS['STUDENTS'].clear();CONTRACTS['STUDENTS'].update(saved)
 wb=load_workbook(BytesIO(old));ws=wb['Import élèves'];ws.protection.sheet=False
 for j,v in enumerate(['KABEYA','MUKENDI','Grace','F','1A'],1):ws.cell(6,j,v)
 bio=BytesIO();wb.save(bio);rows=read_official_xlsx(bio.getvalue(),'STUDENTS')
 assert rows[0][1]['Prénom*']=='Grace' and 'Date inscription' not in rows[0][1]

def test_student_import_stores_the_real_date_and_refuses_a_future_one():
 s=(ROOT/'backend/src/edusync/modules/migration_import/api/router.py').read_text(encoding='utf-8')
 assert "row.get('Date inscription')" in s and "Date d'inscription dans le futur" in s
 assert "'enrolled_on':date.fromisoformat(n['enrolled_on'])" in s
