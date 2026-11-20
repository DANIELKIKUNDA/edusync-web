"""Certification mobile PR #109 (2026-11-20): every overflow found on the real local stack at 320–844 px stays fixed."""
from pathlib import Path

UI = Path(__file__).resolve().parents[2] / 'frontend' / 'src'


def css(name: str) -> str:
    return (UI / name).read_text(encoding='utf-8')


def test_documents_tabs_wrap_on_phones():
    s = css('documents.css')
    assert '.docPanel,.docPanel>*{min-width:0}' in s and '.docScopeTabs button{flex:1 1 0;min-width:0;white-space:normal' in s


def test_page_grids_never_exceed_the_screen():
    s = css('styles.css')
    assert '.pageEnter>*,.syncAdmin>*,.personnelPage>*,.accessMetrics>*{min-width:0}' in s
    assert '.personnelPage,.syncAdmin{grid-template-columns:minmax(0,1fr)}' in s and '.heroActions{flex-wrap:wrap}' in s


def test_communication_and_sync_cards_fit_320px():
    c = css('communications.css'); s = css('sync_admin.css')
    assert '.commRoles{grid-template-columns:repeat(auto-fill,minmax(min(100%,320px),1fr))}' in c
    assert '.commToggleText{grid-template-columns:minmax(0,1fr)}' in c
    assert '.deviceGrid{grid-template-columns:repeat(auto-fill,minmax(min(100%,320px),1fr))}' in s


def test_bottom_bar_and_touch_targets():
    m = css('platform/mobile.css')
    assert '.es-shell .es-bottom button>span.es-bnav-ind{width:min(60px,100%)}' in m
    assert '@media (pointer:coarse)' in m and 'min-height:44px' in m


def test_recovery_chart_follows_a_narrow_card():
    t = (UI / 'platform' / 'recovery_chart.tsx').read_text(encoding='utf-8')
    assert 'Math.max(280' not in t and t.count('Math.max(200') == 2
