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
    # Closure 2026-10: shell replaced by platform/shell.tsx (AppShell); same intent, new implementation.
    shell=(ROOT/'frontend/src/platform/shell.tsx').read_text(encoding='utf-8')
    assert 'es-drawer-account' in shell and 'StatusChip' in shell and 'connectivityLabel(state)' in shell
def test_pwa_identity_assets_declared():
    # Closure 2026-10: installable PNG icons (Android/desktop) + separate maskable variants; SVG kept as scalable icon.
    assert 'icon-192.png' in MAN and 'icon-512.png' in MAN and '"purpose": "maskable"' in MAN
    for name in ('edusync-mark.svg','icon-192.png','icon-512.png','icon-maskable-192.png','icon-maskable-512.png','apple-touch-icon.png','favicon.ico'):
        assert (ROOT/'frontend/public/icons'/name).exists(), name
def test_no_artificial_boot_delay():
    main=(ROOT/'frontend/src/main.tsx').read_text()
    assert 'setTimeout' not in main
    assert "requestAnimationFrame" in main
