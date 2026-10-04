from io import BytesIO
from openpyxl import load_workbook
from edusync.modules.schooling.application.documents import student_directory_pdf,student_directory_xlsx,family_directory_pdf,family_directory_xlsx,student_profile_pdf

STUDENTS=[dict(matricule='ELV-00001',last_name='KIKUNDA',middle_name='NGWEJ',first_name='Daniel',class_label='3e HP',section_label='Secondaire',academic_year_label='2026-2027',gender='M',birth_date='2010-04-12',birth_place='Lubumbashi',family_name='Foyer de Floris',primary_responsible='Floris K.',family_phone='+243990000000',status='ACTIVE')]
FAMILIES=[dict(code='FAM-00001',display_name='Foyer de Floris',phone='+243990000000',child_count=2,contact_status='COMPLETE',guardians=[dict(full_name='Floris K.',phone='+243990000000',is_primary=True)])]

def test_schooling_pdfs_are_real_pdf_bytes():
    assert student_directory_pdf(school_name='École Test',rows=STUDENTS).startswith(b'%PDF')
    assert family_directory_pdf(school_name='École Test',rows=FAMILIES).startswith(b'%PDF')
    profile={**STUDENTS[0], 'birth_date':None,'birth_place':None,'nationality':None,'profile_completeness':40}
    assert student_profile_pdf(school_name='École Test',student=profile).startswith(b'%PDF')

def test_student_and_family_workbooks_have_filters_and_frozen_headers():
    for payload,title in ((student_directory_xlsx(school_name='École Test',rows=STUDENTS),'LISTE DES ÉLÈVES'),(family_directory_xlsx(school_name='École Test',rows=FAMILIES),'RÉPERTOIRE DES FAMILLES')):
        wb=load_workbook(BytesIO(payload));ws=wb.active
        assert ws['A3'].value == title
        assert ws.freeze_panes == 'A6'
        assert ws.auto_filter.ref

def test_student_export_preserves_certified_desktop_columns_exactly():
    wb=load_workbook(BytesIO(student_directory_xlsx(school_name='École Test',rows=STUDENTS)));ws=wb.active
    assert [ws.cell(5,c).value for c in range(1,13)] == ['N°','Matricule','Élève','Sexe','Année','Section','Classe','Date naissance','Lieu naissance','Responsable / foyer','Téléphone','Statut']
    assert ws['D6'].value == 'M' and ws['E6'].value == '2026-2027' and ws['H6'].value == '2010-04-12' and ws['I6'].value == 'Lubumbashi'
