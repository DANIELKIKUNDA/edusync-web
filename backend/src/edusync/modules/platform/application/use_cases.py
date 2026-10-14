from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from edusync.modules.audit.domain.audit import AuditRecord
from edusync.modules.audit.ports.repositories import AuditRepository
from edusync.modules.iam.domain.models import Membership, User
from edusync.modules.iam.ports.repositories import MembershipRepository, UserRepository
from edusync.modules.platform.domain.school import School
from edusync.modules.platform.ports.repositories import SchoolRepository
from edusync.modules.sync.domain.outbox import OutboxMessage
from edusync.modules.sync.ports.repositories import OutboxRepository
from edusync.shared.application.context import ActorContext
from edusync.shared.infrastructure.security import hash_password


def _dedup(actor: ActorContext, event_type: str, aggregate_id: UUID) -> str | None:
    if actor.idempotency_key:
        return f"{actor.idempotency_key}:{event_type}:{aggregate_id}"
    if actor.correlation_id:
        return f"{actor.correlation_id}:{event_type}:{aggregate_id}"
    return None


@dataclass(frozen=True, slots=True)
class CreateSchoolCommand:
    name: str
    code: str
    logo_url: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    province: str | None = None


class CreateSchool:
    def __init__(self, schools: SchoolRepository, audit: AuditRepository, outbox: OutboxRepository):
        self.schools, self.audit, self.outbox = schools, audit, outbox

    def execute(self, actor: ActorContext, cmd: CreateSchoolCommand) -> School:
        actor.require("platform.schools.create")
        if self.schools.get_by_code(cmd.code.strip().upper()):
            raise ValueError("Ce code école existe déjà")
        clean = lambda v: (v or "").strip() or None  # noqa: E731
        school = School(name=cmd.name, code=cmd.code, logo_url=cmd.logo_url, email=clean(cmd.email), phone=clean(cmd.phone),
                        address=clean(cmd.address), city=clean(cmd.city), province=clean(cmd.province))
        self.schools.add(school)
        self.audit.append(AuditRecord(
            action="SCHOOL_CREATED", entity_type="School", entity_id=school.id,
            actor_user_id=actor.user_id, school_id=school.id, source=actor.source,
            new_data={"name": school.name, "code": school.code, "status": school.status.value, "email": school.email,
                      "phone": school.phone, "address": school.address, "city": school.city, "province": school.province},
            correlation_id=actor.correlation_id, idempotency_key=actor.idempotency_key,
        ))
        self.outbox.add(OutboxMessage(
            event_type="SCHOOL_CREATED", aggregate_type="School", aggregate_id=school.id,
            school_id=school.id, payload={"name": school.name, "code": school.code},
            correlation_id=actor.correlation_id,
            deduplication_key=_dedup(actor, "SCHOOL_CREATED", school.id),
        ))
        return school


