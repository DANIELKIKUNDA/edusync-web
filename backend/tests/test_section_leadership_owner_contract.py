"""Canonical RBAC regression for section leadership; no extra grants are inferred."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROLES = {r["code"]: r for r in json.loads(
    (ROOT / "contracts" / "POINT3B_ROLE_DECISIONS_FINAL.json").read_text(encoding="utf-8")
)["roles"]}

PREFET = "PREFET_ETUDES"
DIRECTION = "DIRECTION_SECTION"


def test_section_leadership_has_two_distinct_owner_approved_roles():
    for code in (PREFET, DIRECTION):
        role = ROLES[code]
        assert role["owner_decision"] == "APPROVED"
        assert role["status"] == "LOCKED_OWNER_APPROVED"
        assert role["capability_count"] == 84
        assert len(role["final_capabilities"]) == 84
        assert len(set(role["final_capabilities"])) == 84


def test_section_leadership_shared_capabilities_do_not_imply_shared_scope():
    assert set(ROLES[PREFET]["final_capabilities"]) == set(ROLES[DIRECTION]["final_capabilities"])
    assert "Secondaire" in ROLES[PREFET]["decision_note"]
    assert "Primaire" in ROLES[DIRECTION]["decision_note"]
    assert "Maternelle" in ROLES[DIRECTION]["decision_note"]


def test_section_leadership_can_manage_student_lifecycle_but_not_enroll():
    required = {
        "students.read", "students.identity.update", "students.class.change",
        "students.lifecycle.abandon", "students.lifecycle.suspend",
        "students.lifecycle.reintegrate", "students.lifecycle.transfer",
        "students.lifecycle.history.read",
    }
    forbidden = {
        "enrollments.create", "enrollments.reenroll",
        "finance.checkout.collect", "finance.cash.open",
        "finance.cash.close", "settings.school_identity.update",
        "access.users.create",
    }
    for code in (PREFET, DIRECTION):
        caps = set(ROLES[code]["final_capabilities"])
        assert required <= caps
        assert forbidden.isdisjoint(caps)


def test_section_leadership_parent_communications_not_schoolwide_broadcast():
    for code in (PREFET, DIRECTION):
        caps = set(ROLES[code]["final_capabilities"])
        assert {
            "communications.send.individual", "communications.send.class",
            "communications.send.section", "communications.sms.send",
        } <= caps
        assert "communications.send.all_parents" not in caps
