from pathlib import Path
from edusync.modules.documents.application.storage import DocumentLocation,LocalObjectStorageAdapter,safe_segment

def test_hierarchical_logical_key_is_stable():
    x=DocumentLocation('school-1','2026-2027','Scolarité','Élèves','Liste des élèves.xlsx')
    assert x.logical_key=='schools/school-1/2026-2027/Scolarité/Élèves/Liste des élèves.xlsx'
    assert safe_segment('A/B')=='A_B'

def test_same_logical_export_replaces_current_file(tmp_path:Path):
    s=LocalObjectStorageAdapter(tmp_path); key='schools/s1/2026-2027/Effectifs/Tableaux/effectifs.xlsx'
    h1,n1=s.put_current(key,b'v1'); h2,n2=s.put_current(key,b'v2-updated')
    assert h1!=h2 and n1==2 and n2==10
    assert s.read(key)==b'v2-updated'
    # Windows globbing also matches the parent directory "Effectifs".
    assert [p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob('*') if p.is_file()]==[key]
