from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];APP=(ROOT/'frontend/src/App.tsx').read_text();CSS=(ROOT/'frontend/src/styles.css').read_text()
# Closure 2026-10: AppShell (platform/shell.tsx) — collapsible sidebar remembered, account menu, compact top bar.
def test_shell():
    shell=(ROOT/'frontend/src/platform/shell.tsx').read_text(encoding='utf-8')
    assert '<AppShell' in APP and 'Se déconnecter' in APP and 'Mon profil' in APP
    assert 'es-collapsed' in shell and 'edusync.shell.collapsed' in shell and 'es-top' in shell and 'AccountMenu' in shell
def test_tooltips():
    shell=(ROOT/'frontend/src/platform/shell.tsx').read_text(encoding='utf-8')
    assert 'role="tooltip"' in shell and 'onMouseEnter={showTip(n.label)}' in shell and 'onFocus={showTip(n.label)}' in shell and 'aria-label={n.label}' in shell
def test_compact(): assert '.compactTopbar{height:43px' in CSS
