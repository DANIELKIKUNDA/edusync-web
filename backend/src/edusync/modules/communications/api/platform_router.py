"""Plateforme EduSync — Messagerie : centre d'exploitation des canaux (EXTERNAL_MESSAGING_ARCHITECTURE.md §8, lot 2026-10).

Strictly technical / commercial: provider health, delivery queue, diagnosable failures, SMS wallets. The platform
never reads the body of a school message here: only metadata (school, channel, provider, status, attempts, dates,
sanitized error codes, masked destination).

Provider state (per channel), CURRENT health separated from history:
  NOT_CONFIGURED  channel disabled, configuration incomplete, simulated provider, or the worker lacks the secret;
  CONFIGURED      configuration present, but neither a fresh real check nor a real send proves it works yet;
  OPERATIONAL     a real check of the worker (< 15 min) or a real send (< 24 h) succeeded, and nothing fails now;
  DEGRADED        the provider answers but sends fail now (last 15 min) or the queue of this channel is late;
  UNAVAILABLE     the latest real check failed (< 15 min), or a simulation is configured in a protected environment.
A failure older than 15 minutes is history: it is shown, it never keeps a channel degraded.
"""
from __future__ import annotations

import base64
import json
import re
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from edusync.adapters.postgres_repositories import PostgresAuditRepository
from edusync.bootstrap.dependencies import get_services, require_platform_actor, require_recent_mfa
from edusync.bootstrap.services import AppServices
from edusync.modules.audit.domain.audit import AuditRecord
from edusync.modules.communications.application.messaging import Recipient, request_message
from edusync.modules.communications.application.wallet import wallet_apply
from edusync.shared.application.context import ActorContext
from edusync.shared.messaging import health as provider_health
from edusync.shared.messaging.factory import channel_status

router = APIRouter(tags=['platform-messaging'])
READ = 'platform.messaging.read'
CREDIT = 'platform.sms_wallet.credit'
ADJUST = 'platform.sms_wallet.adjust'
RETRY = 'platform.messaging.retry'
CHANNELS = ('EMAIL', 'PUSH', 'SMS')
STATUSES = ('QUEUED', 'PROCESSING', 'SENT', 'DELIVERED', 'FAILED_RETRYABLE', 'FAILED_PERMANENT', 'CANCELLED')
CURRENT_WINDOW = timedelta(minutes=15)       # a failure older than this is history, never the current state
HEALTH_FRESH = timedelta(minutes=15)
LATE_QUEUE_SECONDS = 600
PROVIDER_NAME = {'email': {'smtp': 'SMTP (Brevo)', 'fake': 'Simulation'}, 'push': {'fcm': 'Firebase Cloud Messaging', 'fake': 'Simulation', 'mock': 'Simulation'},
                 'sms': {'orange': 'Orange SMS', 'fake': 'Simulation', 'mock': 'Simulation', 'sandbox': 'Simulation'}}


def _need(actor: ActorContext, cap: str) -> None:
    try:
        actor.require(cap)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc


def _audit(c, actor: ActorContext, action: str, entity_type: str, entity_id: UUID, new: dict, *, reason: str | None = None, key: str | None = None) -> None:
    PostgresAuditRepository(c).append(AuditRecord(action=action, entity_type=entity_type, entity_id=entity_id, actor_user_id=actor.user_id,
                                                  school_id=None, source=actor.source, reason=reason, new_data=new,
                                                  correlation_id=actor.correlation_id, idempotency_key=key))


def _redis(services: AppServices):
    import redis
    return redis.Redis.from_url(services.settings.redis_url, decode_responses=True, socket_timeout=1, socket_connect_timeout=1)


def _iso(v):
    return v.isoformat() if isinstance(v, (datetime, date)) else v


def mask(channel: str, destination: str | None) -> str:
    """Destination shown to the platform: enough to recognise it, never the full address / number / device token."""
    d = (destination or '').strip()
    if not d or d.startswith('skip:'):
        return '—'
    if channel == 'EMAIL' and '@' in d:
        name, _, domain = d.partition('@')
        return (name[:2] + '•••' if len(name) > 2 else name[:1] + '•••') + '@' + domain
    if channel == 'SMS':
        return d[:4] + '•' * max(0, len(d) - 6) + d[-2:] if len(d) > 6 else '•••'
    if channel == 'PUSH':
        return 'Appareil …' + d[-4:]
    return '•••'


def _sanitize(detail: str | None) -> str | None:
    if not detail:
        return None
    from edusync.shared.infrastructure.signals import redact
    return redact(detail) or None


