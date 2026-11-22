"""Modules of a school — reads and changes on saas_entitlements (platform role: the tenant role cannot read them).

One ACTIVE row per (school, module) is guaranteed by the unique index uq_saas_active_entitlement. A withdrawal never
deletes: the row becomes REVOKED with its end date, so the history of a school's modules stays complete.
"""
from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import text

from edusync.modules.school_modules.domain.catalog import V1_MODULES, V1_REASON_AT_CREATION


def active_codes(conn, school_id: UUID) -> set[str]:
    rows = conn.execute(text("""SELECT module_code FROM saas_entitlements
        WHERE school_id=:s AND status='ACTIVE' AND starts_at<=now() AND (ends_at IS NULL OR ends_at>now())"""),
        {"s": str(school_id)})
    return {r[0] for r in rows}


def has_module(conn, school_id: UUID, code: str) -> bool:
    return conn.execute(text("""SELECT 1 FROM saas_entitlements WHERE school_id=:s AND module_code=:m AND status='ACTIVE'
        AND starts_at<=now() AND (ends_at IS NULL OR ends_at>now()) LIMIT 1"""), {"s": str(school_id), "m": code}).first() is not None


def catalogue(conn) -> dict[str, dict]:
    rows = conn.execute(text("SELECT code,label,description,status,dependencies FROM saas_modules ORDER BY code")).mappings()
    out = {}
    for r in rows:
        deps = r["dependencies"]
        out[r["code"]] = {**dict(r), "dependencies": deps if isinstance(deps, list) else json.loads(deps or "[]")}
    return out


def grant_v1_modules(conn, school_id: UUID, *, reason: str = V1_REASON_AT_CREATION) -> int:
    """Give a school the eight V1 modules it lacks (new school, or repair). Returns how many were added."""
    added = 0
    for code in V1_MODULES:
        # explicit types: the same parameter feeds the SELECT list and the WHERE (else « types incohérents » for $2)
        added += conn.execute(text("""INSERT INTO saas_entitlements(school_id,module_code,source,status,reason)
            SELECT CAST(:s AS uuid),CAST(:m AS varchar),'MANUAL','ACTIVE',CAST(:r AS text) WHERE NOT EXISTS
              (SELECT 1 FROM saas_entitlements WHERE school_id=CAST(:s AS uuid) AND module_code=CAST(:m AS varchar) AND status='ACTIVE')"""),
            {"s": str(school_id), "m": code, "r": reason}).rowcount
    return added


def school_modules(conn, school_id: UUID) -> list[dict]:
    """Every catalogue module with its state for this school (current row first, then the latest history)."""
    cat = catalogue(conn)
    rows = conn.execute(text("""SELECT DISTINCT ON (module_code) id,module_code,source,status,starts_at,ends_at,reason,subscription_id,updated_at
        FROM saas_entitlements WHERE school_id=:s
        ORDER BY module_code,(status='ACTIVE') DESC,updated_at DESC"""), {"s": str(school_id)}).mappings().all()
    current = {r["module_code"]: r for r in rows}
    out = []
    for code, m in cat.items():
        if m["status"] == "RETIRED":
            continue
        e = current.get(code)
        active = bool(e and e["status"] == "ACTIVE")
        out.append({"code": code, "label": m["label"], "description": m["description"], "catalogue_status": m["status"],
                    "dependencies": m["dependencies"], "active": active,
                    "source": e["source"] if e else None, "entitlement_status": e["status"] if e else None,
                    "since": (e["starts_at"].isoformat() if e and e["starts_at"] else None),
                    "until": (e["ends_at"].isoformat() if e and e["ends_at"] else None),
                    "reason": e["reason"] if e else None, "through_subscription": bool(e and e["subscription_id"])})
    return out


def activate(conn, school_id: UUID, code: str, reason: str) -> dict:
    row = conn.execute(text("""INSERT INTO saas_entitlements(school_id,module_code,source,status,reason)
        VALUES(:s,:m,'MANUAL','ACTIVE',:r) RETURNING id,module_code,source,status,starts_at"""),
        {"s": str(school_id), "m": code, "r": reason}).mappings().one()
    return {k: (v.isoformat() if hasattr(v, "isoformat") else str(v) if isinstance(v, UUID) else v) for k, v in dict(row).items()}


def withdraw(conn, school_id: UUID, code: str, reason: str) -> dict:
    row = conn.execute(text("""UPDATE saas_entitlements SET status='REVOKED',
            ends_at=greatest(clock_timestamp(), starts_at + interval '1 millisecond'),
            reason=:r, version=version+1, updated_at=now()
        WHERE school_id=:s AND module_code=:m AND status='ACTIVE' RETURNING id,module_code,status,ends_at"""),
        {"s": str(school_id), "m": code, "r": reason}).mappings().first()
    if row is None:
        raise LookupError("Module non actif")
    return {k: (v.isoformat() if hasattr(v, "isoformat") else str(v) if isinstance(v, UUID) else v) for k, v in dict(row).items()}
