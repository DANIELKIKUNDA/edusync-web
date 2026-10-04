from io import BytesIO
from openpyxl import load_workbook
from pypdf import PdfReader
from edusync.modules.personnel.application.documents import build_staff_profile_pdf,build_staff_register_pdf,build_staff_register_xlsx

ROWS=[{'employee_no':'AG-001','last_name':'KIKUNDA','first_name':'Daniel','middle_name':'Ngwej','category':'ENSEIGNANT','status':'ACTIVE','phone':'0990000000','qualification':'G3','has_linked_access':True,'assignments':[{'function_label':'Enseignant','scope_value':'SECONDAIRE','is_primary':True,'is_titular':True,'titular_class_label':'4e H','start_date':'2026-09-01','end_date':None}]}]

def test_register_xlsx_is_real_workbook_with_title_and_rows():
    data=build_staff_register_xlsx(ROWS,school_name='École Test');wb=load_workbook(BytesIO(data));ws=wb['Personnel'];assert 'École Test' in ws['A1'].value;assert ws['A4'].value=='AG-001';assert ws['B4'].value=='KIKUNDA Ngwej Daniel'

def test_register_xlsx_has_filter_and_frozen_header():
    wb=load_workbook(BytesIO(build_staff_register_xlsx(ROWS,school_name='École Test')));ws=wb['Personnel'];assert ws.freeze_panes=='A4';assert ws.auto_filter.ref.startswith('A3:I')

def test_register_pdf_is_real_pdf_and_contains_staff_text():
    data=build_staff_register_pdf(ROWS,school_name='École Test');assert data.startswith(b'%PDF');text=''.join((p.extract_text() or '') for p in PdfReader(BytesIO(data)).pages);assert 'AG-001' in text and 'KIKUNDA' in text

def test_profile_pdf_keeps_assignment_and_titulariat():
    item={**ROWS[0],'email':'d@example.com','specialty':'Mathématiques','hire_date':'2024-09-01','exit_date':None}
    data=build_staff_profile_pdf(item,school_name='École Test');text=''.join((p.extract_text() or '') for p in PdfReader(BytesIO(data)).pages);assert 'Enseignant' in text and '4e H' in text
