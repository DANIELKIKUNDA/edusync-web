from uuid import uuid4
import pytest
from edusync.adapters.memory import *
from edusync.modules.platform.application.use_cases import *
from edusync.shared.application.context import ActorContext


def actor(platform=True):
    return ActorContext(user_id=uuid4(), school_id=None, membership_id=None,
                        permissions=frozenset(), is_platform_admin=platform, correlation_id=uuid4())

def test_create_school_writes_audit_and_outbox():
    schools, audit, outbox = MemorySchoolRepository(), MemoryAuditRepository(), MemoryOutboxRepository()
    school = CreateSchool(schools, audit, outbox).execute(actor(), CreateSchoolCommand(name="École A", code="A"))
    assert schools.get(school.id) is school
    assert audit.items[-1].action == "SCHOOL_CREATED"
    assert outbox.items[-1].event_type == "SCHOOL_CREATED"
    assert audit.items[-1].school_id == school.id

def test_duplicate_school_code_blocked():
    schools, audit, outbox = MemorySchoolRepository(), MemoryAuditRepository(), MemoryOutboxRepository()
    uc = CreateSchool(schools, audit, outbox)
    uc.execute(actor(), CreateSchoolCommand(name="École A", code="A"))
    with pytest.raises(ValueError):
        uc.execute(actor(), CreateSchoolCommand(name="École B", code="a"))

def test_non_platform_user_cannot_create_school():
    with pytest.raises(PermissionError):
        CreateSchool(MemorySchoolRepository(), MemoryAuditRepository(), MemoryOutboxRepository()).execute(
            actor(False), CreateSchoolCommand(name="École A", code="A"))

def test_bootstrap_admin_creates_membership_and_role():
    schools, audit, outbox = MemorySchoolRepository(), MemoryAuditRepository(), MemoryOutboxRepository()
    users, memberships = MemoryUserRepository(), MemoryMembershipRepository()
    school = CreateSchool(schools, audit, outbox).execute(actor(), CreateSchoolCommand(name="École A", code="A"))
    user, membership = BootstrapSchoolAdmin(schools, users, memberships, audit, outbox).execute(
        actor(), BootstrapSchoolAdminCommand(school.id, "admin@a.cd", "Admin A", "motdepasse-solide"))
    assert membership.school_id == school.id
    assert "settings.school_identity.update" in memberships.permissions(membership.id)
