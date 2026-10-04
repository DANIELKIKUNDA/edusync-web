from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from pypdf import PdfReader
from edusync.modules.effectifs.application.documents import headcounts_pdf,headcounts_xlsx,deposits_xlsx
from edusync.modules.effectifs.domain.models import FGT,HeadcountRow

ROWS=[
 HeadcountRow('Primaire','1re primaire','P1',FGT(12,10,22),FGT(1,0,1),FGT(0,1,1),FGT(11,9,20)),
 HeadcountRow('Primaire','2e primaire','P2',FGT(11,13,24),FGT(0,1,1),FGT(1,0,1),FGT(10,12,22)),
]
SCHOOL={'name':'École Démo EduSync','address':'12 avenue de l’École','city':'Lubumbashi','province':'Haut-Katanga','phone':'+243 000 000 000','email':'demo@ecole.cd'}


def test_effectifs_pdf_is_a4_landscape_and_contains_certified_groups():
    data=headcounts_pdf(school=SCHOOL,rows=ROWS,title='EFFECTIFS PAR CLASSE',scope_label='Primaire',year_label='2026-2027')
    reader=PdfReader(BytesIO(data));assert len(reader.pages)==1
    p=reader.pages[0];assert float(p.mediabox.width)>float(p.mediabox.height)
    text=p.extract_text()
    for token in ['EFFECTIFS PAR CLASSE','Primaire','Inscrits','Abandons','Transférés','Élèves actifs','Total général']:
        assert token in text


def test_effectifs_xlsx_is_14_columns_two_level_header_and_has_total():
    data=headcounts_xlsx(school=SCHOOL,rows=ROWS,title='EFFECTIFS PAR CLASSE',scope_label='Primaire',year_label='2026-2027',sheet_name='Par classe')
    with ZipFile(BytesIO(data)) as z:
        strings=''.join(z.read(n).decode('utf-8','ignore') for n in z.namelist() if n.endswith('.xml'))
        assert 'EFFECTIFS PAR CLASSE' in strings
        assert 'Inscrits' in strings and 'Abandons' in strings and 'Transférés' in strings and 'Élèves actifs' in strings
        assert 'Total général' in strings
        assert 'N5' in strings or 'N6' in strings  # 14th Excel column exists in worksheet XML
        assert 'mergeCell' in strings


def test_deposit_xlsx_keeps_register_columns():
    data=deposits_xlsx(school=SCHOOL,rows=[{'deposited_on':'2026-09-12','matricule':'EL-001','student_name':'KIKUNDA A B','section_label':'Primaire','class_label':'3e primaire','contribution_label':'Rame papier','quantity':'2','unit':'rame','recorded_by_name':'Agent','notes':''}],scope_label='Primaire',year_label='2026-2027')
    with ZipFile(BytesIO(data)) as z:
        strings=''.join(z.read(n).decode('utf-8','ignore') for n in z.namelist() if n.endswith('.xml'))
        for token in ['REGISTRE DES DÉPÔTS MATÉRIELS','Matricule','Contribution','Quantité','Enregistré par']:
            assert token in strings
