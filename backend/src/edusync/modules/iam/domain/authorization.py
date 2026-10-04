from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Iterable
from uuid import UUID, uuid4


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class OfflinePolicy(StrEnum):
    SERVER_ONLY = "SERVER_ONLY"
    READ_CACHE = "READ_CACHE"
    LOCAL_WRITE_SYNC = "LOCAL_WRITE_SYNC"
    PREAUTHORIZED_CRITICAL = "PREAUTHORIZED_CRITICAL"
    EXTERNAL_PROOF_REQUIRED = "EXTERNAL_PROOF_REQUIRED"


class RoleLevel(StrEnum):
    PLATFORM = "PLATFORM"
    SCHOOL = "SCHOOL"


class RoleKind(StrEnum):
    PLATFORM_STANDARD = "PLATFORM_STANDARD"
    SCHOOL_STANDARD = "SCHOOL_STANDARD"
    SCHOOL_CUSTOM = "SCHOOL_CUSTOM"


class RoleStatus(StrEnum):
    DRAFT = "DRAFT"
    OWNER_APPROVED = "OWNER_APPROVED"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class ScopeType(StrEnum):
    PLATFORM = "PLATFORM"
    SCHOOL = "SCHOOL"
    CYCLE = "CYCLE"
    SECTION = "SECTION"
    CLASS = "CLASS"


@dataclass(frozen=True, slots=True)
class Capability:
    code: str
    domain: str
    group: str
    label: str
    action: str
    risk: RiskLevel
    offline_policy: str
    audit_required: bool
    scope_types: tuple[str, ...]
    outputs: tuple[str, ...] = ()
    sensitive: bool = False
    source_status: str = ""
    prerequisites: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.code or "." not in self.code:
            raise ValueError("Code de capacité invalide")
        if not self.domain or not self.group or not self.label:
            raise ValueError("Métadonnées de capacité incomplètes")


@dataclass(frozen=True, slots=True)
class ScopeRef:
    type: ScopeType
    value: str | None = None

    def __post_init__(self) -> None:
        if self.type in {ScopeType.PLATFORM, ScopeType.SCHOOL} and self.value is not None:
            raise ValueError(f"{self.type} ne doit pas porter de valeur")
        if self.type in {ScopeType.CYCLE, ScopeType.SECTION, ScopeType.CLASS} and not self.value:
            raise ValueError(f"{self.type} exige une valeur")


@dataclass(slots=True)
class Role:
    code: str
    label: str
    level: RoleLevel
    kind: RoleKind
    school_id: UUID | None = None
    id: UUID = field(default_factory=uuid4)
    description: str = ""
    status: RoleStatus = RoleStatus.DRAFT
    capability_codes: set[str] = field(default_factory=set)
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        self.code = self.code.strip().upper()
        self.label = self.label.strip()
        if not self.code or not self.label:
            raise ValueError("Code et libellé du rôle obligatoires")
        if self.level == RoleLevel.PLATFORM and self.school_id is not None:
            raise ValueError("Un rôle plateforme ne dépend pas d'une école")
        if self.kind == RoleKind.SCHOOL_CUSTOM and self.school_id is None:
            raise ValueError("Un rôle personnalisé doit appartenir à une école")
        if self.level == RoleLevel.SCHOOL and self.kind == RoleKind.PLATFORM_STANDARD:
            raise ValueError("Incohérence niveau/type de rôle")
        if self.version < 1:
            raise ValueError("Version de rôle invalide")

    def grant(self, capability_code: str) -> None:
        self.capability_codes.add(capability_code)

    def revoke(self, capability_code: str) -> None:
        self.capability_codes.discard(capability_code)

    def approve_by_owner(self) -> None:
        if self.status != RoleStatus.DRAFT:
            raise ValueError("Seul un rôle brouillon peut être approuvé")
        self.status = RoleStatus.OWNER_APPROVED
        self.version += 1

    def activate(self) -> None:
        if self.status != RoleStatus.OWNER_APPROVED:
            raise ValueError("Le rôle doit d'abord être approuvé par le propriétaire")
        self.status = RoleStatus.ACTIVE
        self.version += 1


@dataclass(slots=True)
class RoleAssignment:
    user_id: UUID
    role_id: UUID
    role_level: RoleLevel
    school_id: UUID | None = None
    membership_id: UUID | None = None
    scopes: tuple[ScopeRef, ...] = ()
    id: UUID = field(default_factory=uuid4)
    active: bool = True
    valid_from: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    valid_until: datetime | None = None
    granted_by_user_id: UUID | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.role_level == RoleLevel.PLATFORM:
            if self.school_id is not None or self.membership_id is not None:
                raise ValueError("Une affectation plateforme ne doit pas viser une école")
            if self.scopes and self.scopes != (ScopeRef(ScopeType.PLATFORM),):
                raise ValueError("Périmètre plateforme invalide")
        else:
            if self.school_id is None or self.membership_id is None:
                raise ValueError("Une affectation école exige school_id et membership_id")
            if not self.scopes:
                raise ValueError("Une affectation école exige au moins un périmètre")
            if any(s.type == ScopeType.PLATFORM for s in self.scopes):
                raise ValueError("Périmètre plateforme interdit dans une école")

    def is_effective(self, at: datetime | None = None) -> bool:
        at = at or datetime.now(timezone.utc)
        if not self.active or at < self.valid_from:
            return False
        return self.valid_until is None or at < self.valid_until


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    user_id: UUID
    capability_code: str
    school_id: UUID | None = None
    resource_scope: ScopeRef | None = None


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    matched_role_ids: tuple[UUID, ...] = ()


def scope_covers(assignment_scope: ScopeRef, resource_scope: ScopeRef | None) -> bool:
    """Generic coarse scope rule.

    Hierarchical membership (e.g. CLASS belongs to SECTION) must be resolved by a
    domain scope resolver before calling this function. This deliberately avoids
    guessing school structure inside IAM.
    """
    if assignment_scope.type in {ScopeType.PLATFORM, ScopeType.SCHOOL}:
        return True
    if resource_scope is None:
        return False
    return assignment_scope.type == resource_scope.type and assignment_scope.value == resource_scope.value


def decide(
    context: AuthorizationContext,
    assignments: Iterable[RoleAssignment],
    roles_by_id: dict[UUID, Role],
) -> AuthorizationDecision:
    matched: list[UUID] = []
    for assignment in assignments:
        if assignment.user_id != context.user_id or not assignment.is_effective():
            continue
        role = roles_by_id.get(assignment.role_id)
        if role is None or role.status != RoleStatus.ACTIVE:
            continue
        if context.capability_code not in role.capability_codes:
            continue
        if role.level == RoleLevel.PLATFORM:
            if context.school_id is None:
                matched.append(role.id)
            continue
        if context.school_id != assignment.school_id:
            continue
        if any(scope_covers(scope, context.resource_scope) for scope in assignment.scopes):
            matched.append(role.id)
    if matched:
        return AuthorizationDecision(True, "CAPABILITY_GRANTED", tuple(matched))
    return AuthorizationDecision(False, "CAPABILITY_NOT_GRANTED")