def channel_state(key: str, cfg_state: dict, snap: dict | None, facts: dict, now: datetime) -> dict:
    """CURRENT state of one channel from configuration, the worker's real check and the real sends (pure)."""
    provider = cfg_state['provider']
    h = ((snap or {}).get('channels') or {}).get(key)
    checked = datetime.fromisoformat(h['checked_at']) if h and h.get('checked_at') else None
    fresh = bool(checked and now - checked <= HEALTH_FRESH)
    last_success = facts.get('last_success')
    recent_success = bool(last_success and now - last_success <= timedelta(hours=24))
    failing_now = facts.get('failed_15m', 0) > 0 and facts.get('sent_15m', 0) == 0
    late = (facts.get('oldest_due_seconds') or 0) > LATE_QUEUE_SECONDS
    reasons: list[str] = []
    if cfg_state['state'] == 'REFUSED':
        state = 'UNAVAILABLE'; reasons.append('Simulation interdite dans cet environnement')
    elif cfg_state['state'] in ('DISABLED', 'INCOMPLETE') or (h and h.get('state') == 'NOT_CONFIGURED'):
        state = 'NOT_CONFIGURED'
        reasons.append('Canal désactivé' if cfg_state['state'] == 'DISABLED' else
                       'Configuration incomplète' if cfg_state['state'] == 'INCOMPLETE' else 'Le worker n’a pas les identifiants du fournisseur')
    elif cfg_state['state'] == 'SIMULATED':
        state = 'NOT_CONFIGURED'; reasons.append('Simulation de développement : aucun envoi réel, jamais une certification')
    elif fresh and h.get('ok') is False:
        state = 'UNAVAILABLE'; reasons.append(f"Dernier contrôle réel en échec ({h.get('error_code') or 'erreur'})")
    elif failing_now or late:
        state = 'DEGRADED'
        if failing_now:
            reasons.append(f"{facts['failed_15m']} échec(s) sur les 15 dernières minutes, aucun envoi réussi")
        if late:
            reasons.append(f"Envoi le plus ancien en attente depuis {int(facts['oldest_due_seconds'] // 60)} min")
    elif (fresh and h.get('ok') is True) or recent_success:
        state = 'OPERATIONAL'
        reasons.append('Contrôle réel réussi' if fresh and h.get('ok') else 'Envoi réel réussi dans les dernières 24 h')
    else:
        state = 'CONFIGURED'; reasons.append('Configuré, pas encore prouvé par un contrôle ou un envoi réel')
    return {'key': key, 'channel': key.upper(), 'provider': provider, 'provider_label': PROVIDER_NAME.get(key, {}).get(provider, provider),
            'config_state': cfg_state['state'], 'state': state, 'reasons': reasons, 'simulated': cfg_state['state'] == 'SIMULATED',
            'health': None if not h else {'checked_at': h.get('checked_at'), 'fresh': fresh, 'ok': h.get('ok'), 'latency_ms': h.get('latency_ms'),
                                          'error_code': h.get('error_code'), 'project_id': h.get('project_id'),
                                          'config': {k: v for k, v in (h.get('config') or {}).items() if k != 'provider'}},
            'last_success_at': _iso(last_success), 'last_failure_at': _iso(facts.get('last_failure')),
            'last_failure_code': facts.get('last_failure_code'), 'backlog': facts.get('backlog', 0), 'retrying': facts.get('retrying', 0),
            'dead_7d': facts.get('dead_7d', 0), 'oldest_due_seconds': facts.get('oldest_due_seconds'),
            'volumes_24h': facts.get('volumes_24h', {}), 'last_test': facts.get('last_test')}


