"""Executable section-isolation checks for parent communication audience resolution.

Uses a deterministic fake SQL result, so no external PostgreSQL service is needed.
These tests exercise the real resolve_audience implementation, not source-text matching.
"""
from uuid import uuid4

import pytest

from edusync.modules.communications.application.messaging import resolve_audience
from edusync.shared.application.context import ActorContext


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.executions = []

    def execute(self, statement, params):
        self.executions.append((str(statement), params))
        return FakeResult(self.rows)


def actor_for(section):
    cap = "communications.send.section"
    return ActorContext(
        user_id=uuid4(), school_id=uuid4(), membership_id=uuid4(),
        permissions=frozenset({cap}),
        capability_scopes=((cap, "SECTION", section),),
    )


def guardian(section):
    return {
        "id": uuid4(), "full_name": "Parent de test",
        "phone": "+243990000000", "email": None, "section_code": section,
    }


@pytest.mark.parametrize("granted,allowed,denied", [
    ("SECONDAIRE", "SECONDAIRE", "PRIMAIRE"),
    ("PRIMAIRE", "PRIMAIRE", "SECONDAIRE"),
    ("MATERNELLE", "MATERNELLE", "SECONDAIRE"),
])
def test_section_leader_can_contact_only_own_section(granted, allowed, denied):
    actor = actor_for(granted)
    cap = "communications.send.section"
    own = FakeConnection([guardian(allowed)])
    recipients = resolve_audience(own, actor, actor.school_id, "SECTION", uuid4(), cap)
    assert len(recipients) == 1
    assert own.executions[0][1]["sid"] == str(actor.school_id)

    foreign = FakeConnection([guardian(denied)])
    with pytest.raises(PermissionError, match="hors de votre périmètre"):
        resolve_audience(foreign, actor, actor.school_id, "SECTION", uuid4(), cap)


def test_mixed_audience_fails_closed_without_partial_recipient_list():
    actor = actor_for("SECONDAIRE")
    conn = FakeConnection([guardian("SECONDAIRE"), guardian("PRIMAIRE")])
    with pytest.raises(PermissionError, match="hors de votre périmètre"):
        resolve_audience(
            conn, actor, actor.school_id, "SECTION", uuid4(),
            "communications.send.section",
        )


def test_missing_section_reference_is_rejected_before_query():
    actor = actor_for("SECONDAIRE")
    conn = FakeConnection([])
    with pytest.raises(ValueError, match="Choisissez la section"):
        resolve_audience(
            conn, actor, actor.school_id, "SECTION", None,
            "communications.send.section",
        )
    assert conn.executions == []
