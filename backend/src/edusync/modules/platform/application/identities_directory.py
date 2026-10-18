"""Annuaire « Utilisateurs & accès » of the platform (lot 2026-10): a read-only, cross-cutting directory of identities.

What it aggregates (audited, not assumed):
  - platform accounts: an active platform role assignment (rbac_assignments.school_id IS NULL, role level PLATFORM);
  - school accounts: an active membership in a school (school_memberships.active);
  an account may hold both. Managing them stays where it already lives: Équipe plateforme (platform roles, security),
  the school sheet (school administrator) and the school space (local business roles).

Definitions:
  scope            PLATFORM / SCHOOL / BOTH / NONE (no active platform role nor active school membership)
  status           DISABLED (account deactivated) > SUSPENDED (platform access suspended, platform_account_status)
                   > PENDING (first sign-in not done: temporary password to change or e-mail invitation not accepted)
                   > ACTIVE
  last_activity_at most recent activity of a device session of the account, platform or school (user_device_sessions)
"""
from __future__ import annotations

import base64
import json
import re
from uuid import UUID

from sqlalchemy import text

SCOPES = ("PLATFORM", "SCHOOL")
STATUSES = ("ACTIVE", "PENDING", "SUSPENDED", "DISABLED")
MAX_TERMS = 5
_KEY = "edusync_search_key(u.full_name || ' ' || u.email::text)"

_PLATFORM = """EXISTS (SELECT 1 FROM rbac_assignments pa JOIN rbac_roles pr ON pr.id=pa.role_id AND pr.level='PLATFORM'
                WHERE pa.user_id=u.id AND pa.school_id IS NULL AND pa.active)"""
_SCHOOL = "EXISTS (SELECT 1 FROM school_memberships sm WHERE sm.user_id=u.id AND sm.active)"
_PENDING = """(coalesce(u.must_change_password,false) OR EXISTS (SELECT 1 FROM account_tokens t WHERE t.user_id=u.id
               AND t.purpose='INVITATION' AND t.used_at IS NULL AND t.revoked_at IS NULL AND t.expires_at>now()))"""
_SUSPENDED = "EXISTS (SELECT 1 FROM platform_account_status ps WHERE ps.user_id=u.id AND ps.status='SUSPENDED')"
_STATUS_SQL = {
    "DISABLED": "NOT u.active",
    "SUSPENDED": f"u.active AND {_SUSPENDED}",
    "PENDING": f"u.active AND NOT {_SUSPENDED} AND {_PENDING}",
    "ACTIVE": f"u.active AND NOT {_SUSPENDED} AND NOT {_PENDING}",
}


def _search(q: str | None) -> tuple[list[str], dict]:
    words = [w for w in re.split(r"[\s\-'’.,;:/]+", q or "") if w][:MAX_TERMS]
    return ([f"{_KEY} LIKE '%' || edusync_search_key(CAST(:w{i} AS text)) || '%'" for i in range(len(words))],
            {f"w{i}": w for i, w in enumerate(words)})