def _facts(c) -> dict[str, dict]:
    rows = c.execute(text("""SELECT channel,
            max(sent_at) AS last_success,
            max(failed_at) FILTER (WHERE status='FAILED_PERMANENT') AS last_failure,
            count(*) FILTER (WHERE (status='FAILED_PERMANENT' AND failed_at > now() - interval '15 minutes')
                             OR (status='FAILED_RETRYABLE' AND last_attempt_at > now() - interval '15 minutes')) AS failed_15m,
            count(*) FILTER (WHERE sent_at > now() - interval '15 minutes') AS sent_15m,
            count(*) FILTER (WHERE status IN ('QUEUED','FAILED_RETRYABLE','PROCESSING')) AS backlog,
            count(*) FILTER (WHERE status='FAILED_RETRYABLE') AS retrying,
            count(*) FILTER (WHERE status='FAILED_PERMANENT' AND failed_at > now() - interval '7 days') AS dead_7d,
            extract(epoch FROM now() - min(created_at) FILTER (WHERE status IN ('QUEUED','FAILED_RETRYABLE')))::int AS oldest_due_seconds
        FROM communication_deliveries GROUP BY channel""")).mappings().all()
    out = {r['channel']: dict(r) for r in rows}
    for r in c.execute(text("""SELECT DISTINCT ON (channel) channel, last_error_code FROM communication_deliveries
            WHERE status='FAILED_PERMANENT' ORDER BY channel, failed_at DESC NULLS LAST""")).mappings():
        out.setdefault(r['channel'], {})['last_failure_code'] = r['last_error_code']
    for r in c.execute(text("""SELECT channel, status, count(*) n FROM communication_deliveries
            WHERE created_at >= now() - interval '24 hours' GROUP BY channel, status""")).mappings():
        out.setdefault(r['channel'], {}).setdefault('volumes_24h', {})[r['status']] = r['n']
    for r in c.execute(text("""SELECT DISTINCT ON (d.channel) d.channel, d.status, d.last_error_code, d.sent_at, d.created_at, d.provider_message_id
            FROM communication_deliveries d JOIN communication_messages m ON m.id=d.message_id
            WHERE m.idempotency_key LIKE 'provider-test:%' ORDER BY d.channel, d.created_at DESC""")).mappings():
        out.setdefault(r['channel'], {})['last_test'] = {'status': r['status'], 'error_code': r['last_error_code'], 'at': _iso(r['created_at']),
                                                         'sent_at': _iso(r['sent_at']), 'provider_proof': bool(r['provider_message_id'])}
    return out


