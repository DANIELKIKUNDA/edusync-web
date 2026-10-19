"""Plateforme EduSync — audit log: search, filters, detail (before/after), CSV export (N1 certification 2026-10,
Journal d'audit lot 2026-10).

The audit trail is append-only (trigger trg_audit_no_update; UPDATE/DELETE revoked from the platform role): this module
only reads. Reading requires platform.audit.read; exporting requires platform.audit.export and is itself audited (once,
never re-audited). Quick categories are derived from the stored data only: failures (result <> SUCCESS), security
(events recorded on entity_type UserSecurity), platform (school_id NULL), schools (school_id NOT NULL).
Values of sensitive keys are masked at rendering (defence in depth: the writers already never store secrets).
No retention policy is defined for the audit trail: nothing is purged.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import text

from edusync.adapters.postgres_repositories import PostgresAuditRepository
from edusync.bootstrap.dependencies import get_services, require_platform_actor
from edusync.bootstrap.services import AppServices
from edusync.modules.audit.domain.audit import AuditRecord
from edusync.shared.application.context import ActorContext

router = APIRouter(tags=["Plateforme EduSync — audit"])
EXPORT_MAX_ROWS = 10_000
EXPORT_MAX_DAYS = 92

_FILTER_SQL = """
  FROM audit_events a LEFT JOIN schools s ON s.id=a.school_id LEFT JOIN users u ON u.id=a.actor_user_id
 WHERE (CAST(:action AS text) IS NULL OR a.action=:action)
   AND (CAST(:school AS text) IS NULL OR s.code=upper(:school) OR CAST(a.school_id AS text)=:school)
   AND (CAST(:scope AS text) IS NULL OR (:scope='PLATFORM' AND a.school_id IS NULL) OR (:scope='SCHOOL' AND a.school_id IS NOT NULL))
   AND (CAST(:actor AS text) IS NULL OR u.full_name ILIKE '%'||:actor||'%' OR u.email::text ILIKE '%'||:actor||'%')
   AND (CAST(:result AS text) IS NULL OR a.result=:result)
   AND (CAST(:dfrom AS timestamptz) IS NULL OR a.occurred_at>=:dfrom)
   AND (CAST(:dto AS timestamptz) IS NULL OR a.occurred_at<:dto)
   AND (CAST(:corr AS uuid) IS NULL OR a.correlation_id=:corr)
   AND (CAST(:entity AS uuid) IS NULL OR a.entity_id=:entity)
   AND (CAST(:q AS text) IS NULL
        OR (CAST(:quuid AS uuid) IS NOT NULL AND (a.entity_id=CAST(:quuid AS uuid) OR a.correlation_id=CAST(:quuid AS uuid) OR a.id=CAST(:quuid AS uuid)))
        OR (CAST(:quuid AS uuid) IS NULL AND (
             edusync_search_key(a.action || ' ' || a.entity_type || ' ' || coalesce(a.reason, '')) LIKE '%' || edusync_search_key(CAST(:q AS text)) || '%'
             OR a.actor_user_id IN (SELECT su.id FROM users su
                                     WHERE edusync_search_key(su.full_name || ' ' || su.email::text) LIKE '%' || edusync_search_key(CAST(:q AS text)) || '%'))))
   AND (CAST(:cat AS text) IS NULL OR (:cat='FAILURES' AND a.result<>'SUCCESS') OR (:cat='SECURITY' AND a.entity_type='UserSecurity')
        OR (:cat='PLATFORM' AND a.school_id IS NULL) OR (:cat='SCHOOLS' AND a.school_id IS NOT NULL))
