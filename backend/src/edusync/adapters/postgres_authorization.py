from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection

from edusync.modules.iam.domain.authorization import (
    AuthorizationContext,
    AuthorizationDecision,
    Role,
    RoleAssignment,
    RoleKind,
    RoleLevel,
    RoleStatus,
    ScopeRef,
    ScopeType,
    decide,
)


@dataclass(slots=True)
class PostgresAuthorizationRepository:
    connection: Connection

    def effective_role_assignments(self, user_id: UUID, school_id: UUID | None) -> tuple[RoleAssignment, ...]:
        rows = self.connection.execute(text("""
            SELECT a.id,a.user_id,a.role_id,a.school_id,a.membership_id,a.active,a.valid_from,a.valid_until,
                   a.granted_by_user_id,a.reason,r.level,
                   s.scope_type,s.scope_value
              FROM rbac_assignments a
              JOIN rbac_roles r ON r.id=a.role_id
              LEFT JOIN rbac_assignment_scopes s ON s.assignment_id=a.id
             WHERE a.user_id=:uid
               AND a.active=true
               AND a.valid_from<=now()
               AND (a.valid_until IS NULL OR a.valid_until>now())
               AND ((CAST(:sid AS uuid) IS NULL AND a.school_id IS NULL) OR a.school_id=:sid)
             ORDER BY a.id,s.scope_type,s.scope_value
        """), {"uid": user_id, "sid": school_id}).all()
        grouped: dict[UUID, dict] = {}
        for row in rows:
            m=row._mapping
            item=grouped.setdefault(m['id'], {
                'id':m['id'],'user_id':m['user_id'],'role_id':m['role_id'],'school_id':m['school_id'],
                'membership_id':m['membership_id'],'active':bool(m['active']),'valid_from':m['valid_from'],
                'valid_until':m['valid_until'],'granted_by_user_id':m['granted_by_user_id'],'reason':m['reason'],
                'role_level':RoleLevel(m['level']),'scopes':[]
            })
            if m['scope_type'] is not None:
                item['scopes'].append(ScopeRef(ScopeType(m['scope_type']), m['scope_value']))
        return tuple(RoleAssignment(**{**v,'scopes':tuple(v['scopes'])}) for v in grouped.values())

    def roles(self, role_ids: set[UUID]) -> dict[UUID, Role]:
        if not role_ids:
            return {}
        stmt = text("""
            SELECT r.id,r.school_id,r.code,r.label,r.description,r.level,r.kind,r.status,r.version,r.created_at,
                   c.capability_code
              FROM rbac_roles r
              LEFT JOIN rbac_role_capabilities c ON c.role_id=r.id
             WHERE r.id IN :ids
             ORDER BY r.id,c.capability_code
        """).bindparams(bindparam("ids", expanding=True))
        rows = self.connection.execute(stmt, {"ids": list(role_ids)}).all()
        grouped: dict[UUID, dict] = {}
        for row in rows:
            m=row._mapping
            item=grouped.setdefault(m['id'], {
                'id':m['id'],'school_id':m['school_id'],'code':m['code'],'label':m['label'],
                'description':m['description'],'level':RoleLevel(m['level']),'kind':RoleKind(m['kind']),
                'status':RoleStatus(m['status']),'version':int(m['version']),'created_at':m['created_at'],
                'capability_codes':set()
            })
            if m['capability_code']:
                item['capability_codes'].add(str(m['capability_code']))
        return {rid:Role(**v) for rid,v in grouped.items()}


    def effective_capability_grants(self, user_id: UUID, school_id: UUID) -> tuple[tuple[str, str, str | None], ...]:
        """Return capability-bound scopes for tenant resource filtering.

        This is intentionally more precise than the coarse permission union used
        for menu rendering: a SCHOOL scope attached to role A may not widen a
        SECTION-scoped capability that came only from role B.
        """
        from edusync.adapters.rbac_effective import ASSIGNMENT_CAPABILITIES
        rows = self.connection.execute(text(f"""
            WITH held(code, scope_type, scope_value) AS (
                SELECT DISTINCT ac.capability_code, s.scope_type, s.scope_value
                  FROM rbac_assignments a
                  JOIN rbac_roles r ON r.id=a.role_id AND r.status='ACTIVE'
                  CROSS JOIN LATERAL ({ASSIGNMENT_CAPABILITIES}) ac
                  JOIN rbac_assignment_scopes s ON s.assignment_id=a.id
                 WHERE a.user_id=:uid AND a.school_id=:sid AND a.active=true
                   AND a.valid_from<=now() AND (a.valid_until IS NULL OR a.valid_until>now())
                UNION
                SELECT eg.capability_code,eg.scope_type,eg.scope_value
                  FROM rbac_exception_grants eg
                 WHERE eg.user_id=:uid AND eg.school_id=:sid AND eg.active=true
                   AND eg.valid_from<=now() AND eg.valid_until>now()
            ), canon AS (
                SELECT code, scope_type, scope_value FROM held
                UNION SELECT k.alias_of, h.scope_type, h.scope_value FROM held h JOIN capability_catalog k ON k.code=h.code AND k.alias_of IS NOT NULL
            )
            SELECT code, scope_type, scope_value FROM canon
            UNION SELECT k.code, c.scope_type, c.scope_value FROM canon c JOIN capability_catalog k ON k.alias_of=c.code
             ORDER BY 1,2,3
        """), {"uid":user_id,"sid":school_id}).all()
        return tuple((str(r[0]),str(r[1]),None if r[2] is None else str(r[2])) for r in rows)

    def _apply_school_policies(self, roles: dict[UUID, Role], school_id: UUID) -> None:
        """standard role + school GRANT - school REVOKE, then format aliases (rbac_effective.py)."""
        from edusync.adapters.rbac_effective import expand_aliases
        aliases = {str(r[0]): str(r[1]) for r in self.connection.execute(text(
            "SELECT code, alias_of FROM capability_catalog WHERE alias_of IS NOT NULL")).all()}
        if not roles:
            return
        stmt = text("""SELECT role_id, capability_code, effect FROM rbac_school_role_policies
                        WHERE active AND school_id=:sid AND role_id IN :ids""").bindparams(bindparam("ids", expanding=True))
        policies = self.connection.execute(stmt, {"sid": school_id, "ids": list(roles)}).all()
        for rid, role in roles.items():
            caps = set(role.capability_codes)
            for prid, cap, effect in policies:
                if prid != rid:
                    continue
                if effect == 'REVOKE':
                    caps -= {cap} | {v for v, c in aliases.items() if c == cap}
                else:
                    caps.add(cap)
            role.capability_codes = expand_aliases(caps, aliases)

    def authorize(self, context: AuthorizationContext) -> AuthorizationDecision:
        assignments=self.effective_role_assignments(context.user_id, context.school_id)
        roles=self.roles({a.role_id for a in assignments})
        if context.school_id is not None:
            self._apply_school_policies(roles, context.school_id)
        base=decide(context, assignments, roles)
        if base.allowed:
            return base
        if context.school_id is None:
            return base
        # Rare, explicit, time-limited individual grants. They are union grants only;
        # there is no hidden negative override model.
        row=self.connection.execute(text("""
            SELECT id,scope_type,scope_value
              FROM rbac_exception_grants
             WHERE school_id=:sid AND user_id=:uid AND capability_code=:cap
               AND active=true AND valid_from<=now() AND valid_until>now()
             ORDER BY valid_until DESC LIMIT 1
        """), {'sid':context.school_id,'uid':context.user_id,'cap':context.capability_code}).first()
        if row is None:
            return base
        scope=ScopeRef(ScopeType(row._mapping['scope_type']), row._mapping['scope_value'])
        from edusync.modules.iam.domain.authorization import scope_covers
        if scope_covers(scope, context.resource_scope):
            return AuthorizationDecision(True, 'TEMPORARY_EXCEPTION_GRANT')
        return base
