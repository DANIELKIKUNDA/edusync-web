from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


class CapabilityDenied(PermissionError):
    """The authenticated actor lacks a required application capability."""


@dataclass(frozen=True, slots=True)
class ActorContext:
    user_id: UUID
    school_id: UUID | None
    membership_id: UUID | None
    permissions: frozenset[str]
    is_platform_admin: bool = False
    device_id: UUID | None = None
    source: str = "WEB"
    correlation_id: UUID | None = None
    idempotency_key: str | None = None
    capability_scopes: tuple[tuple[str, str, str | None], ...] = ()
    # Device session of the access token (platform actors): used by the step-up check of sensitive actions.
    session_id: UUID | None = None

    def scopes_for(self, permission: str) -> tuple[tuple[str, str | None], ...]:
        """Effective scopes for one capability. SCHOOL covers every school resource.

        Keeping capability and scope coupled prevents a broad scope from one role
        from widening an unrelated capability granted by another role.
        """
        return tuple((scope_type, scope_value) for cap, scope_type, scope_value in self.capability_scopes if cap == permission)

    def scope_allows(self, permission: str, scope_type: str, scope_value: str | None = None) -> bool:
        for granted_type, granted_value in self.scopes_for(permission):
            if granted_type == "SCHOOL":
                return True
            if granted_type == scope_type and granted_value == scope_value:
                return True
        return False

    def require(self, permission: str) -> None:
        if self.is_platform_admin:
            return
        if permission not in self.permissions:
            raise CapabilityDenied(f"Permission requise: {permission}")