"""
CATEGORIES = ("FAILURES", "SECURITY", "PLATFORM", "SCHOOLS")
SENSITIVE = re.compile(r"(pass(word)?|secret|token|otp|totp|cookie|api[_-]?key|private[_-]?key|recovery[_-]?codes?$|qr|signature)", re.I)


def redact(value):
    """Masks the value of any sensitive key (numbers and booleans are kept: counts such as recovery_codes: 10)."""
    if isinstance(value, dict):
        return {k: ("[masqué]" if SENSITIVE.search(k) and not isinstance(v, (int, float, bool)) and v is not None else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value



def _date(value: str | None, *, end: bool = False):
    if not value:
        return None
    try:
        d = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(422, "Date invalide (format AAAA-MM-JJ)") from exc
    return d + timedelta(days=1) if end and len(value) == 10 else d


def _uuid_or_none(q: str | None) -> str | None:
    """A pasted identifier (event, object, correlation) is matched exactly through the indexes; anything else is text."""
    try:
        return str(UUID((q or "").strip())) if q and len(q.strip()) == 36 else None
    except ValueError:
        return None


def _filters(action, school, scope, actor, result, date_from, date_to, correlation_id, entity_id, q, category=None) -> dict:
    if category not in (None, "") and category not in CATEGORIES:
        raise HTTPException(422, "Catégorie invalide")
    if scope not in (None, "", "PLATFORM", "SCHOOL"):
        raise HTTPException(422, "Portée invalide")
    if result not in (None, "", "SUCCESS", "REJECTED", "FAILED"):
        raise HTTPException(422, "Résultat invalide")
    return {"action": (action or "").strip().upper() or None, "school": (school or "").strip() or None, "scope": scope or None,
            "actor": (actor or "").strip() or None, "result": result or None, "dfrom": _date(date_from), "dto": _date(date_to, end=True),
            "corr": correlation_id, "entity": entity_id, "q": (q or "").strip() or None, "cat": category or None, "quuid": _uuid_or_none(q)}


@router.get("")
def audit_log(action: str | None = Query(None, max_length=96), school: str | None = Query(None, max_length=64),
              scope: str | None = None, actor: str | None = Query(None, max_length=120), result: str | None = None,
              date_from: str | None = None, date_to: str | None = None, correlation_id: UUID | None = None,
              entity_id: UUID | None = None, q: str | None = Query(None, max_length=120), limit: int = 50,
              cursor_at: str | None = None, cursor_id: UUID | None = None, category: str | None = None, sort: str = "newest",
              actor_ctx: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    """One page, server-side (keyset on occurred_at, id), newest first by default; one query for the page (authors and
    schools joined, no query per row)."""
    actor_ctx.require("platform.audit.read")
    limit = max(1, min(limit, 100))
    if (cursor_at is None) != (cursor_id is None):
        raise HTTPException(422, "Curseur incomplet")
    if sort not in ("newest", "oldest"):
        raise HTTPException(422, "Tri invalide")
    params = _filters(action, school, scope, actor, result, date_from, date_to, correlation_id, entity_id, q, category)
    params.update({"ca": _date(cursor_at), "cid": cursor_id, "lim": limit + 1})
    keyset, order = ("<", "DESC") if sort == "newest" else (">", "ASC")
    with services.platform_db.platform_transaction() as c:
        rows = c.execute(text("""SELECT a.id,a.occurred_at,a.school_id,s.code school_code,s.name school_name,a.actor_user_id,u.full_name actor,
              a.action,a.entity_type,a.entity_id,a.source,a.result,a.reason,a.correlation_id,(a.old_json IS NOT NULL OR a.new_json IS NOT NULL) has_changes
            """ + _FILTER_SQL + " AND (CAST(:ca AS timestamptz) IS NULL OR (a.occurred_at,a.id)" + keyset + """(:ca,:cid))
            ORDER BY a.occurred_at """ + order + ",a.id " + order + " LIMIT :lim"), params).mappings().all()
        actions = [r[0] for r in c.execute(text("SELECT DISTINCT action FROM audit_events ORDER BY 1 LIMIT 500"))]
    more = len(rows) > limit
    items = [dict(x) for x in rows[:limit]]
    last = items[-1] if items else None
    return {"items": items, "has_more": more, "actions": actions,
            "next_cursor": ({"at": last["occurred_at"].isoformat(), "id": str(last["id"])} if more and last else None)}


@router.get("/export.csv")
def audit_export(action: str | None = Query(None, max_length=96), school: str | None = Query(None, max_length=64),
                 scope: str | None = None, actor: str | None = Query(None, max_length=120), result: str | None = None,
                 date_from: str | None = None, date_to: str | None = None, correlation_id: UUID | None = None,
                 entity_id: UUID | None = None, q: str | None = Query(None, max_length=120), category: str | None = None,
                 actor_ctx: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    """CSV export of the whole filtered set (not the displayed page): same filters as the list, produced server-side,
    UTF-8 with BOM, formula-injection safe, bounded (period and rows: existing rules), audited once."""
    actor_ctx.require("platform.audit.export")
    params = _filters(action, school, scope, actor, result, date_from, date_to, correlation_id, entity_id, q, category)
    if not params["dfrom"]:
        raise HTTPException(422, "Indiquez une date de début pour exporter")
    end = params["dto"] or datetime.now(params["dfrom"].tzinfo)
    if (end - params["dfrom"]).days > EXPORT_MAX_DAYS:
        raise HTTPException(422, f"Période trop longue : {EXPORT_MAX_DAYS} jours au maximum par export")
    params["lim"] = EXPORT_MAX_ROWS + 1
    with services.platform_db.platform_transaction() as c:
        rows = c.execute(text("""SELECT a.occurred_at,coalesce(s.code,'PLATEFORME') school,coalesce(u.full_name,'Système') actor,a.action,
              a.entity_type,a.entity_id,a.result,a.source,coalesce(a.reason,'') reason,a.correlation_id
            """ + _FILTER_SQL + " ORDER BY a.occurred_at DESC,a.id DESC LIMIT :lim"), params).all()
        if len(rows) > EXPORT_MAX_ROWS:
            raise HTTPException(422, f"Plus de {EXPORT_MAX_ROWS} lignes : affinez les filtres")
        PostgresAuditRepository(c).append(AuditRecord(
            action="PLATFORM_AUDIT_EXPORTED", entity_type="AuditLog", entity_id=None, actor_user_id=actor_ctx.user_id, school_id=None,
            source=actor_ctx.source, correlation_id=actor_ctx.correlation_id,
            new_data={"rows": len(rows), "filters": {k: (str(v) if v is not None else None) for k, v in params.items() if k != "lim"}}))
    def safe(v):
        s = "" if v is None else str(v)
        return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s

    def stream():   # written in chunks: the file is never built in one block, nor in the browser
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        buf.write("\ufeff")
        w.writerow(["Date (UTC)", "École", "Auteur", "Action", "Objet", "Identifiant objet", "Résultat", "Origine", "Motif", "Corrélation"])
        for i, r in enumerate(rows, 1):
            w.writerow([safe(x.isoformat() if hasattr(x, "isoformat") else x) for x in r])
            if i % 500 == 0:
                yield buf.getvalue(); buf.seek(0); buf.truncate(0)
        yield buf.getvalue()
    name = f"audit-plateforme-{datetime.now().strftime('%Y%m%d-%H%M')}.csv"
    return StreamingResponse(stream(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "private, no-store"})


@router.get("/{event_id}")
def audit_event(event_id: UUID, actor_ctx: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor_ctx.require("platform.audit.read")
    with services.platform_db.platform_transaction() as c:
        row = c.execute(text("""SELECT a.*, s.code school_code, s.name school_name, u.full_name actor, u.email actor_email
            FROM audit_events a LEFT JOIN schools s ON s.id=a.school_id LEFT JOIN users u ON u.id=a.actor_user_id WHERE a.id=:id"""),
            {"id": str(event_id)}).mappings().first()
        if not row:
            raise HTTPException(404, "Événement introuvable")
        related = []
        if row["correlation_id"]:
            related = [dict(r) for r in c.execute(text("""SELECT id,occurred_at,action,result FROM audit_events
                WHERE correlation_id=:c AND id<>:id ORDER BY occurred_at LIMIT 20"""), {"c": row["correlation_id"], "id": str(event_id)}).mappings()]
        ctx = c.execute(text("""SELECT
              EXISTS (SELECT 1 FROM schools WHERE id=CAST(:sid AS uuid)) school_exists,
              EXISTS (SELECT 1 FROM users WHERE id=CAST(:aid AS uuid)) actor_exists,
              EXISTS (SELECT 1 FROM rbac_assignments x JOIN rbac_roles r ON r.id=x.role_id WHERE x.user_id=CAST(:aid AS uuid)
                      AND x.school_id IS NULL AND x.active AND r.level='PLATFORM') actor_is_member,
              EXISTS (SELECT 1 FROM users WHERE id=CAST(:eid AS uuid)) entity_is_user,
              EXISTS (SELECT 1 FROM schools WHERE id=CAST(:eid AS uuid)) entity_is_school,
              EXISTS (SELECT 1 FROM platform_system_notifications WHERE id=CAST(:eid AS uuid)) entity_is_campaign"""),
            {"sid": str(row["school_id"]) if row["school_id"] else None, "aid": str(row["actor_user_id"]) if row["actor_user_id"] else None,
             "eid": str(row["entity_id"]) if row["entity_id"] else None}).mappings().one()
    out = dict(row)
    out["related"] = related
    out["context"] = dict(ctx)
    out["old_json"], out["new_json"] = redact(out["old_json"]), redact(out["new_json"])
    out.pop("idempotency_key", None)  # internal replay key: not useful to a reader
    return out
