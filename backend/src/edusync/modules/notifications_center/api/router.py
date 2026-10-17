"""In-app notifications as business objects (N1 certification 2026-10).

* Inboxes: a platform account reads its platform notifications (school_id NULL); a school member reads its own
  notifications of that school. Read/unread, mark all, history with filters and keyset pagination, expiry.
* Campaigns (platform.notifications.system.send): targeting one/many/all active schools, a school role, a
  school member, all platform accounts, a platform role, a platform account. One notification per recipient
  per campaign (unique index), idempotent, audited, internal links only.
* Push devices (Firebase Cloud Messaging): registration token encrypted at rest, one row per device, revocable one by
  one; a token re-registered by another account or school is revoked for the previous one (no cross-account push).
  Push messages go through the communications outbox / worker like every external message (never sent in a request).
"""
from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from edusync.adapters.postgres_idempotency import PostgresIdempotencyRepository
from edusync.adapters.postgres_repositories import PostgresAuditRepository
from edusync.bootstrap.dependencies import get_services, require_platform_actor, require_recent_mfa, require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.modules.audit.domain.audit import AuditRecord
from edusync.shared.application.context import ActorContext
from edusync.shared.application.idempotency import IdempotentExecutor
from edusync.shared.domain.concurrency import IdempotencyConflict, IdempotencyInProgress
from edusync.bootstrap.settings import is_protected_env
from edusync.modules.communications.application.messaging import Recipient, request_message
from edusync.shared.messaging.sealing import PUSH_TOKEN, cipher, token_hash
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
    endpoint: str = Field(min_length=8, max_length=4096)       # FCM registration token (never logged, encrypted at rest)
    device_label: str | None = Field(default=None, max_length=120)
    device_id: UUID | None = None
    platform: str | None = Field(default=None, max_length=32)
    browser: str | None = Field(default=None, max_length=48)


def _push_accepts(settings, provider: str) -> bool:
    configured = (settings.push_provider or "disabled").lower()
    if provider == "FCM":
        return configured == "fcm" or (configured in {"fake", "mock"} and not is_protected_env(settings.env))
    if provider == "MOCK":
        return not is_protected_env(settings.env)
    return False


def _subscribe(c, user_id: UUID, school_id: UUID | None, body: PushSubscriptionInput, settings, membership_id: UUID | None = None) -> dict:
    if not _push_accepts(settings, body.provider):
        raise HTTPException(409, "Ce fournisseur de notifications push n’est pas configuré sur ce serveur")
    h = token_hash(body.endpoint)  # uniqueness / lookup only; the token itself is stored encrypted
    row = c.execute(text("""SELECT id FROM push_subscriptions WHERE user_id=:u AND endpoint_hash=:h AND revoked_at IS NULL
        AND school_id IS NOT DISTINCT FROM CAST(:s AS uuid)"""), {"u": str(user_id), "h": h, "s": str(school_id) if school_id else None}).first()
    if row:
        c.execute(text("UPDATE push_subscriptions SET last_used_at=now() WHERE id=:id"), {"id": str(row[0])})
        return {"id": str(row[0]), "status": "already_subscribed"}
    sid = uuid4()
    sealed = cipher(settings, PUSH_TOKEN).encrypt(body.endpoint, owner=str(sid))
    c.execute(text("""INSERT INTO push_subscriptions(id,user_id,school_id,membership_id,provider,endpoint_hash,token_ciphertext,device_label,device_id,platform,browser)
        VALUES(:id,:u,:s,:m,:p,:h,:tok,:l,:d,:pf,:br)"""),
        {"id": str(sid), "u": str(user_id), "s": str(school_id) if school_id else None, "m": str(membership_id) if membership_id else None,
         "p": body.provider, "h": h, "tok": sealed, "l": body.device_label, "d": str(body.device_id) if body.device_id else None,
         "pf": body.platform, "br": body.browser})
    return {"id": str(sid), "status": "subscribed"}


def _revoke_token_elsewhere(platform_conn, token_h: str, keep_user: UUID, keep_school: UUID | None) -> int:
    """The same browser token now belongs to another account / school: the previous registration stops receiving."""
    return platform_conn.execute(text("""UPDATE push_subscriptions SET revoked_at=now(), revoked_reason='TOKEN_REASSIGNED'
        WHERE endpoint_hash=:h AND revoked_at IS NULL AND (user_id<>:u OR school_id IS DISTINCT FROM CAST(:s AS uuid))"""),
        {"h": token_h, "u": str(keep_user), "s": str(keep_school) if keep_school else None}).rowcount


