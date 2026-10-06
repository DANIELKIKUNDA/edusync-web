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
    for label in ('Tableau de bord','Écoles','Accès','Journal d’audit','État du service'):
        assert label in s
    assert "platformAudit(token,audit.next_cursor)" in s

def test_atelier_pro_tables_are_query_driven_and_bounded():
    s=(ROOT/'backend/src/edusync/modules/platform/api/router.py').read_text()
    assert "limit=max(1,min(limit,100))" in s
    assert "s.name ILIKE '%'||:q||'%'" in s
    assert "u.full_name ILIKE '%'||:q||'%'" in s
