from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
APP=(ROOT/'frontend/src/App.tsx').read_text(encoding='utf-8')
PROJ=(ROOT/'backend/src/edusync/modules/access/application/projection.py').read_text(encoding='utf-8')  # server navigation (2026-10-23)
CSS=(ROOT/'frontend/src/styles.css').read_text(encoding='utf-8')
PKG=(ROOT/'frontend/package.json').read_text(encoding='utf-8')

def test_mobile_navigation_is_real_not_hidden_desktop_only():
    # Closure 2026-10: shell replaced by platform/shell.tsx (AppShell); same intent, new implementation.
    shell=(ROOT/'frontend/src/platform/shell.tsx').read_text(encoding='utf-8')
    assert 'es-bottom' in shell and 'aria-label="Navigation principale"' in shell and 'aria-label="Navigation rapide"' in shell
    assert 'es-drawer' in shell and 'aria-label="Menu EduSync"' in shell
    assert "['home','students','finance','documents']" in APP

def test_mobile_preserves_rbac_and_all_school_modules():
    # 2026-10-23: the phone menu uses the same server navigation as the desktop (/access/me)
    assert 'const shellNav:ShellNavItem[]=nav.map(' in APP and "const nav=me?.navigation??[{key:'home',label:'Accueil',icon:'home'}]" in APP
    for key in ('"stewardship"', '"sync"', '"students"', '"finance"', '"access"'):
        assert key in PROJ

def test_mobile_safe_area_touch_and_table_contracts():
    assert 'env(safe-area-inset-bottom)' in CSS
    assert 'touch-action:manipulation' in CSS
    assert '.dataTable{overflow-x:auto' in CSS
    assert 'font-size:16px!important' in CSS
    assert 'mobileSheetBackdrop' in CSS

def test_mobile_keeps_academic_year_context():
    # Closure 2026-10: shell replaced by platform/shell.tsx (AppShell); same intent, new implementation.
    assert 'es-year' in APP and "yearSelect('drawer')" in APP
    assert 'selectShellYear' in APP
    assert 'drawerTools' in APP

def test_mobile_release_version():
    assert '0.52.0-point17-environment-closure' in PKG
