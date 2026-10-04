from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
APP=(ROOT/'frontend/src/App.tsx').read_text()
BACK=(ROOT/'frontend/src/platform/mobile_back.ts').read_text()
PKG=(ROOT/'frontend/package.json').read_text()

def test_release(): assert '0.52.0-point17-environment-closure' in PKG

def test_android_back_has_real_history_contract():
    assert "window.addEventListener('popstate'" in BACK
    assert "history.pushState" in BACK and "history.replaceState" in BACK
    assert 'edusync:android-back' in BACK

def test_back_closes_transient_layers_first():
    for marker in ['mobileSheetBackdrop','wizardBackdrop','drawerBackdrop','eduDialogBackdrop']:
        assert marker in BACK
    assert 'closeTopOverlay()' in BACK

def test_school_and_platform_restore_screen_from_history():
    assert "replaceMobileRoot('school','home')" in APP
    assert "replaceMobileRoot('platform','dashboard')" in APP
    assert "pushMobileScreen('school',next)" in APP
    assert "pushMobileScreen('platform',next)" in APP

def test_unsaved_browser_exit_guard():
    assert "beforeunload" in BACK
    assert "WeakSet<HTMLFormElement>" in BACK
