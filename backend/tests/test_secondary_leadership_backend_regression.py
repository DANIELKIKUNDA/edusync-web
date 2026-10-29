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
    assert "cap,_,_=_group_meta(group_by);_need(actor,cap);scopes=_scopes(actor,cap)" in EFFECTIFS
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


def test_parent_audience_uses_tenant_classes_and_active_guardians():
    messaging = (ROOT / "src/edusync/modules/communications/application/messaging.py").read_text(encoding="utf-8")
    assert "c.id=e.class_id AND c.school_id=e.school_id" in messaging
    assert "fg.school_id=s.school_id AND fg.is_primary AND fg.active" in messaging
    assert "SELECT DISTINCT ON (g.id, sec.code) g.id, g.full_name" in messaging
    assert "if r[\"id\"] in seen:" in messaging


def test_parent_audience_joins_academic_year_section_and_guardian_with_tenant():
    messaging = (ROOT / "src/edusync/modules/communications/application/messaging.py").read_text(encoding="utf-8")
    assert "y.id=e.academic_year_id AND y.school_id=e.school_id" in messaging
    assert "sec.id=c.section_id AND sec.school_id=c.school_id" in messaging
    assert "g.id=fg.guardian_id AND g.school_id=fg.school_id" in messaging


def test_communications_preview_rejects_in_app_only_draft():
    from fastapi import HTTPException
    from edusync.modules.communications.api.router import Draft, preview
    draft = Draft(audience_type="INDIVIDUAL", channel="IN_APP",
                  body="Message", idempotency_key="preview-123456")
    try:
        preview(draft, actor=object(), services=object())
    except HTTPException as exc:
        assert exc.status_code == 422
        assert "canal" in str(exc.detail)
    else:
        raise AssertionError("A preview without an external channel must be rejected")


def test_director_studies_cannot_send_bulk_sms_without_capability():
    from fastapi import HTTPException
    from edusync.modules.communications.api.router import Draft, _authorize

    class Actor:
        def require(self, capability):
            if capability not in {"communications.compose", "communications.send.class",
                                  "communications.sms.send"}:
                raise PermissionError(capability)

    draft = Draft(audience_type="CLASS", channel="SMS",
                  body="Réunion", idempotency_key="studies-123456")
    try:
        _authorize(Actor(), draft, ["SMS"])
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Bulk SMS must require communications.sms.bulk_send")


def test_director_discipline_bulk_sms_capability_allows_class_audience():
    from edusync.modules.communications.api.router import Draft, _authorize

    class Actor:
        def require(self, capability):
            assert capability in {"communications.compose", "communications.send.class",
                                  "communications.sms.bulk_send"}

    draft = Draft(audience_type="CLASS", channel="SMS",
                  body="Réunion", idempotency_key="discipline-123456")
    assert _authorize(Actor(), draft, ["SMS"]) == "communications.send.class"


PERSONNEL = (ROOT / "src/edusync/modules/personnel/api/router.py").read_text(encoding="utf-8")


def test_directors_staff_directory_and_profile_use_read_scopes():
    assert "_need(actor,'personnel.read');scopes=_scopes(actor,'personnel.read')" in PERSONNEL
    assert "repo.list_staff(actor.school_id,query=q,status=status,category=category,scopes=scopes" in PERSONNEL
    assert "repo.count_staff(actor.school_id,query=q,status=status,category=category,scopes=scopes)" in PERSONNEL
    assert "get_staff(actor.school_id,staff_id,scopes=scopes)" in PERSONNEL


def test_directors_staff_assignments_and_summary_use_independent_scopes():
    assert "_need(actor,'personnel.assignments.read');scopes=_scopes(actor,'personnel.assignments.read')" in PERSONNEL
    assert "list_assignments(actor.school_id,staff_id,scopes=scopes" in PERSONNEL
    assert "_need(actor,'personnel.summary.read');scopes=_scopes(actor,'personnel.summary.read')" in PERSONNEL
    assert "summary(actor.school_id,scopes=scopes)" in PERSONNEL


def test_directors_cannot_see_staff_account_links_without_separate_permission():
    assert "if 'personnel.access_link.read' not in actor.permissions: item['access_links']=[]" in PERSONNEL
    for role in ("DIRECTEUR_ETUDES", "DIRECTEUR_DISCIPLINE"):
        assert "personnel.access_link.read" not in _grants(role)


def test_staff_assignment_scope_options_are_filtered_by_capability():
    endpoint = PERSONNEL.split("def scope_options(", 1)[1].split("\n@router.", 1)[0]
    assert "capabilities=('personnel.assignments.add','personnel.assignments.read')" in endpoint
    assert "actor.scope_allows(cap,'SECTION',section_code)" in endpoint
    assert "if visible(section['code'])" in endpoint
    assert "if visible(school_class['section_code'])" in endpoint


def test_staff_scope_options_joins_belong_to_same_school():
    endpoint = PERSONNEL.split("def scope_options(", 1)[1].split("\n@router.", 1)[0]
    assert "s.id=c.section_id AND s.school_id=c.school_id" in endpoint
    assert "y.id=c.academic_year_id AND y.school_id=c.school_id" in endpoint


def test_communication_delivery_history_joins_tenant_message_and_recipient():
    endpoint = COMMUNICATIONS.split("def deliveries(", 1)[1].split("\n@router.", 1)[0]
    assert "m.id=d.message_id AND m.school_id=d.school_id" in endpoint
    assert "r.id=d.recipient_id AND r.school_id=d.school_id AND r.message_id=d.message_id" in endpoint
    assert "WHERE d.message_id=:m AND d.school_id=:s" in endpoint


DOCUMENTS = (ROOT / "src/edusync/modules/documents/api/router.py").read_text(encoding="utf-8")
AUDIT = (ROOT / "src/edusync/modules/audit/api/router.py").read_text(encoding="utf-8")
NOTIFICATIONS = (ROOT / "src/edusync/modules/notifications/api/router.py").read_text(encoding="utf-8")


def test_current_documents_history_joins_generations_in_same_tenant():
    assert "g.id=c.latest_generation_id AND g.school_id=c.school_id" in DOCUMENTS
    assert "g.required_capability=ANY(CAST(:caps AS text[]))" in DOCUMENTS
    assert "object_store.school_wide_capabilities(actor)" in DOCUMENTS


def test_notifications_are_scoped_to_actor_and_school():
    assert "WHERE school_id=:sid AND user_id=:uid" in NOTIFICATIONS
    assert "WHERE id=:id AND school_id=:sid AND user_id=:uid" in NOTIFICATIONS


def test_audit_entity_history_has_school_and_capability_guard():
    assert "need(actor,'audit.entity.history.read')" in AUDIT
    assert "WHERE school_id=:sid AND entity_type=:et AND entity_id=:eid" in AUDIT