@router.get('/status')
def status(actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    """Cockpit: one card per channel (current state + facts), the queue, the active failures. Metadata only."""
    _need(actor, READ)
    heartbeat = snap = None
    try:
        r = _redis(services)
        heartbeat = r.get('edusync:heartbeat:communications')
        snap = provider_health.read(r)
    except Exception:  # noqa: BLE001 — health is best effort
        pass
    now = datetime.now(timezone.utc)
    with services.platform_db.platform_transaction() as c:
        facts = _facts(c)
        q = c.execute(text("""SELECT count(*) FILTER (WHERE status IN ('QUEUED','FAILED_RETRYABLE')) due,
                count(*) FILTER (WHERE status='PROCESSING') processing,
                count(*) FILTER (WHERE status='FAILED_RETRYABLE') retrying,
                count(*) FILTER (WHERE status='FAILED_PERMANENT' AND failed_at >= now() - interval '7 days') dead_7d,
                count(*) FILTER (WHERE status='FAILED_PERMANENT' AND failed_at >= now() - interval '15 minutes') failed_15m,
                min(created_at) FILTER (WHERE status IN ('QUEUED','FAILED_RETRYABLE')) oldest_due
            FROM communication_deliveries""")).mappings().one()
        undispatched = c.execute(text("""SELECT count(*) FROM communication_messages WHERE dispatched_at IS NULL
            AND created_at >= now() - interval '7 days'""")).scalar_one()
        receipts = c.execute(text("SELECT count(*) FROM provider_receipts WHERE applied_at IS NULL")).scalar_one()
    cfg = channel_status(services.settings)
    channels = [channel_state(k, cfg[k], snap, facts.get(k.upper(), {}), now) for k in ('push', 'email', 'sms')]
    hb_age = int((now - datetime.fromisoformat(heartbeat)).total_seconds()) if heartbeat else None
    return {'channels': channels, 'providers': cfg,
            'queue': {**{k: _iso(v) for k, v in dict(q).items()}, 'waiting_dispatch': undispatched, 'receipts_waiting': receipts,
                      'worker_heartbeat': heartbeat, 'worker_age_seconds': hb_age,
                      'worker_state': 'OK' if hb_age is not None and hb_age < 60 else 'LATE' if hb_age is not None and hb_age < 300 else 'DOWN'},
            'health_checked_at': (snap or {}).get('checked_at'), 'measured_at': now.isoformat(),
            # legacy keys (earlier screens / probes)
            'worker_heartbeat': heartbeat, 'volumes_24h': {k: v.get('volumes_24h', {}) for k, v in facts.items()},
            'receipts_waiting': receipts, 'account_messages_waiting_dispatch': undispatched}


@router.post('/health-check', status_code=202)
def request_health_check(actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    """Asks the worker for a real check of every provider now (no message sent). 30 s cooldown shared by everyone."""
    _need(actor, READ)
    try:
        r = _redis(services)
        if not r.set('edusync:messaging:health:cooldown', '1', nx=True, ex=30):
            return {'requested': False, 'detail': 'Un contrôle vient d’être demandé : résultat dans quelques secondes.'}
        r.set(provider_health.REQUEST_KEY, '1', ex=600)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, 'File de contrôle indisponible (cache injoignable)') from exc
    return {'requested': True}


# ------------------------------------------------------------------------------------------- deliveries (queue explorer)
def _cursor(at: datetime, did: str) -> str:
    return base64.urlsafe_b64encode(json.dumps([at.isoformat(), did]).encode()).decode()


def _decode(cur: str):
    try:
        at, did = json.loads(base64.urlsafe_b64decode(cur.encode()).decode())
        return datetime.fromisoformat(at), str(UUID(did))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(422, 'Curseur invalide') from exc


@router.get('/deliveries')
def deliveries(channel: str | None = Query(None, pattern='^(EMAIL|PUSH|SMS)$'),
               status: str | None = Query(None, pattern='^(QUEUED|PROCESSING|SENT|DELIVERED|FAILED_RETRYABLE|FAILED_PERMANENT|CANCELLED|ACTIVE_FAILURES|BACKLOG)$'),
               school_id: UUID | None = None, scope: str | None = Query(None, pattern='^(PLATFORM|SCHOOL)$'),
               event: str | None = Query(None, max_length=64, pattern=r'^[A-Z0-9_]+$'),  # template / kind, or SCHOOL_MESSAGE
               provider: str | None = Query(None, max_length=24, pattern=r'^[a-z_]+$'),
               date_from: date | None = None, date_to: date | None = None,
               q: str | None = Query(None, max_length=254), cursor: str | None = None, limit: int = Query(25, ge=1, le=100),
               actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    """Server-side search, keyset pagination. q: a delivery / message / outbox / correlation id, a provider message id,
    or an exact recipient address (shown masked)."""
    _need(actor, READ)
    where, p = ['1=1'], {'n': limit + 1}
    if channel:
        where.append('d.channel=:ch'); p['ch'] = channel
    if status == 'ACTIVE_FAILURES':
        where.append("(d.status='FAILED_PERMANENT' AND d.failed_at > now() - interval '7 days' OR d.status='FAILED_RETRYABLE')")
    elif status == 'BACKLOG':
        where.append("d.status IN ('QUEUED','FAILED_RETRYABLE','PROCESSING')")
    elif status:
        where.append('d.status=:st'); p['st'] = status
    if school_id:
        where.append('d.school_id=:sid'); p['sid'] = str(school_id)
    if scope == 'PLATFORM':
        where.append('d.school_id IS NULL')
    elif scope == 'SCHOOL':
        where.append('d.school_id IS NOT NULL')
    if event == 'SCHOOL_MESSAGE':
        where.append('d.school_id IS NOT NULL')
    elif event:
        where.append('(m.template_code=:ev OR m.kind=:ev)'); p['ev'] = event
    if provider:
        where.append('d.provider_code=:pv'); p['pv'] = provider
    if date_from:
        where.append('d.created_at >= :df'); p['df'] = datetime.combine(date_from, datetime.min.time(), timezone.utc)
    if date_to:
        where.append('d.created_at < :dt'); p['dt'] = datetime.combine(date_to + timedelta(days=1), datetime.min.time(), timezone.utc)
    term = (q or '').strip()
    if term:
        try:
            uid = str(UUID(term))
            where.append("""(d.id=:uid OR d.message_id=:uid OR m.correlation_id=:uid
                OR EXISTS (SELECT 1 FROM outbox_events o WHERE o.aggregate_id=d.message_id AND (o.id=:uid OR o.correlation_id=:uid)))"""); p['uid'] = uid
        except ValueError:
            if '@' in term:
                where.append('lower(d.destination)=:dest'); p['dest'] = term.lower()
            else:
                where.append('d.provider_message_id=:pmid'); p['pmid'] = term
    if cursor:
        at, did = _decode(cursor)
        where.append('(d.created_at, d.id) < (:cat, CAST(:cid AS uuid))'); p.update(cat=at, cid=did)
    with services.platform_db.platform_transaction() as c:
        rows = c.execute(text(f"""SELECT d.id, d.channel, d.status, d.provider_code, d.destination, d.attempts, d.created_at, d.last_attempt_at,
                d.next_attempt_at, d.sent_at, d.delivered_at, d.failed_at, d.last_error_code, d.school_id, s.name AS school_name,
                m.kind, m.template_code
            FROM communication_deliveries d LEFT JOIN communication_messages m ON m.id=d.message_id LEFT JOIN schools s ON s.id=d.school_id
            WHERE {' AND '.join(where)} ORDER BY d.created_at DESC, d.id DESC LIMIT :n"""), p).mappings().all()
    more = len(rows) > limit
    rows = rows[:limit]
    return {'items': [{'id': str(r['id']), 'channel': r['channel'], 'status': r['status'], 'provider': r['provider_code'],
                       'destination': mask(r['channel'], r['destination']), 'attempts': r['attempts'], 'event': r['template_code'] or r['kind'] or 'SCHOOL_MESSAGE',
                       'school_id': str(r['school_id']) if r['school_id'] else None, 'school_name': r['school_name'],
                       'created_at': _iso(r['created_at']), 'last_attempt_at': _iso(r['last_attempt_at']), 'next_attempt_at': _iso(r['next_attempt_at']),
                       'sent_at': _iso(r['sent_at']), 'delivered_at': _iso(r['delivered_at']), 'failed_at': _iso(r['failed_at']),
                       'error_code': r['last_error_code']} for r in rows],
            'next_cursor': _cursor(rows[-1]['created_at'], str(rows[-1]['id'])) if more and rows else None}


IMPACT = {'ACCOUNT_INVITATION': 'La personne invitée ne peut pas activer son compte tant que l’invitation n’est pas reçue.',
          'ACCOUNT_PASSWORD_RESET': 'La personne ne peut pas réinitialiser son mot de passe.',
          'ACCOUNT_SECURITY_ALERT': 'La personne n’est pas prévenue d’une action de sécurité sur son compte.',
          'PLATFORM_ALERT': 'Une alerte d’exploitation n’est pas parvenue à son destinataire.'}


@router.get('/deliveries/{delivery_id}')
def delivery_detail(delivery_id: UUID, actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    _need(actor, READ)
    with services.platform_db.platform_transaction() as c:
        r = c.execute(text("""SELECT d.*, s.name AS school_name, m.kind, m.template_code, m.correlation_id AS message_correlation_id,
                m.recipient_count, m.created_at AS message_created_at, m.dispatched_at,
                (SELECT o.id FROM outbox_events o WHERE o.aggregate_id=d.message_id AND o.event_type='COMMUNICATION_REQUESTED' ORDER BY o.created_at LIMIT 1) AS outbox_id,
                (SELECT o.correlation_id FROM outbox_events o WHERE o.aggregate_id=d.message_id AND o.event_type='COMMUNICATION_REQUESTED' ORDER BY o.created_at LIMIT 1) AS outbox_correlation_id
            FROM communication_deliveries d LEFT JOIN communication_messages m ON m.id=d.message_id LEFT JOIN schools s ON s.id=d.school_id
            WHERE d.id=:id"""), {'id': str(delivery_id)}).mappings().first()
        if r is None:
            raise HTTPException(404, 'Envoi introuvable')
        siblings = c.execute(text("""SELECT status, count(*) n FROM communication_deliveries WHERE message_id=:m GROUP BY status"""),
                             {'m': str(r['message_id'])}).mappings().all()
        retries = c.execute(text("""SELECT occurred_at, reason FROM audit_events WHERE entity_id=:id AND action IN
            ('PLATFORM_MESSAGING_DELIVERY_RETRIED','COMMUNICATION_DELIVERY_RETRIED') ORDER BY occurred_at DESC LIMIT 10"""),
                             {'id': str(delivery_id)}).mappings().all()
    # a school message is private: the platform sees the delivery metadata, never the message (row-level security)
    event = r['template_code'] or r['kind'] or 'SCHOOL_MESSAGE'
    can_retry = (RETRY in actor.permissions and r['status'] == 'FAILED_PERMANENT' and r['channel'] in ('EMAIL', 'PUSH'))
    return {'id': str(r['id']), 'channel': r['channel'], 'provider': r['provider_code'], 'status': r['status'], 'event': event, 'kind': r['kind'],
            'school_id': str(r['school_id']) if r['school_id'] else None, 'school_name': r['school_name'],
            'destination': mask(r['channel'], r['destination']), 'attempts': r['attempts'],
            'created_at': _iso(r['created_at']), 'first_attempt_at': _iso(r['first_attempt_at']), 'last_attempt_at': _iso(r['last_attempt_at']),
            'next_attempt_at': _iso(r['next_attempt_at']), 'sent_at': _iso(r['sent_at']), 'delivered_at': _iso(r['delivered_at']),
            'failed_at': _iso(r['failed_at']), 'cancelled_at': _iso(r['cancelled_at']),
            'error_code': r['last_error_code'], 'error_detail': _sanitize(r['last_error_detail']),
            'message_id': str(r['message_id']), 'outbox_id': str(r['outbox_id']) if r['outbox_id'] else None,
            'correlation_id': str(r['message_correlation_id'] or r['outbox_correlation_id']) if (r['message_correlation_id'] or r['outbox_correlation_id']) else None,
            'provider_message_id': r['provider_message_id'], 'segments_billed': r['segments_billed'], 'wallet_state': r['wallet_state'],
            'delivered_proof': r['status'] == 'DELIVERED',
            'impact': IMPACT.get(event) if r['status'] in ('FAILED_PERMANENT', 'FAILED_RETRYABLE') else None,
            'message': {'private': r['kind'] is None, 'recipients': r['recipient_count'], 'created_at': _iso(r['message_created_at']), 'dispatched_at': _iso(r['dispatched_at']),
                        'deliveries_by_status': {s['status']: s['n'] for s in siblings}},
            'retries': [{'at': _iso(x['occurred_at']), 'reason': x['reason']} for x in retries],
            'can_retry': can_retry,
            'retry_policy': ('SMS : la relance se fait depuis l’école (elle engage son portefeuille).' if r['channel'] == 'SMS' else None)}


class RetryBody(BaseModel):
    reason: str = Field(min_length=5, max_length=300)


@router.post('/deliveries/{delivery_id}/retry')
def retry_delivery(delivery_id: UUID, body: RetryBody, idempotency_key: str | None = Header(default=None),
                   actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    """Manual retry of an e-mail / push in FAILED_PERMANENT (dedicated capability, reason, step-up, audit). Idempotent:
    a delivery already back in the queue, sent or delivered is left unchanged — no double send. Never an SMS."""
    _need(actor, RETRY)
    require_recent_mfa(services, actor, RETRY)
    key = _key(idempotency_key)
    with services.platform_db.platform_transaction() as c:
        replay = c.execute(text("""SELECT 1 FROM audit_events WHERE action='PLATFORM_MESSAGING_DELIVERY_RETRIED' AND entity_id=:id AND idempotency_key=:k"""),
                           {'id': str(delivery_id), 'k': key}).first()
        seen = c.execute(text("SELECT status, channel FROM communication_deliveries WHERE id=:id"), {'id': str(delivery_id)}).mappings().first()
        if seen is None:
            raise HTTPException(404, 'Envoi introuvable')
        if seen['channel'] == 'SMS':
            raise HTTPException(409, 'Un SMS se relance depuis l’école : la relance engage son portefeuille.')
        # the row lock is only possible on e-mail / push rows (row-level security of the platform role)
        cur = c.execute(text("SELECT status, channel FROM communication_deliveries WHERE id=:id FOR UPDATE"), {'id': str(delivery_id)}).mappings().one()
        if replay:
            return {'status': cur['status'], 'requeued': False, 'replayed': True}
        if cur['status'] != 'FAILED_PERMANENT':
            return {'status': cur['status'], 'requeued': False}
        c.execute(text("""UPDATE communication_deliveries SET status='QUEUED', attempts=0, next_attempt_at=NULL, last_error_code=NULL,
            last_error_detail=NULL, failed_at=NULL WHERE id=:id AND status='FAILED_PERMANENT' AND channel IN ('EMAIL','PUSH')"""), {'id': str(delivery_id)})
        _audit(c, actor, 'PLATFORM_MESSAGING_DELIVERY_RETRIED', 'CommunicationDelivery', delivery_id,
               {'channel': cur['channel'], 'previous_status': 'FAILED_PERMANENT'}, reason=body.reason.strip(), key=key)
    try:
        _redis(services).lpush('edusync:communications', json.dumps({'delivery_id': str(delivery_id)}))
    except Exception:  # noqa: BLE001 — the worker also polls the database
        pass
    return {'status': 'QUEUED', 'requeued': True}


# ------------------------------------------------------------------------------------------------------- SMS wallets
def _wcursor(name: str, sid: str) -> str:
    return base64.urlsafe_b64encode(json.dumps([name, sid]).encode()).decode()


@router.get('/wallets')
def wallets(q: str | None = Query(None, max_length=120), low: bool = False, cursor: str | None = None, limit: int = Query(50, ge=1, le=200),
            actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    _need(actor, READ)
    where, p = ['1=1'], {'n': limit + 1}
    if q and q.strip():
        where.append('(edusync_search_key(s.name) LIKE :q OR lower(s.code) LIKE :qc)')
        p.update(q='%' + re.sub(r'\s+', ' ', q.strip().lower()) + '%', qc='%' + q.strip().lower() + '%')
    if cursor:
        try:
            name, sid = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
            UUID(sid)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(422, 'Curseur invalide') from exc
        where.append('(s.name, s.id) > (:cn, CAST(:cs AS uuid))'); p.update(cn=name, cs=sid)
    with services.platform_db.platform_transaction() as c:
        base = f"""SELECT s.id AS school_id, s.name, s.code, s.status, coalesce(w.balance,0) balance, coalesce(w.reserved,0) reserved,
                coalesce(cs.sms_enabled,false) sms_enabled, coalesce(cs.sms_low_balance_threshold,50) threshold,
                coalesce((SELECT sum(l.quantity) FROM school_sms_ledger l WHERE l.school_id=s.id AND l.movement_type='CONSUMPTION'
                          AND l.created_at >= now() - interval '30 days'),0) consumed_30d,
                (SELECT max(l.created_at) FROM school_sms_ledger l WHERE l.school_id=s.id AND l.movement_type='TOPUP') last_topup_at
            FROM schools s LEFT JOIN school_sms_wallets w ON w.school_id=s.id LEFT JOIN communication_settings cs ON cs.school_id=s.id
            WHERE {' AND '.join(where)}"""
        if low:
            base = f"SELECT * FROM ({base}) x WHERE x.sms_enabled AND x.balance - x.reserved <= x.threshold"
        rows = c.execute(text(base + " ORDER BY name, school_id LIMIT :n"), p).mappings().all()
        totals = c.execute(text("""SELECT coalesce(sum(balance),0) balance, coalesce(sum(reserved),0) reserved, count(*) FILTER (WHERE balance>0) funded
            FROM school_sms_wallets""")).mappings().one()
    more = len(rows) > limit
    rows = rows[:limit]
    return {'items': [{**{k: (str(v) if k == 'school_id' else _iso(v)) for k, v in dict(r).items()}, 'available': r['balance'] - r['reserved'],
                       'low': bool(r['sms_enabled']) and r['balance'] - r['reserved'] <= r['threshold']} for r in rows],   # no alarm when SMS are off
            'next_cursor': _wcursor(rows[-1]['name'], str(rows[-1]['school_id'])) if more and rows else None,
            'totals': {'balance': int(totals['balance']), 'reserved': int(totals['reserved']), 'available': int(totals['balance'] - totals['reserved']),
                       'funded_schools': int(totals['funded'])}}


@router.get('/wallets/{school_id}/ledger')
def ledger(school_id: UUID, limit: int = Query(100, ge=1, le=500), actor: ActorContext = Depends(require_platform_actor),
           services: AppServices = Depends(get_services)):
    _need(actor, READ)
    with services.platform_db.platform_transaction() as c:
        wallet = c.execute(text("""SELECT s.name, coalesce(w.balance,0) balance, coalesce(w.reserved,0) reserved FROM schools s
            LEFT JOIN school_sms_wallets w ON w.school_id=s.id WHERE s.id=:s"""), {'s': str(school_id)}).mappings().first()
        if wallet is None:
            raise HTTPException(404, 'École introuvable')
        rows = c.execute(text("""SELECT l.id, l.movement_type, l.direction, l.quantity, l.balance_after, l.reserved_after, l.reference, l.reason,
                l.source_type, l.provider_cost, l.provider_cost_currency, l.commercial_price, l.commercial_currency, l.created_at, u.full_name AS actor
            FROM school_sms_ledger l LEFT JOIN users u ON u.id=l.actor_user_id WHERE l.school_id=:s
            ORDER BY l.created_at DESC, l.id DESC LIMIT :n"""), {'s': str(school_id), 'n': limit}).mappings().all()
    items = []
    for r in rows:
        signed = r['quantity'] if r['direction'] == 'CREDIT' else -r['quantity'] if r['direction'] == 'DEBIT' else 0
        # balance before = balance after minus the movement on the balance (reservations / releases only move "reserved")
        items.append({**{k: _iso(v) if k != 'id' else str(v) for k, v in dict(r).items()}, 'balance_before': r['balance_after'] - signed})
    return {'items': items, 'wallet': {'name': wallet['name'], 'balance': wallet['balance'], 'reserved': wallet['reserved'],
                                       'available': wallet['balance'] - wallet['reserved']}}


class CreditBody(BaseModel):
    quantity: int = Field(gt=0, le=10_000_000)
    reference: str = Field(min_length=2, max_length=120)          # invoice / payment reference of the school's purchase
    reason: str = Field(min_length=5, max_length=500)
    paid_on: date
    commercial_price: float = Field(gt=0)
    commercial_currency: str = Field(pattern='^(USD|CDF)$')
    provider_cost: float | None = Field(default=None, ge=0)
    provider_cost_currency: str | None = Field(default=None, pattern='^[A-Z]{3}$')

    @field_validator('paid_on')
    @classmethod
    def not_future(cls, v: date) -> date:
        if v > date.today() + timedelta(days=1):
            raise ValueError('La date du paiement ne peut pas être dans le futur')
        return v


class AdjustBody(BaseModel):
    direction: str = Field(pattern='^(CREDIT|DEBIT)$')
    quantity: int = Field(gt=0, le=10_000_000)
    reason: str = Field(min_length=10, max_length=500)
    reference: str | None = Field(default=None, max_length=120)


def _apply(services, actor, school_id: UUID, movement: str, quantity: int, key: str, *, reference=None, reason=None, direction=None,
           price=None, price_cur=None, cost=None, cost_cur=None, paid_on=None) -> dict:
    try:
        with services.platform_db.platform_transaction() as c:
            if not c.execute(text("SELECT 1 FROM schools WHERE id=:s"), {'s': str(school_id)}).first():
                raise HTTPException(404, 'École introuvable')
            replay = c.execute(text("SELECT 1 FROM school_sms_ledger WHERE school_id=:s AND idempotency_key=:k"), {'s': str(school_id), 'k': key}).first()
            before = c.execute(text("SELECT coalesce(balance,0) b, coalesce(reserved,0) r FROM school_sms_wallets WHERE school_id=:s"),
                               {'s': str(school_id)}).mappings().first() or {'b': 0, 'r': 0}
            row = wallet_apply(c, school_id=school_id, movement=movement, quantity=quantity, key=key, actor=actor.user_id, source_type='platform',
                               reference=reference, reason=reason, direction=direction, provider_cost=cost, provider_cost_currency=cost_cur,
                               commercial_price=price, commercial_currency=price_cur)
            if not replay:
                _audit(c, actor, f'SMS_WALLET_{movement}', 'SchoolSmsWallet', school_id,
                       {'quantity': quantity, 'direction': row['direction'], 'balance_before': before['b'], 'balance_after': row['balance_after'],
                        'reference': reference, 'paid_on': _iso(paid_on), 'amount': price, 'currency': price_cur, 'ledger_id': str(row['id'])},
                       reason=reason, key=key)
            return {'ledger_id': str(row['id']), 'balance_before': before['b'], 'balance': row['balance_after'], 'reserved': row['reserved_after'],
                    'available': row['balance_after'] - row['reserved_after'], 'movement': movement, 'replayed': bool(replay)}
    except DBAPIError as e:
        msg = str(e.orig)
        if 'SMS_INSUFFICIENT_CREDIT' in msg:
            raise HTTPException(409, 'Solde disponible insuffisant pour ce débit : le solde ne peut pas devenir négatif') from e
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
    """Recharge after the school paid EduSync (outside the application): quantity, payment reference, date, amount,
    currency, reason. Audited, idempotent, step-up."""
    _need(actor, CREDIT)
    require_recent_mfa(services, actor)
    key = _key(idempotency_key)
    reason = f"{body.reason} (payé le {body.paid_on.strftime('%d/%m/%Y')} : {body.commercial_price:g} {body.commercial_currency})"
    return _apply(services, actor, school_id, 'TOPUP', body.quantity, f'topup:{key}', reference=body.reference, reason=reason,
                  price=body.commercial_price, price_cur=body.commercial_currency, cost=body.provider_cost, cost_cur=body.provider_cost_currency,
                  paid_on=body.paid_on)


@router.post('/wallets/{school_id}/adjust')
def adjust(school_id: UUID, body: AdjustBody, idempotency_key: str | None = Header(default=None),
           actor: ActorContext = Depends(require_platform_actor), services: AppServices = Depends(get_services)):
    """Correction (credit or debit) — separate, higher capability, justified, never below zero."""
    _need(actor, ADJUST)
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
        if body.channel == 'PUSH' and not c.execute(text("""SELECT 1 FROM push_subscriptions WHERE user_id=:u AND school_id IS NULL
                AND revoked_at IS NULL AND token_ciphertext IS NOT NULL LIMIT 1"""), {'u': str(actor.user_id)}).first():
            raise HTTPException(409, 'Aucun appareil enregistré pour vos notifications plateforme : activez d’abord les notifications sur ce téléphone ou cet ordinateur.')
        out = request_message(c, school_id=None, kind='PLATFORM', channels=[body.channel],
                              subject='Test EduSync', body=f'Message de test {body.channel} envoyé depuis la plateforme EduSync.',
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
        rows = c.execute(text("""SELECT id, channel, status, last_error_code, attempts, sent_at, provider_message_id IS NOT NULL AS provider_proof
            FROM communication_deliveries WHERE message_id=:m AND school_id IS NULL"""), {'m': str(message_id)}).mappings().all()
    return {'items': [{**dict(r), 'id': str(r['id']), 'sent_at': _iso(r['sent_at'])} for r in rows]}
