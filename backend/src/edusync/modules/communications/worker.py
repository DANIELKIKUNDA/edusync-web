"""Durable communications worker. PostgreSQL remains source of truth; Redis is only a wake-up hint.
Provider failure never rolls back a business transaction: the business commit already happened, this worker only
reads what the use case recorded (message + recipients + COMMUNICATION_REQUESTED outbox event).

Pipeline (EXTERNAL_MESSAGING_ARCHITECTURE.md):
  1. dispatch: outbox event COMMUNICATION_REQUESTED -> NotificationPolicy -> one delivery per (message, channel,
     destination). Idempotent (unique key + dispatched_at), SMS credits not used by the policy are released.
  2. deliver: claim a due delivery (QUEUED / FAILED_RETRYABLE, expired lease) with SKIP LOCKED, call the provider
     port OUTSIDE any lock, then record the outcome. SENT needs a provider proof; DELIVERED only comes from receipts.
  3. wallet: SMS credits reserved at confirmation are CONSUMED when the provider accepts, RELEASED on a permanent
     failure or a cancellation. Every movement has an idempotency key derived from the delivery id.
Retries: exponential backoff with jitter, bounded (MAX_ATTEMPTS), then FAILED_PERMANENT (dead letter, visible).
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from uuid import uuid4

import redis
from sqlalchemy import create_engine, text

from edusync.bootstrap.settings import Settings, worker_url
from edusync.modules.communications.application.messaging import sms_units
from edusync.modules.communications.application.wallet import wallet_apply
from edusync.modules.communications.domain.email_templates import render as render_email
from edusync.modules.communications.domain.policy import decide
from edusync.shared.infrastructure.heartbeat import beat
from edusync.shared.messaging import health as provider_health
from edusync.shared.messaging import ports
from edusync.shared.messaging.factory import build_email_provider, build_push_provider, build_sms_provider
from edusync.shared.messaging.sealing import DELIVERY_SECRET, PUSH_TOKEN, cipher

QUEUE = 'edusync:communications'
MAX_ATTEMPTS = 6
LEASE_SECONDS = 90
DISPATCH_BATCH = 20
log = logging.getLogger('edusync.communications_worker')


def backoff_seconds(attempt: int, retry_after: int | None = None) -> int:
    """30 s, 60 s, 120 s ... capped at 1 h, +/-20 % jitter so a provider outage does not create retry storms."""
    base = min(3600, 30 * (2 ** max(0, attempt - 1)))
    if retry_after:
        base = max(base, min(3600, int(retry_after)))
    return max(1, int(base * random.uniform(0.8, 1.2)))


# ================================================================================================ 1. dispatch
def dispatch_pending(cfg, engine, limit: int = DISPATCH_BATCH) -> int:
    done = 0
    for _ in range(limit):
        with engine.begin() as c:
            ev = c.execute(text("""
                SELECT o.id AS event_id, m.id, m.school_id, m.kind, m.channels, m.sms_segments_reserved, m.body
                FROM outbox_events o JOIN communication_messages m ON m.id=o.aggregate_id
                WHERE o.event_type='COMMUNICATION_REQUESTED' AND m.dispatched_at IS NULL
                ORDER BY o.created_at, o.id FOR UPDATE OF m SKIP LOCKED LIMIT 1""")).mappings().first()
            if not ev:
                return done
            settings = None
            if ev['school_id']:
                settings = c.execute(text("SELECT * FROM communication_settings WHERE school_id=:s"), {'s': str(ev['school_id'])}).mappings().first()
                settings = dict(settings) if settings else None
            recipients = c.execute(text("""SELECT id, recipient_kind, recipient_ref, user_id, phone_e164, email, target_school_id FROM communication_recipients
                WHERE message_id=:m ORDER BY created_at, id"""), {'m': str(ev['id'])}).mappings().all()
            units_each = 0
            sms_recipients = 0
            seen: set[str] = set()
            for r in recipients:
                devices = []
                if 'PUSH' in ev['channels'] and r['user_id']:
                    devices = [str(x[0]) for x in c.execute(text("""SELECT id FROM push_subscriptions WHERE user_id=:u AND revoked_at IS NULL
                        AND token_ciphertext IS NOT NULL AND school_id IS NOT DISTINCT FROM :s"""),
                        {'u': str(r['user_id']), 's': str(ev['school_id'] or r['target_school_id']) if (ev['school_id'] or r['target_school_id']) else None}).all()]
                decisions = decide(channels=list(ev['channels']), kind=ev['kind'], settings=settings, phone=r['phone_e164'],
                                   email=r['email'], sms_reserved=ev['sms_segments_reserved'] > 0, push_devices=devices, seen_phones=seen)
                for d in decisions:
                    if d.channel == 'SMS' and d.send:
                        sms_recipients += 1
                    c.execute(text("""INSERT INTO communication_deliveries(school_id, message_id, recipient_id, channel, recipient_ref, destination,
                            status, estimated_segments, wallet_state, last_error_code, cancelled_at, queued_at)
                        VALUES (:s, :m, :r, :ch, :ref, :dest, :st, :seg, :ws, :err, :cancel, now())
                        ON CONFLICT (message_id, channel, destination) DO NOTHING"""),
                        {'s': str(ev['school_id']) if ev['school_id'] else None, 'm': str(ev['id']), 'r': str(r['id']), 'ch': d.channel,
                         'ref': str(r['recipient_ref']), 'dest': d.destination or f"skip:{r['id']}", 'st': 'QUEUED' if d.send else 'CANCELLED',
                         'seg': None, 'ws': None, 'err': d.reason, 'cancel': None if d.send else 'now'})
            if sms_recipients:
                units_each = sms_units(ev['body'])
                c.execute(text("""UPDATE communication_deliveries SET estimated_segments=:u, wallet_state='RESERVED'
                    WHERE message_id=:m AND channel='SMS' AND status='QUEUED'"""), {'u': units_each, 'm': str(ev['id'])})
            # Credits reserved but not used by the policy (setting switched off, duplicate, invalid number) go back.
            unused = ev['sms_segments_reserved'] - units_each * sms_recipients
            if unused > 0 and ev['school_id']:
                wallet_apply(c, school_id=ev['school_id'], movement='RELEASE', quantity=unused, key=f"release-dispatch:{ev['id']}",
                             source_type='communication_message', source_id=ev['id'], reason="Crédits non utilisés par la politique d'envoi")
            c.execute(text("UPDATE communication_messages SET dispatched_at=now() WHERE id=:m"), {'m': str(ev['id'])})
            done += 1
    return done


# ================================================================================================ 2. deliver
def _claim(engine, delivery_id=None):
    token = str(uuid4())
    with engine.begin() as c:
        params = {'token': token, 'lease': LEASE_SECONDS}
        extra = ''
        if delivery_id:
            extra = ' AND d.id=:did'
            params['did'] = delivery_id
        row = c.execute(text(f"""SELECT d.id, d.school_id, d.destination, d.attempts, d.channel, d.estimated_segments, d.wallet_state,
                d.recipient_id, d.message_id, m.body, m.subject, m.kind, m.template_code, m.link_path,
                r.display_name, r.secret_ciphertext, r.target_school_id, s.enabled, s.sms_enabled, s.email_enabled, s.push_enabled
            FROM communication_deliveries d
            JOIN communication_messages m ON m.id=d.message_id
            LEFT JOIN communication_recipients r ON r.id=d.recipient_id
            LEFT JOIN communication_settings s ON s.school_id=d.school_id
            WHERE (d.status IN ('QUEUED','FAILED_RETRYABLE') OR (d.status='PROCESSING' AND d.locked_until<now()))
              AND (d.next_attempt_at IS NULL OR d.next_attempt_at<=now())
              AND (d.locked_until IS NULL OR d.locked_until<now()) {extra}
              AND (d.school_id IS NULL OR EXISTS (SELECT 1 FROM schools sc WHERE sc.id=d.school_id AND sc.status='ACTIVE'))
            ORDER BY d.created_at, d.id FOR UPDATE OF d SKIP LOCKED LIMIT 1"""), params).mappings().first()
        if not row:
            return None
        c.execute(text("""UPDATE communication_deliveries SET processing_token=:token, locked_until=now()+(:lease||' seconds')::interval,
            status='PROCESSING', last_attempt_at=now(), first_attempt_at=coalesce(first_attempt_at, now()) WHERE id=:id"""),
            {'token': token, 'lease': LEASE_SECONDS, 'id': row['id']})
        school = None
        school_ref = row['school_id'] or row.get('target_school_id')
        if school_ref:
            school = c.execute(text("SELECT name FROM schools WHERE id=:s"), {'s': str(school_ref)}).scalar_one_or_none()
        out = dict(row)
        out['school_name'] = school
        return out, token


def _channel_enabled(row) -> bool:
    if row['kind'] in ('ACCOUNT', 'PLATFORM'):
        return row['channel'] in ('EMAIL', 'PUSH')
    if not row.get('enabled'):
        return False
    return {'SMS': bool(row.get('sms_enabled')), 'EMAIL': bool(row.get('email_enabled')), 'PUSH': row.get('push_enabled') is not False}.get(row['channel'], False)


async def _send(cfg, engine, row) -> ports.SendResult | None:
    """Calls the provider port. External I/O happens outside the PostgreSQL transaction / row lock."""
    ch = row['channel']
    if ch == 'SMS':
        p = build_sms_provider(cfg)
        return await p.send_sms(to_e164=row['destination'], body=row['body']) if p else None
    if ch == 'EMAIL':
        p = build_email_provider(cfg)
        if not p:
            return None
        link = None
        if row.get('secret_ciphertext'):
            link = cipher(cfg, DELIVERY_SECRET).decrypt(row['secret_ciphertext'], owner=str(row['recipient_id']))
        ttl = (f"{cfg.invitation_ttl_hours} heures" if row['template_code'] == 'ACCOUNT_INVITATION'
               else f"{cfg.password_reset_ttl_minutes} minutes" if row['template_code'] == 'ACCOUNT_PASSWORD_RESET' else None)
        content = render_email(row['template_code'], recipient_name=row.get('display_name'), school_name=row.get('school_name'),
                               subject=row.get('subject'), body=row['body'], link=link, ttl_label=ttl)
        return await p.send_email(to=row['destination'], content=content)
    if ch == 'PUSH':
        p = build_push_provider(cfg)
        if not p:
            return None
        with engine.begin() as c:
            sub = c.execute(text("SELECT id, token_ciphertext FROM push_subscriptions WHERE id=:id AND revoked_at IS NULL"),
                            {'id': row['destination']}).mappings().first()
        if not sub or not sub['token_ciphertext']:
            return ports.SendResult(ports.INVALID_TOKEN, error_code='PUSH_DEVICE_REVOKED')
        token = cipher(cfg, PUSH_TOKEN).decrypt(sub['token_ciphertext'], owner=str(sub['id']))
        # N1 rule: a push carries a title and an internal link, never the message body or personal data (lock screens).
        title = (row.get('subject') or row.get('school_name') or 'EduSync')[:120]
        text_ = 'Cet appareil recevra les notifications de votre école.' if row['kind'] == 'PUSH_TEST' else 'Ouvrez EduSync pour lire le message.'
        return await p.send_push(token=token, title=title, body=text_, link=row.get('link_path') or '/',
                                 data={'message_id': str(row['message_id'])})
    return ports.SendResult(ports.PERMANENT, error_code='CHANNEL_UNSUPPORTED')


def _wallet(c, row, movement: str, quantity: int | None) -> None:
    if row['channel'] != 'SMS' or row.get('wallet_state') != 'RESERVED' or not row['school_id'] or not quantity:
        return
    wallet_apply(c, school_id=row['school_id'], movement=movement, quantity=quantity, key=f"{movement.lower()}:{row['id']}",
                 source_type='communication_delivery', source_id=row['id'], provider_message_id=row.get('provider_message_id'))
    c.execute(text("UPDATE communication_deliveries SET wallet_state=:w WHERE id=:id"),
              {'w': 'CONSUMED' if movement == 'CONSUMPTION' else 'RELEASED', 'id': row['id']})


def _wipe_secret_if_final(c, row) -> None:
    if row.get('recipient_id') and row.get('secret_ciphertext'):
        c.execute(text("""UPDATE communication_recipients SET secret_ciphertext=NULL WHERE id=:r AND NOT EXISTS (
            SELECT 1 FROM communication_deliveries d WHERE d.recipient_id=:r AND d.status IN ('QUEUED','PROCESSING','FAILED_RETRYABLE'))"""),
                  {'r': str(row['recipient_id'])})


def _finish(engine, row, token, result) -> str:
    attempts = int(row['attempts']) + 1
    with engine.begin() as c:
        if result is not None and result.outcome == ports.SENT:
            row = {**row, 'provider_message_id': result.provider_message_id}
            n = c.execute(text("""UPDATE communication_deliveries SET status='SENT', attempts=:a, sent_at=now(), provider_message_id=:pm,
                provider_code=:pc, segments_billed=CASE WHEN channel='SMS' THEN estimated_segments END,
                last_error_code=NULL, last_error_detail=NULL, next_attempt_at=NULL, locked_until=NULL, processing_token=NULL
                WHERE id=:id AND processing_token=:t"""),
                {'a': attempts, 'pm': result.provider_message_id, 'pc': row['channel'].lower(), 'id': row['id'], 't': token}).rowcount
            if n:
                _wallet(c, row, 'CONSUMPTION', row.get('estimated_segments'))
                if row['channel'] == 'PUSH':
                    c.execute(text("UPDATE push_subscriptions SET last_used_at=now(), last_error_code=NULL WHERE id=:id"), {'id': row['destination']})
                _wipe_secret_if_final(c, row)
            return 'SENT'
        code = 'PROVIDER_NOT_CONFIGURED' if result is None else ports.safe_error(result.error_code or result.outcome)
        retryable = result is None or result.outcome == ports.RETRYABLE
        if retryable and attempts < MAX_ATTEMPTS:
            delay = backoff_seconds(attempts, None if result is None else result.retry_after_seconds)
            c.execute(text("""UPDATE communication_deliveries SET status='FAILED_RETRYABLE', attempts=:a,
                next_attempt_at=now()+(:d||' seconds')::interval, last_error_code=:e, locked_until=NULL, processing_token=NULL
                WHERE id=:id AND processing_token=:t"""), {'a': attempts, 'd': delay, 'e': code, 'id': row['id'], 't': token})
            return 'FAILED_RETRYABLE'
        n = c.execute(text("""UPDATE communication_deliveries SET status='FAILED_PERMANENT', attempts=:a, failed_at=now(), last_error_code=:e,
            next_attempt_at=NULL, locked_until=NULL, processing_token=NULL WHERE id=:id AND processing_token=:t"""),
            {'a': attempts, 'e': code, 'id': row['id'], 't': token}).rowcount
        if n:
            _wallet(c, row, 'RELEASE', row.get('estimated_segments'))
            if row['channel'] == 'PUSH' and result is not None and result.outcome == ports.INVALID_TOKEN:
                # A token declared invalid by the provider is deactivated; the user's other devices are untouched.
                c.execute(text("""UPDATE push_subscriptions SET revoked_at=coalesce(revoked_at, now()), revoked_reason=coalesce(revoked_reason, 'PROVIDER_INVALID_TOKEN'),
                    last_error_code=:e, last_error_at=now() WHERE id=:id"""), {'e': code, 'id': row['destination']})
            _wipe_secret_if_final(c, row)
        return 'FAILED_PERMANENT'


def _cancel(engine, row, token, reason: str) -> str:
    with engine.begin() as c:
        n = c.execute(text("""UPDATE communication_deliveries SET status='CANCELLED', cancelled_at=now(), last_error_code=:e,
            locked_until=NULL, processing_token=NULL WHERE id=:id AND processing_token=:t"""), {'e': reason, 'id': row['id'], 't': token}).rowcount
        if n:
            _wallet(c, row, 'RELEASE', row.get('estimated_segments'))
            _wipe_secret_if_final(c, row)
    return 'CANCELLED'


class SmsThrottle:
    """Orange documents 5 SMS per second: at most cfg.orange_sms_max_tps sends per second from one worker process."""
    def __init__(self, tps: float):
        self.interval = 1.0 / max(0.1, tps)
        self.last = 0.0

    def wait(self) -> None:
        delay = self.last + self.interval - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self.last = time.monotonic()


def run_once(cfg, r, engine, throttle: SmsThrottle | None = None) -> bool:
    # Redis is a hint, never the durable scheduler. If the hint is lost, DB due-row polling recovers it.
    delivery_id = None
    try:
        job = r.brpop('edusync:communications', timeout=1) if r is not None else None
        if job:
            try:
                delivery_id = json.loads(job[1]).get('delivery_id')
            except Exception:
                delivery_id = None
    except redis.RedisError:pass
    claimed = _claim(engine, delivery_id) or (_claim(engine) if delivery_id else None)
    if not claimed:
        return False
    row, token = claimed
    if not _channel_enabled(row):
        _cancel(engine, row, token, 'CHANNEL_DISABLED')
        return True
    if row['channel'] == 'SMS' and throttle is not None:
        throttle.wait()
    try:
        result = asyncio.run(_send(cfg, engine, row))
    except Exception as exc:  # noqa: BLE001 — an adapter bug is a retryable failure, never a lost message
        log.warning('provider call failed channel=%s error=%s', row['channel'], type(exc).__name__)
        result = ports.SendResult(ports.RETRYABLE, error_code='ADAPTER_ERROR')
    _finish(engine, row, token, result)
    return True


# ================================================================================================ receipts
def apply_receipt(engine, provider_code: str, receipt) -> int:
    """SENT -> DELIVERED / FAILED only from a provider receipt; a later DELIVERED receipt can upgrade a receipt failure
    (Orange: DeliveryImpossible may be followed by delivery). Idempotent: replaying the same receipt changes nothing."""
    with engine.begin() as c:
        if receipt.status == 'DELIVERED':
            return c.execute(text("""UPDATE communication_deliveries SET status='DELIVERED', delivered_at=coalesce(delivered_at, now()), last_error_code=NULL
                WHERE provider_code=:p AND provider_message_id=:m AND (status='SENT' OR (status='FAILED_PERMANENT' AND last_error_code='UNDELIVERABLE'))"""),
                {'p': provider_code, 'm': receipt.provider_message_id}).rowcount
        if receipt.status == 'FAILED':
            return c.execute(text("""UPDATE communication_deliveries SET status='FAILED_PERMANENT', failed_at=now(), last_error_code=:e
                WHERE provider_code=:p AND provider_message_id=:m AND status='SENT'"""),
                {'p': provider_code, 'm': receipt.provider_message_id, 'e': receipt.error_code or 'UNDELIVERABLE'}).rowcount
    return 0


def process_receipts(engine, limit: int = 200) -> int:
    """Applies the receipts stored by the provider webhook (provider_receipts), oldest first, exactly once."""
    from edusync.shared.messaging.ports import DeliveryReceipt
    with engine.begin() as c:
        rows = c.execute(text("""SELECT id, provider_code, provider_message_id, provider_status, status FROM provider_receipts
            WHERE applied_at IS NULL ORDER BY received_at, id FOR UPDATE SKIP LOCKED LIMIT :n"""), {'n': limit}).mappings().all()
        ids = [str(r['id']) for r in rows]
    changed = 0
    for r in rows:
        if r['status'] in ('DELIVERED', 'FAILED'):
            changed += apply_receipt(engine, r['provider_code'], DeliveryReceipt(r['provider_message_id'], r['status'], r['provider_status'],
                                                                                 'UNDELIVERABLE' if r['status'] == 'FAILED' else None))
    if ids:
        with engine.begin() as c:
            c.execute(text("UPDATE provider_receipts SET applied_at=now() WHERE id = ANY(CAST(:ids AS uuid[]))"), {'ids': ids})
    return changed


def run():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    cfg = Settings()
    r = redis.Redis.from_url(cfg.redis_url, decode_responses=True, socket_connect_timeout=3, socket_timeout=3)
    engine = create_engine(worker_url(cfg), pool_pre_ping=True, pool_recycle=1800)
    throttle = SmsThrottle(cfg.orange_sms_max_tps)
    last_receipts = 0.0
    last_health = -1e9
    while True:
        try:
            beat(r, 'communications')
            if provider_health.due(r, last_health):
                # Real provider checks (no message sent), every 5 min or on request from the cockpit. A failing check
                # never blocks the deliveries: it is logged and retried at the next interval.
                last_health = time.monotonic()
                try:
                    provider_health.run_and_store(cfg, r)
                except Exception:  # noqa: BLE001
                    log.exception('provider health check failed')
            if time.monotonic() - last_receipts >= 10:
                process_receipts(engine)
                last_receipts = time.monotonic()
            dispatched = dispatch_pending(cfg, engine)
            if not run_once(cfg, r, engine, throttle) and not dispatched:
                time.sleep(.5)
        except Exception:
            log.exception('communications worker iteration failed')
            time.sleep(2)


if __name__ == '__main__':
    run()
