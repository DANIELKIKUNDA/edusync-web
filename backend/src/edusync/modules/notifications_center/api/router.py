"""In-app notifications as business objects (N1 certification 2026-10).

* Inboxes: a platform account reads its platform notifications (school_id NULL); a school member reads its own
  notifications of that school. Read/unread, mark all, history with filters and keyset pagination, expiry.
* Campaigns (platform.notifications.system.send): targeting one/many/all active schools, a school role, a
  school member, all platform accounts, a platform role, a platform account. One notification per recipient
  per campaign (unique index), idempotent, audited, internal links only.
* Push subscriptions per device (mock provider for certification; real providers are BLOCKED_EXTERNAL).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from edusync.adapters.postgres_idempotency import PostgresIdempotencyRepository
from edusync.adapters.postgres_repositories import PostgresAuditRepository
from edusync.bootstrap.dependencies import get_services, require_platform_actor, require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.modules.audit.domain.audit import AuditRecord
from edusync.shared.application.context import ActorContext
from edusync.shared.application.idempotency import IdempotentExecutor
from edusync.shared.domain.concurrency import IdempotencyConflict, IdempotencyInProgress
from edusync.shared.infrastructure.push import build_push_provider
from edusync.shared.infrastructure.realtime import inbox_events, publish_inbox_changed

router = APIRouter(tags=["Notifications"])
LINK_RE = re.compile(r"^/[A-Za-z0-9/_?=&.-]*$")
SEND_CAP = "platform.notifications.system.send"
MAX_RECIPIENTS = 50_000


# ------------------------------------------------------------------ helpers

def _inbox(c, user_id: UUID, school_id: UUID | None, status: str | None, severity: str | None, limit: int, cursor_at, cursor_id):
    limit = max(1, min(limit, 100))
    rows = c.execute(text("""SELECT id, category, severity, title, body, link_path, created_at, read_at, expires_at
        FROM notifications WHERE user_id=:u AND school_id IS NOT DISTINCT FROM CAST(:s AS uuid)
          AND (expires_at IS NULL OR expires_at>now())
          AND (CAST(:st AS text) IS NULL OR (:st='unread' AND read_at IS NULL) OR (:st='read' AND read_at IS NOT NULL))
          AND (CAST(:sev AS text) IS NULL OR severity=:sev)
          AND (CAST(:ca AS timestamptz) IS NULL OR (created_at,id)<(:ca,:cid))
        ORDER BY created_at DESC, id DESC LIMIT :lim"""),
        {"u": str(user_id), "s": str(school_id) if school_id else None, "st": status, "sev": severity,
         "ca": cursor_at, "cid": cursor_id, "lim": limit + 1}).mappings().all()
    unread = c.execute(text("""SELECT count(*) FROM notifications WHERE user_id=:u AND school_id IS NOT DISTINCT FROM CAST(:s AS uuid)
        AND read_at IS NULL AND (expires_at IS NULL OR expires_at>now())"""), {"u": str(user_id), "s": str(school_id) if school_id else None}).scalar_one()
    items = [dict(r) for r in rows[:limit]]
    last = items[-1] if len(rows) > limit and items else None
    return {"items": items, "unread": int(unread), "next_cursor": {"at": last["created_at"].isoformat(), "id": str(last["id"])} if last else None}


def _validate_filters(status, severity):
    if status not in (None, "", "all", "unread", "read"):
        raise HTTPException(422, "Filtre de statut invalide")
    if severity not in (None, "", "INFO", "WARNING", "CRITICAL"):
        raise HTTPException(422, "Filtre de gravité invalide")
    return (None if status in (None, "", "all") else status), (severity or None)


def _cursor(cursor_at: str | None, cursor_id: UUID | None):
    if (cursor_at is None) != (cursor_id is None):
        raise HTTPException(422, "Curseur incomplet")
    try:
        return datetime.fromisoformat(cursor_at) if cursor_at else None
    except ValueError as exc:
        raise HTTPException(422, "Curseur invalide") from exc


class PushSubscriptionInput(BaseModel):
    provider: str = Field(pattern="^(MOCK|WEBPUSH|FCM)$")
    endpoint: str = Field(min_length=8, max_length=2000)
    device_label: str | None = Field(default=None, max_length=120)


def _subscribe(c, user_id: UUID, school_id: UUID | None, body: PushSubscriptionInput, settings) -> dict:
    if body.provider != "MOCK" and (settings.push_provider or "disabled").lower() != body.provider.lower():
        raise HTTPException(409, "Ce fournisseur de notifications push n’est pas configuré sur ce serveur")
    h = hashlib.sha256(body.endpoint.encode("utf-8")).hexdigest()  # the endpoint itself (a capability URL) is never stored
    row = c.execute(text("""SELECT id FROM push_subscriptions WHERE user_id=:u AND endpoint_hash=:h AND revoked_at IS NULL"""), {"u": str(user_id), "h": h}).first()
    if row:
        return {"id": str(row[0]), "status": "already_subscribed"}
    sid = c.execute(text("""INSERT INTO push_subscriptions(user_id,school_id,provider,endpoint_hash,device_label)
        VALUES(:u,:s,:p,:h,:l) RETURNING id"""), {"u": str(user_id), "s": str(school_id) if school_id else None, "p": body.provider, "h": h, "l": body.device_label}).scalar_one()
    return {"id": str(sid), "status": "subscribed"}


# ------------------------------------------------------------------ platform inbox

@router.get("/platform/inbox")
def platform_inbox(status: str | None = None, severity: str | None = None, limit: int = 30, cursor_at: str | None = None, cursor_id: UUID | None = None,
                   actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    st, sev = _validate_filters(status, severity)
    with services.platform_db.platform_transaction() as c:
        return _inbox(c, actor.user_id, None, st, sev, limit, _cursor(cursor_at, cursor_id), cursor_id)


@router.post("/platform/inbox/{notification_id}/read")
def platform_inbox_read(notification_id: UUID, actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    with services.platform_db.platform_transaction() as c:
        row = c.execute(text("""UPDATE notifications SET read_at=coalesce(read_at,now()) WHERE id=:id AND user_id=:u AND school_id IS NULL
            RETURNING id, read_at"""), {"id": str(notification_id), "u": str(actor.user_id)}).mappings().first()
    if not row:
        raise HTTPException(404, "Notification introuvable")
    return dict(row)


@router.post("/platform/inbox/read-all")
def platform_inbox_read_all(actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    with services.platform_db.platform_transaction() as c:
        n = c.execute(text("UPDATE notifications SET read_at=now() WHERE user_id=:u AND school_id IS NULL AND read_at IS NULL"), {"u": str(actor.user_id)}).rowcount
    return {"marked_read": n}


@router.post("/platform/inbox/push-subscriptions", status_code=201)
def platform_push_subscribe(body: PushSubscriptionInput, actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    with services.platform_db.platform_transaction() as c:
        return _subscribe(c, actor.user_id, None, body, services.settings)


@router.get("/platform/inbox/push-subscriptions")
def platform_push_list(actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    with services.platform_db.platform_transaction() as c:
        rows = c.execute(text("""SELECT id, provider, device_label, created_at, last_used_at FROM push_subscriptions
            WHERE user_id=:u AND school_id IS NULL AND revoked_at IS NULL ORDER BY created_at DESC"""), {"u": str(actor.user_id)}).mappings().all()
    return {"items": [dict(r) for r in rows]}


@router.post("/platform/inbox/push-subscriptions/{subscription_id}/revoke")
def platform_push_revoke(subscription_id: UUID, actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    with services.platform_db.platform_transaction() as c:
        n = c.execute(text("""UPDATE push_subscriptions SET revoked_at=now(), revoked_reason='USER_UNSUBSCRIBED'
            WHERE id=:id AND user_id=:u AND revoked_at IS NULL"""), {"id": str(subscription_id), "u": str(actor.user_id)}).rowcount
    if not n:
        raise HTTPException(404, "Abonnement introuvable")
    return {"id": str(subscription_id), "revoked": True}


# ------------------------------------------------------------------ school inbox

def _need(actor: ActorContext, cap: str):
    try:
        actor.require(cap)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


@router.get("/notifications/inbox")
def school_inbox(status: str | None = None, severity: str | None = None, limit: int = 30, cursor_at: str | None = None, cursor_id: UUID | None = None,
                 actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, "notifications.internal.read")
    st, sev = _validate_filters(status, severity)
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        return _inbox(c, actor.user_id, actor.school_id, st, sev, limit, _cursor(cursor_at, cursor_id), cursor_id)


@router.post("/notifications/inbox/read-all")
def school_inbox_read_all(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, "notifications.internal.dismiss")
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        n = c.execute(text("UPDATE notifications SET read_at=now() WHERE user_id=:u AND school_id=:s AND read_at IS NULL"),
                      {"u": str(actor.user_id), "s": str(actor.school_id)}).rowcount
    return {"marked_read": n}


@router.post("/notifications/push-subscriptions", status_code=201)
def school_push_subscribe(body: PushSubscriptionInput, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, "notifications.internal.read")
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        return _subscribe(c, actor.user_id, actor.school_id, body, services.settings)


@router.post("/notifications/push-subscriptions/{subscription_id}/revoke")
def school_push_revoke(subscription_id: UUID, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        n = c.execute(text("""UPDATE push_subscriptions SET revoked_at=now(), revoked_reason='USER_UNSUBSCRIBED'
            WHERE id=:id AND user_id=:u AND school_id=:s AND revoked_at IS NULL"""),
            {"id": str(subscription_id), "u": str(actor.user_id), "s": str(actor.school_id)}).rowcount
    if not n:
        raise HTTPException(404, "Abonnement introuvable")
    return {"id": str(subscription_id), "revoked": True}


# ------------------------------------------------------------------ campaigns

class Target(BaseModel):
    type: str = Field(pattern="^(ALL_ACTIVE_SCHOOLS|SCHOOLS|SCHOOL_ROLE|SCHOOL_USER|PLATFORM_ALL|PLATFORM_ROLE|PLATFORM_USER)$")
    school_ids: list[UUID] = Field(default_factory=list, max_length=500)
    role_code: str | None = Field(default=None, max_length=96)
    user_id: UUID | None = None


class CampaignInput(BaseModel):
    title: str = Field(min_length=2, max_length=180)
    body: str = Field(min_length=2, max_length=2000)
    severity: str = Field(default="INFO", pattern="^(INFO|WARNING|CRITICAL)$")
    target: Target
    link_path: str | None = Field(default=None, max_length=200)
    expires_at: datetime | None = None


def _recipients(c, t: Target) -> list[dict]:
    """(user_id, school_id|None) pairs. Only active accounts, active memberships of ACTIVE schools, and platform
    accounts with an active platform role and not suspended."""
    platform_base = """SELECT DISTINCT a.user_id, NULL::uuid AS school_id FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id
        JOIN users u ON u.id=a.user_id LEFT JOIN platform_account_status ps ON ps.user_id=a.user_id
        WHERE a.school_id IS NULL AND a.active AND r.level='PLATFORM' AND r.status='ACTIVE' AND u.active
          AND a.valid_from<=now() AND (a.valid_until IS NULL OR a.valid_until>now()) AND coalesce(ps.status,'ACTIVE')='ACTIVE'"""
    school_base = """SELECT DISTINCT m.user_id, m.school_id FROM school_memberships m JOIN schools s ON s.id=m.school_id JOIN users u ON u.id=m.user_id
        WHERE m.active AND u.active AND s.status='ACTIVE'"""
    if t.type == "PLATFORM_ALL":
        rows = c.execute(text(platform_base))
    elif t.type == "PLATFORM_ROLE":
        if not c.execute(text("SELECT 1 FROM rbac_roles WHERE code=:c AND level='PLATFORM' AND status='ACTIVE'"), {"c": t.role_code}).first():
            raise HTTPException(422, "Rôle plateforme actif introuvable")
        rows = c.execute(text(platform_base + " AND r.code=:c"), {"c": t.role_code})
    elif t.type == "PLATFORM_USER":
        rows = c.execute(text(platform_base + " AND a.user_id=:u"), {"u": str(t.user_id)})
    elif t.type == "ALL_ACTIVE_SCHOOLS":
        rows = c.execute(text(school_base))
    elif t.type == "SCHOOLS":
        if not t.school_ids:
            raise HTTPException(422, "Choisissez au moins une école")
        active = {r[0] for r in c.execute(text("SELECT id FROM schools WHERE id = ANY(:ids) AND status='ACTIVE'"), {"ids": [str(x) for x in t.school_ids]})}
        if len(active) != len(set(t.school_ids)):
            raise HTTPException(422, "Toutes les écoles ciblées doivent exister et être actives")
        rows = c.execute(text(school_base + " AND m.school_id = ANY(:ids)"), {"ids": [str(x) for x in t.school_ids]})
    elif t.type == "SCHOOL_ROLE":
        if not c.execute(text("SELECT 1 FROM rbac_roles WHERE code=:c AND level='SCHOOL' AND status='ACTIVE'"), {"c": t.role_code}).first():
            raise HTTPException(422, "Rôle école actif introuvable")
        rows = c.execute(text(school_base + """ AND EXISTS (SELECT 1 FROM rbac_assignments a JOIN rbac_roles r ON r.id=a.role_id
            WHERE a.membership_id=m.id AND a.active AND r.code=:c AND r.status='ACTIVE')
            AND (cardinality(CAST(:ids AS uuid[]))=0 OR m.school_id = ANY(CAST(:ids AS uuid[])))"""), {"c": t.role_code, "ids": [str(x) for x in t.school_ids]})
    else:  # SCHOOL_USER
        if len(t.school_ids) != 1 or not t.user_id:
            raise HTTPException(422, "Indiquez l’école et le membre ciblés")
        rows = c.execute(text(school_base + " AND m.school_id=:s AND m.user_id=:u"), {"s": str(t.school_ids[0]), "u": str(t.user_id)})
    out = [dict(r._mapping) for r in rows]
    if not out:
        raise HTTPException(422, "Aucun destinataire actif ne correspond à cette cible")
    if len(out) > MAX_RECIPIENTS:
        raise HTTPException(422, f"Trop de destinataires ({len(out)}) : {MAX_RECIPIENTS} au maximum par campagne")
    return out


@router.post("/platform/notification-campaigns", status_code=201)
def create_campaign(body: CampaignInput, response: Response, idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                    actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require(SEND_CAP)
    key = (idempotency_key or "").strip()
    if not key or len(key) > 180:
        raise HTTPException(400, "En-tête Idempotency-Key obligatoire pour cette mutation")
    if body.link_path and (not LINK_RE.match(body.link_path) or body.link_path.startswith("//")):
        raise HTTPException(422, "Lien interne uniquement (chemin relatif commençant par /)")
    if body.expires_at and body.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(422, "La date d’expiration doit être dans le futur")
    t = body.target
    if t.type in ("SCHOOL_ROLE", "PLATFORM_ROLE") and not t.role_code:
        raise HTTPException(422, "Rôle cible obligatoire")
    if t.type == "PLATFORM_USER" and not t.user_id:
        raise HTTPException(422, "Compte cible obligatoire")
    request_actor = replace(actor, correlation_id=uuid4(), idempotency_key=key)
    pushed: list[dict] = []
    notified: list[tuple[str, str | None]] = []
    try:
        with services.platform_db.platform_transaction() as c:
            idem = IdempotentExecutor(PostgresIdempotencyRepository(c))

            def action():
                recipients = _recipients(c, t)
                cid = uuid4()
                legacy_school = t.school_ids[0] if t.type == "SCHOOL_USER" else None
                c.execute(text("""INSERT INTO platform_system_notifications(id,title,body,severity,target_scope,target_school_id,created_by,recipient_count,target_json,link_path,expires_at)
                    VALUES(:id,:t,:b,:sev,:scope,:sid,:u,:n,CAST(:tj AS jsonb),:link,:exp)"""),
                    {"id": cid, "t": body.title.strip(), "b": body.body.strip(), "sev": body.severity, "scope": t.type, "sid": legacy_school,
                     "u": str(actor.user_id), "n": len(recipients), "tj": t.model_dump_json(), "link": body.link_path, "exp": body.expires_at})
                c.execute(text("""INSERT INTO notifications(school_id,user_id,category,severity,title,body,campaign_id,link_path,expires_at)
                    SELECT CAST(x->>'school_id' AS uuid), CAST(x->>'user_id' AS uuid), :cat, :sev, :t, :b, :cid, :link, :exp
                    FROM jsonb_array_elements(CAST(:rec AS jsonb)) x ON CONFLICT DO NOTHING"""),
                    {"cat": f"SYSTEM_{body.severity}", "sev": body.severity, "t": body.title.strip(), "b": body.body.strip(), "cid": cid,
                     "link": body.link_path, "exp": body.expires_at,
                     "rec": json.dumps([{"user_id": str(r["user_id"]), "school_id": str(r["school_id"]) if r["school_id"] else None} for r in recipients])})
                PostgresAuditRepository(c).append(AuditRecord(
                    action="PLATFORM_NOTIFICATION_CAMPAIGN_SENT", entity_type="PlatformSystemNotification", entity_id=cid, actor_user_id=actor.user_id,
                    school_id=None, source=actor.source, correlation_id=request_actor.correlation_id, idempotency_key=key,
                    new_data={"target": t.model_dump(mode="json"), "severity": body.severity, "recipient_count": len(recipients), "title": body.title.strip(),
                              "link_path": body.link_path, "expires_at": body.expires_at.isoformat() if body.expires_at else None}))
                subs = c.execute(text("""SELECT p.id, p.user_id FROM push_subscriptions p WHERE p.revoked_at IS NULL
                    AND (p.user_id, coalesce(p.school_id,'00000000-0000-0000-0000-000000000000'::uuid)) IN
                    (SELECT n.user_id, coalesce(n.school_id,'00000000-0000-0000-0000-000000000000'::uuid) FROM notifications n WHERE n.campaign_id=:cid)"""),
                    {"cid": cid}).mappings().all()
                pushed.extend(dict(s) for s in subs)
                notified.extend((str(r["user_id"]), str(r["school_id"]) if r["school_id"] else None) for r in recipients)
                return 201, {"id": str(cid), "recipient_count": len(recipients), "target": t.type, "severity": body.severity}

            result = idem.execute(scope_key="platform", idempotency_key=key, operation="PLATFORM_NOTIFICATION_CAMPAIGN",
                                  payload=body.model_dump(mode="json"), school_id=None, actor_user_id=str(actor.user_id), action=action)
    except (IdempotencyConflict, IdempotencyInProgress) as exc:
        raise HTTPException(409, str(exc)) from exc
    response.status_code = result.status_code
    response.headers["Idempotent-Replayed"] = "true" if result.replayed else "false"
    if notified and not result.replayed:
        publish_inbox_changed(services.settings.redis_url, notified)  # real-time: bells update immediately
    if pushed and not result.replayed:
        provider = build_push_provider(services.settings)
        sent = sum(provider.send(s, {"title": body.title.strip(), "severity": body.severity, "link": body.link_path}).accepted for s in pushed)
        result.body["push"] = {"provider": provider.name, "devices": len(pushed), "accepted": sent}
    return result.body


@router.get("/platform/notification-campaigns")
def list_campaigns(limit: int = 30, offset: int = 0, actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    actor.require(SEND_CAP)
    limit, offset = max(1, min(limit, 100)), max(0, offset)
    with services.platform_db.platform_transaction() as c:
        rows = c.execute(text("""SELECT p.id, p.title, p.severity, p.target_scope, p.target_json, p.link_path, p.expires_at, p.created_at,
              p.recipient_count, u.full_name AS author, s.code AS target_school_code,
              (SELECT count(*) FROM notifications n WHERE n.campaign_id=p.id AND n.read_at IS NOT NULL) AS read_count
            FROM platform_system_notifications p LEFT JOIN users u ON u.id=p.created_by LEFT JOIN schools s ON s.id=p.target_school_id
            ORDER BY p.created_at DESC, p.id DESC LIMIT :lim OFFSET :off"""), {"lim": limit + 1, "off": offset}).mappings().all()
    return {"items": [dict(r) for r in rows[:limit]], "has_more": len(rows) > limit, "offset": offset, "limit": limit}


# ------------------------------------------------------------------ real-time streams (SSE)

_SSE_HEADERS = {"Cache-Control": "no-store", "X-Accel-Buffering": "no", "Connection": "keep-alive"}


@router.get("/platform/inbox/stream")
async def platform_inbox_stream(request: Request, actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    """Server-Sent Events: "your inbox changed" signals for this platform account (no content)."""
    return StreamingResponse(inbox_events(services.settings.redis_url, actor.user_id, None, request.is_disconnected),
                             media_type="text/event-stream", headers=_SSE_HEADERS)


@router.get("/notifications/stream")
async def school_inbox_stream(request: Request, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, "notifications.internal.read")
    return StreamingResponse(inbox_events(services.settings.redis_url, actor.user_id, actor.school_id, request.is_disconnected),
                             media_type="text/event-stream", headers=_SSE_HEADERS)