class ChangeSchoolStatus:
    def __init__(self, schools: SchoolRepository, audit: AuditRepository, outbox: OutboxRepository):
        self.schools, self.audit, self.outbox = schools, audit, outbox

    def suspend(self, actor: ActorContext, school_id: UUID, reason: str) -> School:
        actor.require("platform.schools.suspend")
        school = self.schools.get(school_id)
        if not school:
            raise LookupError("École introuvable")
        old = school.status.value
        school.suspend(reason)
        self.schools.save(school)
        self.audit.append(AuditRecord(
            action="SCHOOL_SUSPENDED", entity_type="School", entity_id=school.id,
            actor_user_id=actor.user_id, school_id=school.id, source=actor.source,
            old_data={"status": old}, new_data={"status": school.status.value}, reason=reason,
            correlation_id=actor.correlation_id, idempotency_key=actor.idempotency_key,
        ))
        self.outbox.add(OutboxMessage(
            event_type="SCHOOL_SUSPENDED", aggregate_type="School", aggregate_id=school.id,
            school_id=school.id, payload={"reason": reason}, correlation_id=actor.correlation_id,
            deduplication_key=_dedup(actor, "SCHOOL_SUSPENDED", school.id),
        ))
        return school

    def reactivate(self, actor: ActorContext, school_id: UUID) -> School:
        actor.require("platform.schools.activate")
        school = self.schools.get(school_id)
        if not school:
            raise LookupError("École introuvable")
        old = school.status.value
        school.reactivate()
        self.schools.save(school)
        self.audit.append(AuditRecord(
            action="SCHOOL_REACTIVATED", entity_type="School", entity_id=school.id,
            actor_user_id=actor.user_id, school_id=school.id, source=actor.source,
            old_data={"status": old}, new_data={"status": school.status.value},
            correlation_id=actor.correlation_id, idempotency_key=actor.idempotency_key,
        ))
        self.outbox.add(OutboxMessage(
            event_type="SCHOOL_REACTIVATED", aggregate_type="School", aggregate_id=school.id,
            school_id=school.id, payload={}, correlation_id=actor.correlation_id,
            deduplication_key=_dedup(actor, "SCHOOL_REACTIVATED", school.id),
        ))
        return school


@dataclass(frozen=True, slots=True)
class BootstrapSchoolAdminCommand:
    school_id: UUID
    email: str
    full_name: str
    password: str


class BootstrapSchoolAdmin:
    def __init__(self, schools: SchoolRepository, users: UserRepository, memberships: MembershipRepository,
                 audit: AuditRepository, outbox: OutboxRepository):
        self.schools, self.users, self.memberships = schools, users, memberships
        self.audit, self.outbox = audit, outbox

    def execute(self, actor: ActorContext, cmd: BootstrapSchoolAdminCommand) -> tuple[User, Membership]:
        actor.require("platform.school_admin.bootstrap")
        school = self.schools.get(cmd.school_id)
        if not school:
            raise LookupError("École introuvable")
        existing = self.users.get_by_email(cmd.email)
        created = False
        if existing:
            if not existing.active:
                raise ValueError("Ce compte utilisateur est désactivé")
            user = existing
        else:
            user = User(email=cmd.email, full_name=cmd.full_name, password_hash=hash_password(cmd.password))
            self.users.add(user)
            # Owner decision 2026-10-14 (Desktop parity: the first administrator sets his own secret): the password typed
            # by the platform is a bootstrap credential only; it opens the password-choice step, never a session.
            self.users.require_password_change(user.id, set_by="PLATFORM")
            created = True
        membership = self.memberships.get_for_user_school(user.id, school.id)
        if membership is None:
            membership = Membership(user_id=user.id, school_id=school.id)
            self.memberships.add(membership)
        elif not membership.active:
            raise ValueError("L'appartenance de cet utilisateur à l'école est désactivée")
        self.memberships.set_role(membership.id, "ADMIN_SYSTEME_ECOLE")
        self.audit.append(AuditRecord(
            action="SCHOOL_ADMIN_BOOTSTRAPPED", entity_type="Membership", entity_id=membership.id,
            actor_user_id=actor.user_id, school_id=school.id, source=actor.source,
            new_data={"user_id": str(user.id), "email": user.email, "role": "ADMIN_SYSTEME_ECOLE",
                      "account": "CREATED_PASSWORD_TO_CHOOSE" if created else "EXISTING_ACCOUNT_ATTACHED"},
            correlation_id=actor.correlation_id, idempotency_key=actor.idempotency_key,
        ))
        self.outbox.add(OutboxMessage(
            event_type="SCHOOL_ADMIN_BOOTSTRAPPED", aggregate_type="Membership",
            aggregate_id=membership.id, school_id=school.id, payload={"user_id": str(user.id)},
            correlation_id=actor.correlation_id,
            deduplication_key=_dedup(actor, "SCHOOL_ADMIN_BOOTSTRAPPED", membership.id),
        ))
        return user, membership
