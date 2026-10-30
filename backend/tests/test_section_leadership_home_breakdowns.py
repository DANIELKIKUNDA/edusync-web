"""PR #27 certification: the home headcount card receives its groupings from the server projection, never from
browser-side permission checks (owner decision 9, 2026-10-23)."""
from edusync.modules.access.application.projection import declared_capabilities, widgets


def _breakdowns(caps):
    return next(w for w in widgets(set(caps)) if w["id"] == "headcounts.summary")["breakdowns"]


def test_breakdowns_follow_the_capabilities_held():
    assert _breakdowns({"headcounts.read"}) == []
    assert _breakdowns({"headcounts.read", "headcounts.by_section.read"}) == ["section"]
    assert _breakdowns({"headcounts.read", "headcounts.by_class.read", "headcounts.by_option.read"}) == ["class", "option"]


def test_no_headcount_read_no_card_and_internal_rules_never_leak():
    assert all(w["id"] != "headcounts.summary" for w in widgets({"headcounts.by_section.read"}))
    for w in widgets({"headcounts.read", "headcounts.by_section.read"}):
        assert "all" not in w and "any" not in w


def test_breakdown_capabilities_are_declared():
    assert {"headcounts.by_section.read", "headcounts.by_class.read", "headcounts.by_option.read"} <= declared_capabilities()
