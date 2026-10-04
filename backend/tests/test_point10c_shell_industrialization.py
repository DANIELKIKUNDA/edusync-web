from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];APP=(ROOT/'frontend/src/App.tsx').read_text();CSS=(ROOT/'frontend/src/styles.css').read_text()
def test_shell(): assert all(x in APP for x in ['navCollapsed','accountDock','Mes paramètres','Se déconnecter','compactTopbar'])
def test_tooltips(): assert 'title={collapsed?l:undefined}' in APP and 'button[title]:hover:after' in CSS
def test_compact(): assert '.compactTopbar{height:43px' in CSS
