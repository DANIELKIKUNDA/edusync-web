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
 for f in ('schooling.tsx','personnel.tsx','finance.tsx'):
  s=(ROOT/'frontend/src'/f).read_text(encoding='utf-8')
  assert 'accept=".xlsx"' in s
 assert 'studentImportTemplate(token,year)' in (ROOT/'frontend/src/schooling.tsx').read_text(encoding='utf-8')

def test_import_api_is_fail_closed_for_non_xlsx_and_contract_parser_is_shared():
 s=(ROOT/'backend/src/edusync/modules/migration_import/api/router.py').read_text(encoding='utf-8')
 assert s.count("ext!='xlsx'")>=3
 assert "read_official_xlsx(data,'STUDENTS')" in s
 assert "read_official_xlsx(data,'STAFF')" in s
 assert "read_official_xlsx(data,'FINANCE_HISTORY')" in s
