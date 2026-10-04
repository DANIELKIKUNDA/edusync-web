from pathlib import Path
ROOT=Path(__file__).parents[2]
UI=(ROOT/'frontend'/'src'/'schooling.tsx').read_text(encoding='utf-8')
CSS=(ROOT/'frontend'/'src'/'styles.css').read_text(encoding='utf-8')
API=(ROOT/'frontend'/'src'/'api.ts').read_text(encoding='utf-8')
ROUTER=(ROOT/'backend'/'src'/'edusync'/'modules'/'schooling'/'api'/'router.py').read_text(encoding='utf-8')

def test_wizard_marks_five_terrain_fields_required_by_default():
    for label in ('Nom *','Postnom *','Prénom *','Sexe *','Classe *'):
        assert label in UI
    assert 'Date de naissance<input' in UI
    assert 'Lieu de naissance<input' in UI
    assert 'Date de naissance *' not in UI
    assert 'Lieu de naissance *' not in UI
    assert 'Seuls 5 éléments bloquent l’inscription.' in UI

def test_household_ui_does_not_require_manual_family_name_and_explains_resolution():
    assert 'Pas de “nom de famille” obligatoire.' in UI
    assert 'EduSync propose le foyer sans jamais fusionner silencieusement.' in UI
    assert 'Le libellé du foyer sera généré automatiquement' in UI

def test_modern_ui_has_centered_kpis_and_motion_accessibility():
    assert 'schoolingKpi' in UI and 'kpiIcon' in UI
    assert 'toLocaleString' in UI
    assert 'prefers-reduced-motion:reduce' in CSS
    assert 'place-items:center' in CSS or 'align-items:center' in CSS

def test_student_and_family_pdf_xlsx_exports_are_exposed():
    for marker in ('studentDirectoryPdf','studentDirectoryXlsx','familyDirectoryPdf','familyDirectoryXlsx','studentProfilePdf'):
        assert marker in API
    assert "@router.get('/exports/families.xlsx')" in ROUTER

def test_static_household_resolution_route_precedes_dynamic_family_route():
    assert ROUTER.index("@router.get('/families/resolve/candidates')") < ROUTER.index("@router.get('/families/{family_id}')")