def _push_config(settings) -> dict:
    """Public configuration for the browser: Firebase web app config + VAPID public key (never the service account)."""
    kind = (settings.push_provider or "disabled").lower()
    try:
        web = json.loads(settings.fcm_web_config_json) if settings.fcm_web_config_json else None
    except json.JSONDecodeError:
        web = None
    public_keys = {"apiKey", "authDomain", "projectId", "storageBucket", "messagingSenderId", "appId", "measurementId"}
    return {"provider": "fcm" if kind == "fcm" else ("fake" if kind in {"fake", "mock"} and not is_protected_env(settings.env) else "disabled"),
            "web_config": {k: v for k, v in (web or {}).items() if k in public_keys} or None,
            "vapid_public_key": settings.fcm_vapid_public_key or None}


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


@router.get("/platform/inbox/push/config")
def platform_push_config(actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    return _push_config(services.settings)


@router.post("/platform/inbox/push-subscriptions", status_code=201)
def platform_push_subscribe(body: PushSubscriptionInput, actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    with services.platform_db.platform_transaction() as c:
        out = _subscribe(c, actor.user_id, None, body, services.settings)
        _revoke_token_elsewhere(c, token_hash(body.endpoint), actor.user_id, None)
        return out


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


@router.get("/notifications/push/config")
def school_push_config(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, "notifications.internal.read")
    return _push_config(services.settings)


@router.get("/notifications/push-subscriptions")
def school_push_list(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, "notifications.internal.read")
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        rows = c.execute(text("""SELECT id, provider, device_label, platform, browser, created_at, last_used_at, last_error_code FROM push_subscriptions
            WHERE user_id=:u AND school_id=:s AND revoked_at IS NULL ORDER BY created_at DESC"""), {"u": str(actor.user_id), "s": str(actor.school_id)}).mappings().all()
    return {"items": [dict(r) for r in rows]}


@router.post("/notifications/push-subscriptions", status_code=201)
def school_push_subscribe(body: PushSubscriptionInput, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, "notifications.internal.read")
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        out = _subscribe(c, actor.user_id, actor.school_id, body, services.settings, actor.membership_id)
    with services.platform_db.platform_transaction() as pc:
        _revoke_token_elsewhere(pc, token_hash(body.endpoint), actor.user_id, actor.school_id)
    return out


@router.post("/notifications/push-test")
def school_push_test(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """Test notification to the caller's own devices of this school, through the normal outbox / worker path."""
    _need(actor, "notifications.internal.read")
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        n = c.execute(text("SELECT count(*) FROM push_subscriptions WHERE user_id=:u AND school_id=:s AND revoked_at IS NULL"),
                      {"u": str(actor.user_id), "s": str(actor.school_id)}).scalar_one()
        if not n:
            raise HTTPException(409, "Activez d’abord les notifications sur cet appareil")
        out = request_message(c, school_id=actor.school_id, kind="PUSH_TEST", channels=["PUSH"], subject="Notifications EduSync activées",
                              body="Cet appareil recevra les notifications de votre école.",
                              recipients=[Recipient("USER", actor.user_id, None, user_id=actor.user_id)],
                              idempotency_key=f"push-test:{uuid4()}", created_by=actor.user_id, link_path="/")
    return {"message_id": out["id"], "devices": n, "status": "QUEUED"}


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
    if t.type == "ALL_ACTIVE_SCHOOLS":
        require_recent_mfa(services, actor)  # step-up: message to every school
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
                subs = c.execute(text("""SELECT DISTINCT p.user_id, p.school_id FROM push_subscriptions p WHERE p.revoked_at IS NULL
                    AND p.token_ciphertext IS NOT NULL
                    AND (p.user_id, coalesce(p.school_id,'00000000-0000-0000-0000-000000000000'::uuid)) IN
                    (SELECT n.user_id, coalesce(n.school_id,'00000000-0000-0000-0000-000000000000'::uuid) FROM notifications n WHERE n.campaign_id=:cid)"""),
                    {"cid": cid}).mappings().all()
                if subs:
                    # Push goes through the outbox: one platform message, one recipient per (account, school); the worker
                    # only targets that account's devices of that school.
                    request_message(c, school_id=None, kind="PLATFORM", channels=["PUSH"], subject=body.title.strip()[:120],
                                    body=body.body.strip()[:240], link_path=body.link_path, idempotency_key=f"campaign-push:{cid}", created_by=actor.user_id,
                                    recipients=[Recipient("USER", uuid5(NAMESPACE_URL, f"{s['user_id']}:{s['school_id']}"), None, user_id=s["user_id"],
                                                          target_school_id=s["school_id"]) for s in subs])
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
        result.body["push"] = {"status": "QUEUED", "recipients_with_devices": len(pushed)}
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