def encode_cursor(row: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps([row["full_name"].lower(), str(row["id"])]).encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> dict | None:
    if not cursor:
        return None
    try:
        k1, kid = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        if not isinstance(k1, str):
            raise ValueError
        return {"k1": k1, "kid": str(UUID(str(kid)))}
    except Exception as exc:  # noqa: BLE001 — a forged or stale cursor is just refused
        raise ValueError("Curseur de pagination invalide") from exc


def _filters(q, scope, status, school_id, role, active_only) -> tuple[list[str], dict]:
    where, params = _search(q)
    if scope == "PLATFORM":
        where.append(_PLATFORM)
    elif scope == "SCHOOL":
        where.append(_SCHOOL)
    if status:
        where.append(_STATUS_SQL[status])
    if school_id:
        where.append("EXISTS (SELECT 1 FROM school_memberships fm WHERE fm.user_id=u.id AND fm.active AND fm.school_id=CAST(:school AS uuid))")
        params["school"] = str(school_id)
    if role:
        where.append("""EXISTS (SELECT 1 FROM rbac_assignments fa JOIN rbac_roles fr ON fr.id=fa.role_id AND fr.code=:role
                         LEFT JOIN school_memberships fam ON fam.id=fa.membership_id
                         WHERE fa.user_id=u.id AND fa.active AND (fa.school_id IS NULL OR fam.active))""")
        params["role"] = role
    if active_only:   # same definition as the dashboard KPI "Accès actifs"
        where.append(f"u.active AND {_SCHOOL}")
    return where, params


_PAGE = """
WITH page AS (
  SELECT u.id, u.full_name, u.email::text AS email, u.active, u.must_change_password
    FROM users u
   WHERE {where}
   ORDER BY lower(u.full_name), u.id
   LIMIT :lim
)
SELECT u.id, u.full_name, u.email, u.active,
       {platform} AS is_platform, {school} AS is_school,
       CASE WHEN NOT u.active THEN 'DISABLED' WHEN {suspended} THEN 'SUSPENDED' WHEN {pending} THEN 'PENDING' ELSE 'ACTIVE' END AS status,
       pr.platform_roles, sr.school_roles, sc.schools_count, fs.first_school_id, fs.first_school_name, fs.first_school_code,
       (SELECT max(d.last_seen_at) FROM user_device_sessions d WHERE d.user_id=u.id) AS last_activity_at
  FROM page u
  LEFT JOIN LATERAL (SELECT coalesce(array_agg(DISTINCT r.label ORDER BY r.label), '{{}}') platform_roles
         FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id AND r.level='PLATFORM'
        WHERE a.user_id=u.id AND a.school_id IS NULL AND a.active) pr ON true
  LEFT JOIN LATERAL (SELECT coalesce(array_agg(DISTINCT r.label ORDER BY r.label), '{{}}') school_roles
         FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id JOIN school_memberships m ON m.id=a.membership_id AND m.active
        WHERE a.user_id=u.id AND a.active) sr ON true
  LEFT JOIN LATERAL (SELECT count(*) schools_count FROM school_memberships m WHERE m.user_id=u.id AND m.active) sc ON true
  LEFT JOIN LATERAL (SELECT s.id first_school_id, s.name first_school_name, s.code first_school_code
         FROM school_memberships m JOIN schools s ON s.id=m.school_id WHERE m.user_id=u.id AND m.active
        ORDER BY lower(s.name), s.id LIMIT 1) fs ON true
 ORDER BY lower(u.full_name), u.id
"""


def list_identities(c, *, q: str | None, scope: str | None, status: str | None, school_id, role: str | None, active_only: bool,
                    cursor: str | None, limit: int) -> dict:
    """One page (keyset on lower(full_name), id) with its total; per-row details are computed for the page only."""
    where, params = _filters(q, scope, status, school_id, role, active_only)
    total = int(c.execute(text("SELECT count(*) FROM users u WHERE " + (" AND ".join(where) or "TRUE")), params).scalar_one())
    page_where = list(where)
    key = decode_cursor(cursor)
    if key:
        page_where.append("(lower(u.full_name), u.id) > (CAST(:k1 AS text), CAST(:kid AS uuid))")
        params |= key
    sql = _PAGE.format(where=" AND ".join(page_where) or "TRUE", platform=_PLATFORM, school=_SCHOOL, suspended=_SUSPENDED,
                       pending=_PENDING)
    rows = [dict(r) for r in c.execute(text(sql), params | {"lim": limit + 1}).mappings()]
    more = len(rows) > limit
    rows = rows[:limit]
    for r in rows:
        r["scope"] = "BOTH" if r["is_platform"] and r["is_school"] else "PLATFORM" if r["is_platform"] else "SCHOOL" if r["is_school"] else "NONE"
        r["platform_roles"] = list(r["platform_roles"] or [])
        r["school_roles"] = list(r["school_roles"] or [])
        r["schools_count"] = int(r["schools_count"] or 0)
    return {"items": rows, "total": total, "has_more": more, "next_cursor": encode_cursor(rows[-1]) if more and rows else None, "limit": limit}


def filter_roles(c) -> list[dict]:
    """Standard roles (platform and school) that can be used as a filter: the custom roles stay searchable by account."""
    return [dict(r) for r in c.execute(text("""SELECT code, label, level FROM rbac_roles
        WHERE kind IN ('PLATFORM_STANDARD','SCHOOL_STANDARD') AND status='ACTIVE' ORDER BY level, lower(label)""")).mappings()]


_DETAIL = ("SELECT u.id, u.full_name, u.email::text AS email, u.active, u.created_at, "
           "coalesce(u.must_change_password,false) must_change_password, "
           "CASE WHEN NOT u.active THEN 'DISABLED' WHEN " + _SUSPENDED + " THEN 'SUSPENDED' WHEN " + _PENDING + " THEN 'PENDING' "
           "ELSE 'ACTIVE' END AS status, "
           "(SELECT max(d.last_seen_at) FROM user_device_sessions d WHERE d.user_id=u.id) last_activity_at "
           "FROM users u WHERE u.id=:u")


def identity_detail(c, user_id, *, can_security: bool) -> dict | None:
    u = c.execute(text(_DETAIL), {"u": str(user_id)}).mappings().first()
    if not u:
        return None
    platform_roles = [dict(r) for r in c.execute(text("""SELECT r.code, r.label, a.valid_from AS since
        FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id AND r.level='PLATFORM'
        WHERE a.user_id=:u AND a.school_id IS NULL AND a.active ORDER BY lower(r.label)"""), {"u": str(user_id)}).mappings()]
    memberships = [dict(r) for r in c.execute(text("""SELECT s.id school_id, s.code, s.name, s.status school_status, m.active,
          m.created_at since,
          coalesce((SELECT array_agg(DISTINCT r.label ORDER BY r.label) FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id
                     WHERE a.membership_id=m.id AND a.active), '{}') roles,
          (SELECT max(d.last_seen_at) FROM user_device_sessions d WHERE d.user_id=m.user_id AND d.school_id=m.school_id) last_activity_at
        FROM school_memberships m JOIN schools s ON s.id=m.school_id
        WHERE m.user_id=:u ORDER BY m.active DESC, lower(s.name)"""), {"u": str(user_id)}).mappings()]
    for m in memberships:
        m["roles"] = list(m["roles"] or [])
    active_memberships = [m for m in memberships if m["active"]]
    scope = ("BOTH" if platform_roles and active_memberships else "PLATFORM" if platform_roles
             else "SCHOOL" if active_memberships else "NONE")
    security = None
    if can_security:   # same information as Équipe plateforme (second-factor status, open sessions), never a secret
        security = dict(c.execute(text("""SELECT
            EXISTS (SELECT 1 FROM user_mfa_factors f WHERE f.user_id=:u AND f.status='ACTIVE') mfa_enrolled,
            (SELECT count(*) FROM user_device_sessions d WHERE d.user_id=:u AND d.revoked_at IS NULL AND d.expires_at>now()) open_sessions"""),
            {"u": str(user_id)}).mappings().one())
    return {**dict(u), "scope": scope, "platform_roles": platform_roles, "memberships": memberships, "security": security}
