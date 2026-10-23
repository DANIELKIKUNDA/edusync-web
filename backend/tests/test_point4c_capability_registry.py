import json
from pathlib import Path
REG=json.loads((Path(__file__).parents[2]/'contracts'/'CAPABILITY_REGISTRY.json').read_text(encoding='utf-8'))

def test_registry_contains_point4c_capabilities_without_duplicates():
    codes=[x['code'] for x in REG['capabilities']]
    assert len(codes)==len(set(codes))==REG['capability_count']
    assert REG['registry_version']=='2.0.0' and REG['status']=='CANONICAL'  # canonical registry (2026-10-23)
    for code in ('students.directory.print_pdf','students.directory.export_xlsx','students.profile.print_pdf','families.directory.print_pdf','families.directory.export_xlsx','families.resolution.audit','students.profile.complete'):
        assert code in codes
