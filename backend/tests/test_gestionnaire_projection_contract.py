"""Regression coverage for the owner-approved Gestionnaire supervision projection."""
from __future__ import annotations

import json
from pathlib import Path

from edusync.modules.access.application.projection import actions, navigation, widgets

ROOT = Path(__file__).resolve().parents[2]
ROLES = json.loads((ROOT / "contracts" / "POINT3B_ROLE_DECISIONS_FINAL.json").read_text(encoding="utf-8"))["roles"]


def test_gestionnaire_projection_uses_owner_approved_capabilities():
    role = next(r for r in ROLES if r["code"] == "GESTIONNAIRE")
    caps = set(role["final_capabilities"])
    assert len(caps) == role["capability_count"]
    visible_widgets = {item["id"] for item in widgets(caps)}
    visible_actions = {item["id"] for item in actions(caps)}
    visible_modules = {item["key"] for item in navigation(caps)}
    assert {"cash.supervision", "personnel.summary", "headcounts.summary", "finance.recovery"} <= visible_widgets
    assert {"cash.supervise", "reports.open"} <= visible_actions
    assert {"finance", "personnel", "headcounts"} <= visible_modules
    assert "cash.today" not in visible_widgets
    assert "checkout.quick" not in visible_widgets
    assert "checkout.new" not in visible_actions
    assert "members.create" not in visible_actions
    assert "settings.open" not in visible_actions


def test_gestionnaire_projection_respects_removed_permissions():
    role = next(r for r in ROLES if r["code"] == "GESTIONNAIRE")
    caps = set(role["final_capabilities"])
    without_cash = caps - {"finance.cash.other.read"}
    assert "cash.supervision" not in {w["id"] for w in widgets(without_cash)}
    assert "cash.supervise" not in {a["id"] for a in actions(without_cash)}
    without_personnel = caps - {"personnel.summary.read"}
    assert "personnel.summary" not in {w["id"] for w in widgets(without_personnel)}
