"""Atelier Pro — external messaging supervision and SMS wallets (EXTERNAL_MESSAGING_ARCHITECTURE.md §8).

Strictly technical / commercial: provider states, worker health, volumes and failure rates, SMS wallet of each
school, audited manual credit. The platform never reads the body of a school message here: only metadata
(school, channel, status, quantities, dates, error codes).
"""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from edusync.adapters.postgres_repositories import PostgresAuditRepository
from edusync.bootstrap.dependencies import get_services, require_platform_actor, require_recent_mfa
from edusync.bootstrap.services import AppServices
from edusync.modules.audit.domain.audit import AuditRecord
from edusync.modules.communications.application.messaging import Recipient, request_message
from edusync.modules.communications.application.wallet import wallet_apply
from edusync.shared.application.context import ActorContext
from edusync.shared.messaging.factory import channel_status

router = APIRouter(tags=['platform-messaging'])
READ = 'platform.messaging.read'
CREDIT = 'platform.sms_wallet.credit'


def _need(actor: ActorContext, cap: str) -> None:
    try:
        actor.require(cap)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


def _audit(c, actor: ActorContext, action: str, school_id: UUID, new: dict, *, reason: str | None = None, key: str | None = None) -> None:
    PostgresAuditRepository(c).append(AuditRecord(action=action, entity_type='SchoolSmsWallet', entity_id=school_id, actor_user_id=actor.user_id,
                                                  school_id=None, source=actor.source, reason=reason, new_data=new,
                                                  correlation_id=actor.correlation_id, idempotency_key=key))


