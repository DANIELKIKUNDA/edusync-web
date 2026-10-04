from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PROVISION=(ROOT/'scripts'/'provision_database.py').read_text(encoding='utf-8')
COMPOSE=(ROOT.parent/'docker-compose.yml').read_text(encoding='utf-8')


def test_fresh_database_provisioner_applies_every_current_migration():
    required=[path.name for path in sorted((ROOT/'migrations').glob('*.sql'))]
    assert required, 'No SQL migrations found'
    positions=[PROVISION.index(x) for x in required]
    assert positions == sorted(positions)


def test_runtime_keeps_owner_credentials_outside_backend_container():
    backend=COMPOSE.split('  backend:',1)[1].split('  frontend:',1)[0]
    assert 'EDUSYNC_OWNER_DATABASE_URL' not in backend
    assert 'POSTGRES_OWNER_PASSWORD' not in backend


def test_live_certification_scripts_are_shipped():
    for name in ('g1_live_certification.py','g1_api_probe.py','g3_multi_cashier_probe.py'):
        assert (ROOT/'scripts'/name).exists()
