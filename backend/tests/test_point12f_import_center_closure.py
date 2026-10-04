from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
r=(ROOT/'backend/src/edusync/modules/migration_import/api/router.py').read_text()
p=(ROOT/'frontend/package.json').read_text()
def test_limits_and_registry():
 assert 'MAX_IMPORT_BYTES=10*1024*1024' in r and 'MAX_IMPORT_ROWS=5000' in r
 assert "@router.get('/contracts')" in r and 'OFFICIAL_TEMPLATE_ONLY' in r
def test_cancel_is_fail_closed_and_audited():
 assert "@router.post('/batches/{kind}/{batch_id}/cancel')" in r
 assert "Un lot exécuté ne peut pas être annulé" in r
 assert 'IMPORT_BATCH_CANCELLED' in r and 'FOR UPDATE' in r
def test_release_version(): assert '0.52.0-point17-environment-closure' in p