@router.get('/status')
def status(actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    _need(actor, READ)
    heartbeat = None
    try:
        import redis
        heartbeat = redis.Redis.from_url(services.settings.redis_url, decode_responses=True, socket_timeout=1,
                                         socket_connect_timeout=1).get('edusync:heartbeat:communications')
    except Exception:  # noqa: BLE001 — health is best effort
        pass
    with services.platform_db.platform_transaction() as c:
        volumes = c.execute(text("""SELECT channel, status, count(*) n FROM communication_deliveries
            WHERE created_at >= now() - interval '24 hours' GROUP BY channel, status ORDER BY channel, status""")).mappings().all()
        due = c.execute(text("""SELECT count(*) FILTER (WHERE status IN ('QUEUED','FAILED_RETRYABLE')) due,
                count(*) FILTER (WHERE status='PROCESSING') processing,
                count(*) FILTER (WHERE status='FAILED_PERMANENT' AND failed_at >= now() - interval '7 days') dead_7d,
                min(created_at) FILTER (WHERE status IN ('QUEUED','FAILED_RETRYABLE')) oldest_due
            FROM communication_deliveries""")).mappings().one()
        undispatched = c.execute(text("""SELECT count(*) FROM outbox_events WHERE event_type='COMMUNICATION_REQUESTED' AND created_at >= now() - interval '7 days'
            AND aggregate_id IN (SELECT id FROM communication_messages WHERE dispatched_at IS NULL AND school_id IS NULL)""")).scalar_one()
        receipts = c.execute(text("SELECT count(*) FROM provider_receipts WHERE applied_at IS NULL")).scalar_one()
    stats: dict[str, dict] = {}
    for v in volumes:
        stats.setdefault(v['channel'], {})[v['status']] = v['n']
    failure_rate = {}
    for ch, st in stats.items():
        total = sum(st.values()) - st.get('CANCELLED', 0)
        failed = st.get('FAILED_PERMANENT', 0)
        failure_rate[ch] = round(failed / total, 4) if total else 0.0
    return {'providers': channel_status(services.settings), 'worker_heartbeat': heartbeat,
            'queue': {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in dict(due).items()},
            'account_messages_waiting_dispatch': undispatched, 'receipts_waiting': receipts,
            'volumes_24h': stats, 'failure_rate_24h': failure_rate}


@router.get('/wallets')
def wallets(actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    _need(actor, READ)
    with services.platform_db.platform_transaction() as c:
        rows = c.execute(text("""SELECT s.id AS school_id, s.name, s.status, coalesce(w.balance,0) balance, coalesce(w.reserved,0) reserved,
                coalesce(cs.sms_enabled,false) sms_enabled, coalesce(cs.sms_low_balance_threshold,50) threshold,
                coalesce((SELECT sum(l.quantity) FROM school_sms_ledger l WHERE l.school_id=s.id AND l.movement_type='CONSUMPTION'
                          AND l.created_at >= now() - interval '30 days'),0) consumed_30d,
                (SELECT max(l.created_at) FROM school_sms_ledger l WHERE l.school_id=s.id AND l.movement_type='TOPUP') last_topup_at
            FROM schools s LEFT JOIN school_sms_wallets w ON w.school_id=s.id LEFT JOIN communication_settings cs ON cs.school_id=s.id
            ORDER BY s.name""")).mappings().all()
    return {'items': [{**dict(r), 'available': r['balance'] - r['reserved'], 'low': r['balance'] - r['reserved'] <= r['threshold']} for r in rows]}


@router.get('/wallets/{school_id}/ledger')
def ledger(school_id: UUID, limit: int = 100, actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    _need(actor, READ)
    with services.platform_db.platform_transaction() as c:
        rows = c.execute(text("""SELECT l.id, l.movement_type, l.direction, l.quantity, l.balance_after, l.reserved_after, l.reference, l.reason,
                l.source_type, l.provider_cost, l.provider_cost_currency, l.commercial_price, l.commercial_currency, l.created_at, u.full_name AS actor
            FROM school_sms_ledger l LEFT JOIN users u ON u.id=l.actor_user_id WHERE l.school_id=:s
            ORDER BY l.created_at DESC, l.id DESC LIMIT :n"""), {'s': str(school_id), 'n': max(1, min(limit, 500))}).mappings().all()
    return {'items': [dict(r) for r in rows]}


class CreditBody(BaseModel):
    quantity: int = Field(gt=0, le=10_000_000)
    reference: str = Field(min_length=2, max_length=120)          # invoice / payment reference of the school's purchase
    reason: str = Field(min_length=5, max_length=500)
    paid_on: date | None = None
    commercial_price: float | None = Field(default=None, ge=0)
    commercial_currency: str | None = Field(default=None, pattern='^[A-Z]{3}$')
    provider_cost: float | None = Field(default=None, ge=0)
    provider_cost_currency: str | None = Field(default=None, pattern='^[A-Z]{3}$')


class AdjustBody(BaseModel):
    direction: str = Field(pattern='^(CREDIT|DEBIT)$')
    quantity: int = Field(gt=0, le=10_000_000)
    reason: str = Field(min_length=5, max_length=500)
    reference: str | None = Field(default=None, max_length=120)


def _apply(services, actor, school_id: UUID, movement: str, quantity: int, key: str, *, reference=None, reason=None, direction=None,
           price=None, price_cur=None, cost=None, cost_cur=None) -> dict:
    try:
        with services.platform_db.platform_transaction() as c:
            if not c.execute(text("SELECT 1 FROM schools WHERE id=:s"), {'s': str(school_id)}).first():
                raise HTTPException(404, 'École introuvable')
            replay = c.execute(text("SELECT 1 FROM school_sms_ledger WHERE school_id=:s AND idempotency_key=:k"), {'s': str(school_id), 'k': key}).first()
            row = wallet_apply(c, school_id=school_id, movement=movement, quantity=quantity, key=key, actor=actor.user_id, source_type='platform',
                               reference=reference, reason=reason, direction=direction, provider_cost=cost, provider_cost_currency=cost_cur,
                               commercial_price=price, commercial_currency=price_cur)
            if not replay:
                _audit(c, actor, f'SMS_WALLET_{movement}', school_id,
                       {'quantity': quantity, 'direction': row['direction'], 'balance_after': row['balance_after'], 'reference': reference,
                        'ledger_id': str(row['id'])}, reason=reason, key=key)
            return {'ledger_id': str(row['id']), 'balance': row['balance_after'], 'reserved': row['reserved_after'], 'movement': movement,
                    'replayed': bool(replay)}
    except DBAPIError as e:
        msg = str(e.orig)
        if 'SMS_INSUFFICIENT_CREDIT' in msg:
            raise HTTPException(409, 'Solde disponible insuffisant pour ce débit') from e
        if 'SMS_' in msg:
            raise HTTPException(422, 'Mouvement de portefeuille refusé') from e
        raise


def _key(value: str | None) -> str:
    if not value or len(value.strip()) < 8:
        raise HTTPException(400, 'Idempotency-Key obligatoire')
    return value.strip()[:180]


@router.post('/wallets/{school_id}/credit')
def credit(school_id: UUID, body: CreditBody, idempotency_key: str | None = Header(default=None),
           actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    """Manual top-up after the school paid EduSync (outside the application, first version). Audited, idempotent."""
    _need(actor, CREDIT)
    require_recent_mfa(services, actor)
    key = _key(idempotency_key)
    reason = body.reason + (f' (payé le {body.paid_on.isoformat()})' if body.paid_on else '')
    return _apply(services, actor, school_id, 'TOPUP', body.quantity, f'topup:{key}', reference=body.reference, reason=reason,
                  price=body.commercial_price, price_cur=body.commercial_currency, cost=body.provider_cost, cost_cur=body.provider_cost_currency)


@router.post('/wallets/{school_id}/adjust')
def adjust(school_id: UUID, body: AdjustBody, idempotency_key: str | None = Header(default=None),
           actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    _need(actor, CREDIT)
    require_recent_mfa(services, actor)
    key = _key(idempotency_key)
    return _apply(services, actor, school_id, 'ADJUSTMENT', body.quantity, f'adjust:{key}', reference=body.reference, reason=body.reason,
                  direction=body.direction)


class TestSendBody(BaseModel):
    channel: str = Field(pattern='^(EMAIL|PUSH)$')


@router.post('/test-send')
def test_send(body: TestSendBody, actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    """Sends a test e-mail to the Manager's own address, or a test push to the Manager's own devices (never a third
    party): proves the real provider end to end. Goes through the same outbox / worker path as every message."""
    _need(actor, READ)
    require_recent_mfa(services, actor)
    with services.platform_db.platform_transaction() as c:
        user = c.execute(text("SELECT id, email, full_name FROM users WHERE id=:u"), {'u': str(actor.user_id)}).mappings().one()
        out = request_message(c, school_id=None, kind='PLATFORM', channels=[body.channel],
                              subject='Test EduSync', body=f'Message de test {body.channel} envoyé depuis l’Atelier Pro.',
                              recipients=[Recipient('USER', user['id'], user['full_name'], email=user['email'], user_id=user['id'])],
                              idempotency_key=f'provider-test:{uuid4()}', created_by=actor.user_id, template_code=None, link_path='/')
        PostgresAuditRepository(c).append(AuditRecord(action='PLATFORM_MESSAGING_TEST_SENT', entity_type='CommunicationMessage', entity_id=UUID(out['id']),
                                                      actor_user_id=actor.user_id, school_id=None, source=actor.source, new_data={'channel': body.channel},
                                                      correlation_id=actor.correlation_id))
    return {'message_id': out['id'], 'status': 'QUEUED', 'channel': body.channel}


@router.get('/test-send/{message_id}')
def test_send_status(message_id: UUID, actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    _need(actor, READ)
    with services.platform_db.platform_transaction() as c:
        rows = c.execute(text("""SELECT channel, status, last_error_code, attempts, sent_at FROM communication_deliveries
            WHERE message_id=:m AND school_id IS NULL"""), {'m': str(message_id)}).mappings().all()
    return {'items': [dict(r) for r in rows]}
