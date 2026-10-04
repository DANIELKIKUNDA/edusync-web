from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def test_compact_topbar_keeps_year_selector():
 s=(ROOT/'frontend/src/App.tsx').read_text(encoding='utf-8')
 assert 'Année scolaire consultée' in s
 assert 'listAcademicYears(session.token)' in s
 assert "edusync.year.${session.school.id}" in s
 assert "status==='ACTIVE'" in s
def test_year_context_reaches_read_models():
 a=(ROOT/'frontend/src/App.tsx').read_text(encoding='utf-8')
 e=(ROOT/'frontend/src/effectifs.tsx').read_text(encoding='utf-8')
 h=(ROOT/'frontend/src/home.tsx').read_text(encoding='utf-8')
 assert 'yearId={selectedYearId||undefined}' in a
 assert 'getEffectifsOverview(token,scope,yearId)' in e
 assert "getEffectifsCounts(token,'section','ALL',yearId)" in h
 assert "recoveryMonthly(token,yearId,'CDF')" in h
