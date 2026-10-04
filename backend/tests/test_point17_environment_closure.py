from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def test_mobile_viewport_safe_area_and_two_by_two_kpis():
    html=(ROOT/'frontend/index.html').read_text()
    css=(ROOT/'frontend/src/styles.css').read_text()
    assert 'viewport-fit=cover' in html
    assert 'env(safe-area-inset-bottom)' in css
    assert '.kpis,.schoolingKpis,.personMetrics,.effectifsKpis,.homeKpis,.importStats' in css
    assert 'grid-template-columns:repeat(2,minmax(0,1fr))!important' in css

def test_mobile_touch_and_ios_form_zoom_hardening():
    css=(ROOT/'frontend/src/styles.css').read_text()
    assert 'min-height:44px' in css
    assert 'input,select,textarea{font-size:16px!important}' in css
    assert 'prefers-reduced-motion:reduce' in css

def test_no_legacy_static_placeholder_component():
    app=(ROOT/'frontend/src/App.tsx').read_text()
    assert 'function StaticCard' not in app
    assert 'Les écrans métier détaillés seront raffinés' not in app

def test_release_version_point17():
    import json
    package=json.loads((ROOT/'frontend/package.json').read_text())
    assert package['version']=='0.52.0-point17-environment-closure'
