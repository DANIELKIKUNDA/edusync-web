from pathlib import Path
PROJECT=Path(__file__).resolve().parents[2]
PAGE=(PROJECT/'frontend/src/effectifs.tsx').read_text()
APP=(PROJECT/'frontend/src/App.tsx').read_text()
CSS=(PROJECT/'frontend/src/styles.css').read_text()


def test_scope_selector_matches_certified_desktop():
    for label in ["Toute l’école","Maternelle","Primaire","Secondaire"]:assert label in PAGE


def test_certified_effectifs_tabs_and_groups_are_not_redesigned():
    for label in ['Par classe','Par section','Par filière / option','Mouvements','Inscrits','Abandons','Transférés','Élèves actifs','Total général']:
        assert label in PAGE
    assert 'grid-template-columns:130px 190px repeat(12' in CSS


def test_kpis_actions_deposits_and_icons_exist():
    for label in ['Élèves actifs','Classes actives','Moyenne','Imprimer','PDF','Excel','Dépôts matériels','Enregistrer un dépôt']:
        assert label in PAGE
    assert '<svg className="fxIcon"' in PAGE
    assert '@media(prefers-reduced-motion:reduce)' in CSS


def test_navigation_enables_effectifs_module():
    assert "import EffectifsPage from './effectifs'" in APP
    assert "module==='headcounts'?<EffectifsPage" in APP
    assert "['settings','personnel','students','headcounts','home']" in APP
    assert 'POINT 4D' in APP
