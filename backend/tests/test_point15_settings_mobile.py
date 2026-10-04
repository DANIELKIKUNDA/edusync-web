from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
APP=(ROOT/'frontend/src/App.tsx').read_text()
API=(ROOT/'frontend/src/api.ts').read_text()
CSS=(ROOT/'frontend/src/styles.css').read_text()

def test_settings_placeholders_removed_from_navigation():
    for key in ["'payment'","'enrollment'","'benefits'","'documents'","'advanced'"]:
        assert key not in APP.split('] as const;',1)[0].split('const parameterTabs=[',1)[1]

def test_real_settings_editors_are_wired():
    for token in ['IdentitySettings','ContributionsSettings','ProductsSettings','createTariff','updateSchoolIdentity','listSettingsProducts','listSettingsContributions']:
        assert token in APP or token in API

def test_mobile_platform_tables_become_cards_and_readiness_is_compact():
    assert '.platformShell .row.platformSchoolActionRow' in CSS
    assert 'grid-template-columns:repeat(2,minmax(0,1fr))!important' in CSS
    assert '.readinessGrid{grid-template-columns:repeat(2' in CSS

def test_release():
    assert '0.52.0-point17-environment-closure' in (ROOT/'frontend/package.json').read_text()

def test_settings_loading_is_permission_aware():
    assert "safe(can('settings.products.read')" in APP
    assert "safe(can('settings.contributions.read')" in APP
    assert "parameterTabs.filter" in APP
