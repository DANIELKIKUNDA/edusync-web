from decimal import Decimal
from pathlib import Path
from edusync.modules.finance_fee_tracking.domain.models import totals
ROOT=Path(__file__).resolve().parents[2]
def test_fee_totals_are_financial_not_average_rates():
    x=totals([{'net_expected':'100','regularized':'100'},{'net_expected':'300','regularized':'0'}])
    assert x['net_expected']==Decimal('400') and x['remaining']==Decimal('300') and x['rate']==Decimal('25.0')
def test_fee_tracking_is_read_projection_not_second_checkout():
    r=(ROOT/'backend/src/edusync/modules/finance_fee_tracking/api/router.py').read_text()
    assert "@router.get('/students')" in r and "@router.post('/" not in r
def test_ui_renames_analysis_to_fee_tracking_and_keeps_named_students():
    f=(ROOT/'frontend/src/finance.tsx').read_text()
    assert 'Suivi des frais' in f and 'Détail nominatif' in f and 'student_name' in f
    assert '>Analyses<' not in f
def test_student_and_family_profiles_surface_same_fee_projection():
    s=(ROOT/'frontend/src/schooling.tsx').read_text()
    assert 'Situation financière ·' in s and 'Situation financière familiale' in s
    assert 'studentFeeSummary' in s and 'familyFeeSummary' in s
def test_taxonomy_is_school_configurable():
    m=(ROOT/'backend/migrations/0023_fee_tracking.sql').read_text()
    assert 'fee_categories' in m and 'category_id' in m and 'FORCE ROW LEVEL SECURITY' in m
def test_fee_filters_follow_real_class_obligations():
    repo=(ROOT/'backend/src/edusync/adapters/postgres_fee_tracking.py').read_text()
    api=(ROOT/'backend/src/edusync/modules/finance_fee_tracking/api/router.py').read_text()
    ui=(ROOT/'frontend/src/finance.tsx').read_text()
    assert 'FROM finance_charge_effective fc' in repo and 'e.class_id=%s' in repo and 'sc.section_id=%s' in repo
    assert 'class_id:UUID|None=None' in api and 'section_id:UUID|None=None' in api
    assert 'Tous les frais applicables' in ui and 'Section' in ui and 'Classe' in ui
