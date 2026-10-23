from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def test_atelier_pro_backend_has_real_read_models():
    s=(ROOT/'backend/src/edusync/modules/platform/api/router.py').read_text()
    for route in ("'/dashboard'","'/schools-page'","'/access'","'/audit'","'/diagnostics'"):
        assert route in s
    assert "ORDER BY a.occurred_at DESC,a.id DESC" in s
    assert "LIMIT :lim OFFSET :off" in s

def test_atelier_pro_frontend_no_longer_placeholder_nav():
    s=(ROOT/'frontend/src/App.tsx').read_text()
    assert 'Administration technique légère de la plateforme' not in s
    # Closure 2026-10: shell replaced by platform/shell.tsx (AppShell); same intent, new implementation.
    for label in ('Tableau de bord','Écoles','accès','Journal d’audit','État du service'):
        assert label in s
    # N1 certification 2026-10 (justified adaptation): the audit journal moved to platform/audit.tsx on the
    # filtered /platform/audit-log endpoint; it is still keyset-paginated by cursor (same intent).
    audit=(ROOT/'frontend/src/platform/audit.tsx').read_text(encoding='utf-8')
    # Journal d'audit lot 2026-10: cursor stack (pages) and « Charger la suite »
    assert 'r.next_cursor' in audit and '<AuditPanel token={token}' in s

def test_atelier_pro_tables_are_query_driven_and_bounded():
    s=(ROOT/'backend/src/edusync/modules/platform/api/router.py').read_text()
    assert "limit=max(1,min(limit,100))" in s
    # Schools module lot 2026-10 (justified adaptation): the schools screen moved to platform/schools.tsx + school_sheet.tsx
    # and its SQL to application/schools_directory.py; same intent, new implementation.
    d=(ROOT/'backend/src/edusync/modules/platform/application/schools_directory.py').read_text(encoding='utf-8')
    assert 'edusync_search_key(' in d and 'LIMIT :lim' in d
    assert "u.full_name ILIKE '%'||:q||'%'" in s
