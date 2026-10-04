from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MIG=(ROOT/'migrations'/'0010_settings_domain.sql').read_text(encoding='utf-8')
API=(ROOT/'src'/'edusync'/'modules'/'settings'/'api'/'router.py').read_text(encoding='utf-8')
REPO=(ROOT/'src'/'edusync'/'adapters'/'postgres_settings.py').read_text(encoding='utf-8')
APP=(ROOT/'src'/'edusync'/'bootstrap'/'app.py').read_text(encoding='utf-8')


def test_settings_migration_does_not_invent_school_classes_or_tariffs():
    bootstrap=MIG.split('-- Tenant isolation.')[0]
    # Tables may be defined, but defaults must never INSERT business classes/tariffs.
    assert 'INSERT INTO school_classes' not in bootstrap
    assert 'INSERT INTO tariffs' not in bootstrap
    assert 'INSERT INTO school_sections' not in bootstrap


def test_settings_tables_are_force_rls_and_tariffs_have_exact_scope_uniqueness():
    assert 'FORCE ROW LEVEL SECURITY' in MIG
    assert 'uq_tariffs_active_exact_scope' in MIG
    assert 'NULLS NOT DISTINCT' in MIG


def test_reference_catalogs_and_safe_defaults_exist():
    for token in ('rdc_reference_sections','rdc_reference_classes','rdc_reference_fee_types'):
        assert token in MIG
    assert '"implicit_currency_conversion":false' in MIG
    assert '"external_sms_enabled":false' in MIG


def test_settings_api_exposes_explicit_year_lifecycle_and_options():
    for route in ("/academic-years/{year_id}/activate", "/academic-years/{year_id}/close", "/academic-years/{year_id}/archive", "/academic-years/{year_id}/reopen", "/options"):
        assert route in API
    assert "settings.academic_year.close" in API
    assert "settings.academic_year.reopen" in API
    assert "settings.options.manage" in API


def test_tariff_repository_checks_tenant_consistency_before_insert():
    for text in ('Année ou type de frais incompatible avec cette école','Classe incompatible avec cette école ou cette année','Option incompatible avec cette école'):
        assert text in REPO


def test_settings_router_is_mounted():
    assert 'settings_router' in APP
    assert 'prefix="/api/v1/settings"' in APP


def test_database_provisioning_applies_point3b_addendum_and_settings_in_order():
    provision=(ROOT/'scripts'/'provision_database.py').read_text(encoding='utf-8')
    positions=[provision.index(x) for x in (
        '0009_secondary_leadership_roles', '0010_settings_domain', '0011_migrate_legacy_school_admin_rbac'
    )]
    assert positions == sorted(positions)
    assert 'POINT-4A database provisioning: PASS' in provision
