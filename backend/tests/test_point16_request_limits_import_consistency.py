from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def test_api_guard_closes_chunked_body_bypass_and_scopes_import_ceiling():
    s=(ROOT/'backend/src/edusync/shared/infrastructure/api_guard.py').read_text()
    assert 'IMPORT_MAX_BODY_BYTES = 10 * 1024 * 1024' in s
    assert 'IMPORT_ANALYZE_PATHS = frozenset' in s
    assert 'body.extend' in s and 'len(body) > effective_limit' in s
    assert 'POST", "PUT", "PATCH' in s

def test_import_handlers_stream_with_hard_limit_and_uniform_row_contract():
    s=(ROOT/'backend/src/edusync/modules/migration_import/api/router.py').read_text()
    assert 'async def read_import_body' in s and 'request.stream()' in s
    assert s.count('read_import_body(request)') == 3
    assert "if len(parsed)>10000" not in s
    assert "Maximum 10 000 lignes financières" not in s
    assert s.count('MAX_IMPORT_ROWS') >= 4

def test_import_limits_are_not_weaker_than_runtime_production_guard():
    settings=(ROOT/'backend/src/edusync/bootstrap/settings.py').read_text()
    router=(ROOT/'backend/src/edusync/modules/migration_import/api/router.py').read_text()
    assert '10 * 1024 * 1024' in settings
    assert 'MAX_IMPORT_BYTES=10*1024*1024' in router
