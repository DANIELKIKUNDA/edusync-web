from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
APP=(ROOT/'frontend/src/App.tsx').read_text()
API=(ROOT/'frontend/src/api.ts').read_text()
CSS=(ROOT/'frontend/src/styles.css').read_text()

def test_settings_placeholders_removed_from_navigation():
    tabs=APP.split('] as const;',1)[0].split('const parameterTabs=[',1)[1]
    for key in ["'documents'","'advanced'"]:
        assert key not in tabs
    # Parity lot L5 2026-10 (justified adaptation): 'payment' edits the Desktop cash-desk rules enforced by the checkout.
    assert "'payment'" in tabs and "<PaymentPolicySettings token={token}" in APP
    # Parity lot L3 2026-10 (justified adaptation): 'benefits' is a real editor of the Desktop benefit policies
    # (/settings/benefit-policies), consumed at enrollment and in the due charges.
    assert "'benefits'" in tabs and "<BenefitsSettings token={token}" in APP
    # N2 2026-10 (justified adaptation): 'enrollment' is back as a real editor of the policy the schooling module
    # enforces (/settings/policies/ENROLLMENT), not a placeholder.
    assert "'enrollment'" in tabs and "putPolicy(token,'ENROLLMENT'" in APP

def test_real_settings_editors_are_wired():
    for token in ['IdentitySettings','ContributionsSettings','ProductsSettings','createTariff','updateSchoolIdentity','listSettingsProducts','listSettingsContributions']:
        assert token in APP or token in API

def test_mobile_platform_tables_become_cards_and_readiness_is_compact():
    assert '.platformShell .row.platformSchoolActionRow' in CSS
    assert 'grid-template-columns:repeat(2,minmax(0,1fr))!important' in CSS
    assert '.readinessGrid{grid-template-columns:repeat(2' in CSS

def test_release():
    assert f'"version": "{(ROOT/"VERSION").read_text().strip()}"' in (ROOT/'frontend/package.json').read_text()

def test_settings_loading_is_permission_aware():
    assert "load('products',can('settings.products.read')" in APP  # partial reload, still permission-aware (2026-10-24)
    assert "can('settings.contributions.read')" in APP
    assert "const allowed=(key:TabKey)=>" in APP and "g.keys.filter(allowed)" in APP  # grouped, permission-aware (2026-10-24)
