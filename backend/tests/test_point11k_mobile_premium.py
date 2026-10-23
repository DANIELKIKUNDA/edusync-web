from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
APP=(ROOT/'frontend/src/App.tsx').read_text()
PROJ=(ROOT/'backend/src/edusync/modules/access/application/projection.py').read_text(encoding='utf-8')  # server navigation (2026-10-23)
HTML=(ROOT/'frontend/index.html').read_text()
MAN=(ROOT/'frontend/public/manifest.webmanifest').read_text()
def test_mobile_navigation_is_permission_driven():
    # 2026-10-23: no client prefixes any more — explicit capabilities per entry, computed by the server
    assert "const prefixes" not in APP and "canOpenModule=(key:string)=>nav.some(x=>x.key===key)" in APP
    for x in ["settings.","personnel.","students.","families.","headcounts.","finance.","documents.","inventory.","sync."]:
        assert x in PROJ
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
    # N0 certification 2026-10 (justified adaptation): the boot screen no longer disappears on the first frame to be
    # replaced by a second, different loader; it stays until the real session check ends (App dismisses it when
    # `restoring` becomes false). The intent is unchanged: no timer, no artificial delay.
    main=(ROOT/'frontend/src/main.tsx').read_text(encoding='utf-8')
    assert 'setTimeout' not in main
    app=(ROOT/'frontend/src/App.tsx').read_text(encoding='utf-8')
    assert 'if(!restoring)dismissBoot()' in app and 'setTimeout' not in (ROOT/'frontend/src/platform/boot.ts').read_text(encoding='utf-8').split('el.classList.add')[0]
