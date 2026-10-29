"""Backend role-baseline invariants for secondary leadership.

These tests intentionally do not grant new privileges to the two roles.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (ROOT / "migrations/0009_secondary_leadership_roles.sql").read_text(encoding="utf-8")
SCHOOLING = (ROOT / "src/edusync/modules/schooling/api/router.py").read_text(encoding="utf-8")
EFFECTIFS = (ROOT / "src/edusync/modules/effectifs/api/router.py").read_text(encoding="utf-8")


def _grants(role):
    return set(re.findall(r"\('"+role+r"',\s*'([^']+)'\)", MIGRATION))


def test_secondary_leadership_does_not_inherit_finance_mutations():
    for role in ("DIRECTEUR_ETUDES", "DIRECTEUR_DISCIPLINE"):
        grants = _grants(role)
        assert grants
        assert not any(x.startswith("finance.") for x in grants)
        assert not any(x.startswith("personnel.") and not x.endswith(".read") for x in grants)


def test_directors_have_different_communications_baselines():
    studies = _grants("DIRECTEUR_ETUDES")
    discipline = _grants("DIRECTEUR_DISCIPLINE")
    assert "communications.sms.bulk_send" not in studies
    assert "communications.sms.bulk_send" in discipline
    assert "students.identity.update" not in studies
    assert "students.identity.update" in discipline


def test_secondary_scope_is_enforced_by_database_trigger():
    assert "validate_secondary_standard_role_scope" in MIGRATION
    assert "NEW.scope_type <> 'SECTION'" in MIGRATION
    assert "SECONDAIRE" in MIGRATION
    assert "BEFORE INSERT OR UPDATE ON rbac_assignment_scopes" in MIGRATION


def test_student_read_routes_use_capability_scopes():
    assert "_need(actor,'students.read');scopes=_scopes(actor,'students.read')" in SCHOOLING
    assert "list_students(actor.school_id,scopes=scopes" in SCHOOLING
    assert "get_student(actor.school_id,student_id,scopes=scopes)" in SCHOOLING


def test_headcounts_queries_use_capability_scopes():
    assert '_need(actor,"headcounts.read");scopes=_scopes(actor,"headcounts.read")' in EFFECTIFS
    assert "repo.overview(actor.school_id,y[\"id\"],scopes=scopes" in EFFECTIFS
    assert "repo.counts(actor.school_id,y[\"id\"],scopes=scopes" in EFFECTIFS


COMMUNICATIONS = (ROOT / "src/edusync/modules/communications/api/router.py").read_text(encoding="utf-8")


def test_secondary_communication_authorization_is_audience_specific():
    assert "cap = AUDIENCE_CAPS[b.audience_type.upper()]" in COMMUNICATIONS
    assert "need(actor, cap)" in COMMUNICATIONS
    assert "'communications.sms.send' if b.audience_type.upper() == 'INDIVIDUAL' else 'communications.sms.bulk_send'" in COMMUNICATIONS


def test_secondary_communication_preview_and_send_resolve_scoped_audience():
    assert COMMUNICATIONS.count("resolve_audience(c, actor, actor.school_id, b.audience_type, b.audience_ref, cap)") >= 2
    assert "if b.confirm_fingerprint != figures['fingerprint']" in COMMUNICATIONS
    assert "if not figures['sufficient']" in COMMUNICATIONS
    assert "idempotency_key=b.idempotency_key" in COMMUNICATIONS


def test_discipline_identity_update_cannot_smuggle_profile_changes():
    patch = SCHOOLING.split("@router.patch('/students/{student_id}')", 1)[1].split("\n@router.", 1)[0]
    assert "capability='students.identity.update'" in patch
    assert "Séparez la correction d’identité des modifications du profil élève" in patch
    assert "('gender','birth_date','birth_place','nationality','address','previous_school','photo_url','notes')" in patch
    assert "repo.get_student(actor.school_id,student_id,scopes=scopes)" in patch


def test_parent_audience_filters_section_before_deduplication():
    from uuid import uuid4
    from edusync.modules.communications.application.messaging import resolve_audience

    parent = uuid4()
    class Result:
        def mappings(self):
            return self
        def all(self):
            return [
                {"id": parent, "full_name": "Parent", "phone": "+243900000001", "email": None, "section_code": "PRIMAIRE"},
                {"id": parent, "full_name": "Parent", "phone": "+243900000001", "email": None, "section_code": "SECONDAIRE"},
            ]

    class Connection:
        def execute(self, query, params):
            return Result()

    class Actor:
        is_platform_admin = False
        def scopes_for(self, cap):
            return (("SECTION", "SECONDAIRE"),)
        def scope_allows(self, cap, scope_type, value):
            return scope_type == "SECTION" and value == "SECONDAIRE"

    recipients = resolve_audience(Connection(), Actor(), uuid4(), "SCHOOL", None, "communications.send.all_parents")
    assert len(recipients) == 1
    assert recipients[0].ref == parent


def test_parent_audience_does_not_expose_other_section():
    from uuid import uuid4
    from edusync.modules.communications.application.messaging import resolve_audience

    class Result:
        def mappings(self):
            return self
        def all(self):
            return [{"id": uuid4(), "full_name": "Primary parent", "phone": None, "email": None, "section_code": "PRIMAIRE"}]

    class Connection:
        def execute(self, query, params):
            return Result()

    class Actor:
        is_platform_admin = False
        def scopes_for(self, cap):
            return (("SECTION", "SECONDAIRE"),)
        def scope_allows(self, cap, scope_type, value):
            return value == "SECONDAIRE"

    assert resolve_audience(Connection(), Actor(), uuid4(), "SECTION", uuid4(), "communications.send.section") == []
