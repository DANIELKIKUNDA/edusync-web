from __future__ import annotations

from uuid import UUID

from edusync.modules.audit.domain.audit import AuditRecord
from edusync.modules.iam.domain.models import Membership, User
from edusync.modules.platform.domain.school import School
from edusync.modules.sync.domain.outbox import OutboxMessage


class MemorySchoolRepository:
    def __init__(self): self.items: dict[UUID, School] = {}
    def add(self, school: School) -> None: self.items[school.id] = school
    def get(self, school_id: UUID) -> School | None: return self.items.get(school_id)
    def get_by_code(self, code: str) -> School | None:
        code = code.strip().upper()
        return next((x for x in self.items.values() if x.code == code), None)
    def list(self) -> list[School]: return sorted(self.items.values(), key=lambda x: x.name.casefold())
    def save(self, school: School) -> None: self.items[school.id] = school


class MemoryAuditRepository:
    def __init__(self): self.items: list[AuditRecord] = []
    def append(self, record: AuditRecord) -> None: self.items.append(record)


class MemoryOutboxRepository:
    def __init__(self): self.items: list[OutboxMessage] = []
    def add(self, message: OutboxMessage) -> None: self.items.append(message)


class MemoryUserRepository:
    def __init__(self): self.items: dict[UUID, User] = {}
    def add(self, user: User) -> None: self.items[user.id] = user
    def get(self, user_id: UUID) -> User | None: return self.items.get(user_id)
    def get_by_email(self, email: str) -> User | None:
        email = email.strip().lower()
        return next((u for u in self.items.values() if u.email == email), None)


class MemoryMembershipRepository:
    DEFAULT_ROLE_PERMISSIONS = {
        # Legacy compatibility only. Runtime production uses the Point 3 RBAC tables.
        "SCHOOL_ADMIN": frozenset({"school.manage", "users.manage", "configuration.manage", "audit.read"}),
        "ADMIN_SYSTEME_ECOLE": frozenset({
            "settings.school_identity.read", "settings.school_identity.update",
            "settings.academic_year.read", "settings.academic_year.create", "settings.academic_year.update",
            "settings.structure.read", "settings.sections.manage", "settings.classes.create",
            "settings.fee_types.read", "settings.fee_types.manage", "settings.tariffs.read", "settings.tariffs.manage",
            "access.users.create", "access.users.read", "access.roles.manage", "audit.school.read",
        }),
        "DIRECTION": frozenset({"school.read", "schooling.read", "finance.read", "reports.read"}),
        "CAISSIER": frozenset({"finance.collect", "cash.manage", "receipts.reprint"}),
        "SECRETARIAT": frozenset({"schooling.manage", "students.manage", "families.manage"}),
        "INTENDANT": frozenset({"stewardship.manage", "stock.manage", "suppliers.manage"}),
    }
    def __init__(self):
        self.items: dict[UUID, Membership] = {}
        self.roles: dict[UUID, set[str]] = {}
    def add(self, membership: Membership) -> None:
        self.items[membership.id] = membership
        self.roles.setdefault(membership.id, set())
    def get_for_user_school(self, user_id: UUID, school_id: UUID) -> Membership | None:
        return next((m for m in self.items.values() if m.user_id == user_id and m.school_id == school_id), None)
    def set_role(self, membership_id: UUID, role_code: str) -> None:
        if membership_id not in self.items: raise LookupError("Membership introuvable")
        self.roles.setdefault(membership_id, set()).add(role_code)
    def permissions(self, membership_id: UUID) -> frozenset[str]:
        perms: set[str] = set()
        for role in self.roles.get(membership_id, set()):
            perms.update(self.DEFAULT_ROLE_PERMISSIONS.get(role, ()))
        return frozenset(perms)
