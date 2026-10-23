"""Effective school capabilities (owner decisions 2026-10-23, migration 0085) — one SQL definition shared by the login /
menu union (memberships.permissions), the scoped grants (effective_capability_grants) and the access projection.

    effective(assignment) = baseline(role) − school REVOKE + school GRANT          (standard roles keep their identity)
    effective(member)     = ⋃ effective(assignment) within its scopes ∪ temporary exception grants
    then format aliases:  a variant and its canonical *.export are the same authorization (both directions)

A REVOKE of a canonical *.export also withdraws its format variants carried by the baseline, so an alias can never
bring back what the school removed. Policies only exist for standard roles (trigger in 0085), so custom roles and
platform roles are unchanged.
"""
from __future__ import annotations

# Role capabilities of one assignment row `a` (alias: a.school_id, a.role_id), after the school's policy.
ASSIGNMENT_CAPABILITIES = """
    SELECT rc.capability_code
      FROM rbac_role_capabilities rc
      LEFT JOIN capability_catalog k ON k.code=rc.capability_code
     WHERE rc.role_id=a.role_id
       AND NOT EXISTS (SELECT 1 FROM rbac_school_role_policies p
                        WHERE p.active AND p.effect='REVOKE' AND p.school_id=a.school_id AND p.role_id=a.role_id
                          AND p.capability_code IN (rc.capability_code, k.alias_of))
    UNION
    SELECT p.capability_code FROM rbac_school_role_policies p
     WHERE p.active AND p.effect='GRANT' AND p.school_id=a.school_id AND p.role_id=a.role_id
"""

# Expands a CTE named `held(code)` with the format aliases: canonical of each variant, then every variant of a canonical.
ALIAS_EXPANSION = """
    , canon AS (
        SELECT code FROM held
        UNION SELECT k.alias_of FROM held JOIN capability_catalog k ON k.code=held.code AND k.alias_of IS NOT NULL
    )
    SELECT code FROM canon
    UNION SELECT k.code FROM capability_catalog k WHERE k.alias_of IN (SELECT code FROM canon)
"""


def expand_aliases(codes: set[str], aliases: dict[str, str]) -> set[str]:
    """Python twin of ALIAS_EXPANSION (aliases: variant -> canonical)."""
    canon = set(codes) | {aliases[c] for c in codes if c in aliases}
    return canon | {v for v, c in aliases.items() if c in canon}
