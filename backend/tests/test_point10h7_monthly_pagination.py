from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def text(rel): return (ROOT/rel).read_text(encoding='utf-8')
def test_monthly_scope_filter_is_sql_side_and_exported():
    repo=text('backend/src/edusync/adapters/postgres_finance_recovery.py')
    router=text('backend/src/edusync/modules/finance_recovery/api/router.py')
    api=text('frontend/src/api.ts')
    ui=text('frontend/src/recovery.tsx')
    assert 'period_order=None' in repo
    assert 'COALESCE(fc.period_order,EXTRACT(MONTH FROM fc.due_date)::int,0)=%s' in repo
    assert 'period_order:int|None=Query(None,ge=1,le=12)' in router
    assert 'period_order:periodOrder' in api
    assert 'Mois de synthèse' in ui and 'Toute l’année' in ui
    assert 'recoverySummaryExport' in ui and 'monthOrder?Number(monthOrder):undefined' in ui
def test_schooling_directories_are_server_paginated():
    router=text('backend/src/edusync/modules/schooling/api/router.py')
    ui=text('frontend/src/schooling.tsx')
    assert "'has_more':has_more" in router
    assert 'PAGE_SIZE=50' in ui
    assert 'directoryPager' in ui
    assert 'Précédent' in ui and 'Suivant' in ui
