from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
APP=(ROOT/'frontend/src/App.tsx').read_text(encoding='utf-8')
CSS=(ROOT/'frontend/src/styles.css').read_text(encoding='utf-8')
PKG=(ROOT/'frontend/package.json').read_text(encoding='utf-8')

def test_mobile_navigation_is_real_not_hidden_desktop_only():
    assert 'mobileBottomNav' in APP
    assert 'aria-label="Navigation principale"' in APP
    assert 'aria-label="Navigation Atelier Pro"' in APP
    assert 'mobileModuleGrid' in APP
    assert "['home','students','finance']" in APP

def test_mobile_preserves_rbac_and_all_school_modules():
    assert 'visibleNav.map' in APP
    assert "stewardship:['inventory.']" in APP and "const visibleNav=nav.filter(([, ,key])=>canOpenModule(key))" in APP
    assert "sync:['sync.']" in APP

def test_mobile_safe_area_touch_and_table_contracts():
    assert 'env(safe-area-inset-bottom)' in CSS
    assert 'touch-action:manipulation' in CSS
    assert '.dataTable{overflow-x:auto' in CSS
    assert 'font-size:16px!important' in CSS
    assert 'mobileSheetBackdrop' in CSS

def test_mobile_keeps_academic_year_context():
    assert 'yearContext' in APP
    assert 'selectShellYear' in APP
    assert 'schoolMobileProfile' in APP

def test_mobile_release_version():
    assert '0.52.0-point17-environment-closure' in PKG
