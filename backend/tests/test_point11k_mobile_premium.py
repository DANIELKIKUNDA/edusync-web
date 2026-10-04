from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
APP=(ROOT/'frontend/src/App.tsx').read_text()
HTML=(ROOT/'frontend/index.html').read_text()
MAN=(ROOT/'frontend/public/manifest.webmanifest').read_text()
def test_mobile_navigation_is_permission_driven():
    assert "const prefixes:Record<string,string[]>" in APP
    for x in ["settings.","personnel.","students.","families.","enrollments.","headcounts.","finance.","documents.","inventory.","sync."]:
        assert x in APP
    assert "const visibleNav=nav.filter(([, ,key])=>canOpenModule(key))" in APP
def test_boot_signature_and_account_are_present():
    assert 'from VolcanoTech' in HTML
    assert 'mobileAccountCard' in APP
    assert 'connectivityLabel(connection)' in APP
def test_pwa_identity_assets_declared():
    assert 'icon-192.svg' in MAN and 'icon-512.svg' in MAN and 'maskable' in MAN
    assert (ROOT/'frontend/public/icons/edusync-mark.svg').exists()
    assert (ROOT/'frontend/public/icons/icon-192.svg').exists()
    assert (ROOT/'frontend/public/icons/icon-512.svg').exists()
def test_no_artificial_boot_delay():
    main=(ROOT/'frontend/src/main.tsx').read_text()
    assert 'setTimeout' not in main
    assert "requestAnimationFrame" in main
