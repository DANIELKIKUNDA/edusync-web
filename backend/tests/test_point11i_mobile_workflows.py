from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
CSS=(ROOT/'frontend/src/styles.css').read_text()
PKG=(ROOT/'frontend/package.json').read_text()
DOC=(ROOT/'POINT11I_MOBILE_WORKFLOWS.md').read_text()

def test_mobile_workflow_release():
    assert f'"version": "{(ROOT/"VERSION").read_text().strip()}"' in PKG
    assert 'POINT 11I' in CSS

def test_cashier_mobile_action_is_reachable():
    assert '.checkoutFooter{position:sticky!important' in CSS
    assert 'env(safe-area-inset-bottom)' in CSS
    assert '.chargeRow{grid-template-columns:34px minmax(0,1fr) auto!important' in CSS

def test_schooling_mobile_is_not_desktop_table_squeeze():
    assert '.studentRow.header{display:none}' in CSS
    assert '.studentRow{grid-template-columns:minmax(0,1fr) auto!important' in CSS
    assert '.familyCards{grid-template-columns:1fr' in CSS

def test_mobile_preserves_business_data_doctrine():
    assert "Aucune colonne ou règle métier n'est supprimée" in DOC
    assert '.stewardship .compactTable>.tr{min-width:620px}' in CSS
