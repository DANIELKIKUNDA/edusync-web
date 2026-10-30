"""Certification 2026-10-30: the delivery details of a message show recipients' names and phone numbers. A section-scoped
reader (Directeur des études / de discipline) only reaches the messages it sent or whose audience lies in its sections;
the real-PostgreSQL proof is tools/ci/three_roles_postgres_integration.py (7 checks fail on the previous code)."""
from __future__ import annotations

from uuid import uuid4

from edusync.modules.communications.api.router import _history_scope
from edusync.shared.application.context import ActorContext


def _actor(scopes):
    return ActorContext(user_id=uuid4(), school_id=uuid4(), membership_id=uuid4(), permissions=frozenset({"communications.history.read"}),
                        capability_scopes=tuple(("communications.history.read", t, v) for t, v in scopes))


def test_school_wide_reader_is_not_filtered():
    assert _history_scope(_actor([("SCHOOL", None)])) == ("TRUE", {})


def test_section_reader_sees_own_messages_and_its_sections_only():
    actor = _actor([("SECTION", "secondaire")])
    sql, params = _history_scope(actor)
    assert params == {"hs_uid": str(actor.user_id), "hs_secs": ["SECONDAIRE"]}
    assert "m.created_by=:hs_uid" in sql
    for audience in ("'SECTION'", "'CLASS'", "'INDIVIDUAL'"):
        assert f"m.audience_type={audience}" in sql
    assert "'SCHOOL'" not in sql                      # a whole-school message is never shown to a section reader
    assert sql.count("school_id=m.school_id") >= 3    # every join stays inside the message's school
