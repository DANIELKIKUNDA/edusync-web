from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def test_compact_topbar_keeps_year_selector():
 s=(ROOT/'frontend/src/App.tsx').read_text(encoding='utf-8')
 assert 'Année scolaire consultée' in s
 # Every school member needs the shell selector (cashier had a 403 on the admin list): minimal selector route.
 assert 'listYearSelector(session.token)' in s
 assert "@router.get('/academic-years/selector')" in (ROOT/'backend/src/edusync/modules/settings/api/router.py').read_text(encoding='utf-8')
 assert "edusync.year.${session.school.id}" in s
 assert "status==='ACTIVE'" in s
def test_year_context_reaches_read_models():
 a=(ROOT/'frontend/src/App.tsx').read_text(encoding='utf-8')
 e=(ROOT/'frontend/src/effectifs.tsx').read_text(encoding='utf-8')
 h=(ROOT/'frontend/src/home.tsx').read_text(encoding='utf-8')
 assert 'yearId={selectedYearId||undefined}' in a
 assert 'getEffectifsOverview(token,scope,yearId)' in e
 assert "getEffectifsCounts(token,'section','ALL',yearId)" in h
 # Recovery chart (2026-10-24): the home passes the selected year to the chart, which reads it per currency.
 c=(ROOT/'frontend/src/platform/recovery_chart.tsx').read_text(encoding='utf-8')
 assert "<RecoveryChart token={token} yearId={yearId}" in h and "recoveryMonthly(token, yearId, currency)" in c
