"""School Communication Center API (EXTERNAL_MESSAGING_ARCHITECTURE.md).

Channel configuration, SMS wallet (read), audience preview with SMS cost, confirmed sending, history and retries.
Sending never calls a provider: the use case records the message, its recipients, the SMS credit reservation and a
COMMUNICATION_REQUESTED outbox event in one transaction; the communications worker sends after commit ('QUEUED').
External channels are optional and fail closed: 'Canal externe non activé' when the school did not enable them.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from edusync.bootstrap.dependencies import get_services, require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.modules.communications.application.messaging import (MAX_SMS_CHARS, preview as compute_preview, request_message,
                                                                   resolve_audience, sms_units)
from edusync.modules.communications.application.wallet import wallet_apply
from edusync.modules.communications.domain.models import TEMPLATE_VARIABLES, render_template, sms_segments, validate_template
from edusync.shared.application.context import ActorContext
from edusync.shared.messaging.factory import channel_status

router = APIRouter(tags=['communications'])

AUDIENCE_CAPS = {'INDIVIDUAL': 'communications.send.individual', 'CLASS': 'communications.send.class',
                 'SECTION': 'communications.send.section', 'SCHOOL': 'communications.send.all_parents'}


def need(a, p):
    try:
        a.require(p)
    except PermissionError as e:
        raise HTTPException(403, str(e)) from e


def _audit(c, actor, action, entity_type, entity_id, detail: dict | None = None):
    import json
    c.execute(text("""INSERT INTO audit_events(school_id,actor_user_id,membership_id,action,entity_type,entity_id,source,new_json)
        VALUES(:sid,:uid,:mid,:a,:t,:id,'WEB',CAST(:j AS jsonb))"""),
        {'sid': str(actor.school_id), 'uid': str(actor.user_id), 'mid': str(actor.membership_id), 'a': action, 't': entity_type,
         'id': str(entity_id) if entity_id else None, 'j': json.dumps(detail or {})})


def _settings(c, school_id) -> dict:
    row = c.execute(text('SELECT * FROM communication_settings WHERE school_id=:sid'), {'sid': str(school_id)}).mappings().first()
    return dict(row) if row else {'enabled': False, 'in_app_enabled': True, 'sms_enabled': False, 'email_enabled': False,
                                  'push_enabled': True, 'sms_low_balance_threshold': 50, 'version': 0}


def _wallet(c, school_id) -> dict:
    w = c.execute(text('SELECT balance, reserved FROM school_sms_wallets WHERE school_id=:s'), {'s': str(school_id)}).mappings().first()
    return {'balance': w['balance'] if w else 0, 'reserved': w['reserved'] if w else 0}


# ------------------------------------------------------------------------------------------------ readiness & settings
@router.get('/readiness')
def readiness(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    # Read by composers (communications.read) and by the school administrator who configures the channels.
    if 'notifications.internal.configure' not in actor.permissions:
        need(actor, 'communications.read')
    platform = channel_status(services.settings)
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        s = _settings(c, actor.school_id)
        w = _wallet(c, actor.school_id)
    available = w['balance'] - w['reserved']
    ready = lambda ch: platform[ch]['state'] in ('CONFIGURED', 'SIMULATED')  # noqa: E731
    return {'enabled': bool(s['enabled']), 'in_app_enabled': bool(s.get('in_app_enabled', True)),
            'sms_enabled': bool(s['sms_enabled']), 'email_enabled': bool(s['email_enabled']), 'push_enabled': s.get('push_enabled') is not False,
            'sms_low_balance_threshold': s.get('sms_low_balance_threshold', 50), 'version': s.get('version', 0),
            'platform': {ch: {'state': platform[ch]['state'], 'available': ready(ch)} for ch in ('sms', 'email', 'push')},
            'wallet': {**w, 'available': available, 'low': available <= int(s.get('sms_low_balance_threshold', 50) or 0)},
            'external_ready': bool(s['enabled'] and ((s['sms_enabled'] and ready('sms')) or (s['email_enabled'] and ready('email'))
                                                    or (s.get('push_enabled') is not False and ready('push')))),
            'max_sms_characters': MAX_SMS_CHARS}


class SettingsBody(BaseModel):
    enabled: bool
    sms_enabled: bool
    email_enabled: bool
    push_enabled: bool = True
    sms_low_balance_threshold: int = Field(default=50, ge=0, le=1_000_000)
    expected_version: int = Field(ge=0)


@router.put('/settings')
def save_settings(b: SettingsBody, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """School switch per channel. A disabled channel never blocks finance, schooling or cash: messages just skip it."""
    need(actor, 'notifications.internal.configure')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        row = c.execute(text("""INSERT INTO communication_settings(school_id, enabled, sms_enabled, email_enabled, push_enabled, sms_low_balance_threshold)
            VALUES (:s, :e, :sms, :mail, :push, :th)
            ON CONFLICT (school_id) DO UPDATE SET enabled=EXCLUDED.enabled, sms_enabled=EXCLUDED.sms_enabled, email_enabled=EXCLUDED.email_enabled,
              push_enabled=EXCLUDED.push_enabled, sms_low_balance_threshold=EXCLUDED.sms_low_balance_threshold, updated_at=now(),
              version=communication_settings.version+1
            WHERE communication_settings.version=:v RETURNING version"""),
            {'s': str(actor.school_id), 'e': b.enabled, 'sms': b.sms_enabled, 'mail': b.email_enabled, 'push': b.push_enabled,
             'th': b.sms_low_balance_threshold, 'v': b.expected_version}).first()
        if not row:
            raise HTTPException(409, 'Réglages modifiés entre-temps : rechargez la page')
        _audit(c, actor, 'COMMUNICATION_SETTINGS_UPDATED', 'CommunicationSettings', actor.school_id, b.model_dump(exclude={'expected_version'}))
    return {'version': row[0]}


# ------------------------------------------------------------------------------------------------ SMS wallet (read)
@router.get('/wallet')
def wallet(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    need(actor, 'communications.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        w = _wallet(c, actor.school_id)
        s = _settings(c, actor.school_id)
        used = c.execute(text("""SELECT coalesce(sum(quantity),0) FROM school_sms_ledger WHERE school_id=:s AND movement_type='CONSUMPTION'
            AND created_at >= date_trunc('month', now())"""), {'s': str(actor.school_id)}).scalar_one()
    available = w['balance'] - w['reserved']
    return {**w, 'available': available, 'threshold': s.get('sms_low_balance_threshold', 50),
            'low': available <= int(s.get('sms_low_balance_threshold', 50) or 0), 'consumed_this_month': int(used), 'unit': 'SMS_SEGMENT'}


@router.get('/wallet/ledger')
def wallet_ledger(limit: int = 50, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    need(actor, 'communications.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        rows = c.execute(text("""SELECT id, movement_type, direction, quantity, balance_after, reserved_after, source_type, reference, reason, created_at
            FROM school_sms_ledger WHERE school_id=:s ORDER BY created_at DESC, id DESC LIMIT :n"""),
            {'s': str(actor.school_id), 'n': max(1, min(limit, 200))}).mappings().all()
    return {'items': [dict(r) for r in rows]}


# ------------------------------------------------------------------------------------------------ compose: preview + send
class Draft(BaseModel):
    kind: str = Field(default='COMMUNIQUE', pattern='^[A-Z_]{3,24}$')
    audience_type: str = Field(pattern='^(INDIVIDUAL|CLASS|SECTION|SCHOOL)$')
    audience_ref: UUID | None = None
    subject: str | None = Field(default=None, max_length=180)
    body: str = Field(min_length=1, max_length=4000)
    channel: str = 'IN_APP'                                   # historical single channel
    channels: list[str] = Field(default_factory=list, max_length=3)
    idempotency_key: str = Field(min_length=8, max_length=180)
    confirm_fingerprint: str | None = Field(default=None, max_length=64)

    def wanted(self) -> list[str]:
        chans = [c.upper() for c in (self.channels or [self.channel])]
        return list(dict.fromkeys(chans))


def _authorize(actor, b: Draft, channels: list[str]) -> str:
    need(actor, 'communications.compose')
    cap = AUDIENCE_CAPS[b.audience_type.upper()]
    need(actor, cap)
    if 'SMS' in channels:
        need(actor, 'communications.sms.send' if b.audience_type.upper() == 'INDIVIDUAL' else 'communications.sms.bulk_send')
    return cap


def _check_channels(s: dict, channels: list[str], platform: dict) -> None:
    for ch in channels:
        if ch not in ('SMS', 'EMAIL', 'PUSH'):
            raise HTTPException(422, f'Canal inconnu : {ch}')
        if not s.get('enabled') or (ch == 'SMS' and not s.get('sms_enabled')) or (ch == 'EMAIL' and not s.get('email_enabled')) \
                or (ch == 'PUSH' and s.get('push_enabled') is False):
            raise HTTPException(409, 'Canal externe non activé pour cette école')
        if ch == 'SMS' and platform['sms']['state'] not in ('CONFIGURED', 'SIMULATED'):
            raise HTTPException(409, 'Fournisseur SMS ou expéditeur non configuré')
        if ch == 'EMAIL' and platform['email']['state'] not in ('CONFIGURED', 'SIMULATED'):
            raise HTTPException(409, 'Fournisseur e-mail non configuré sur la plateforme')


@router.post('/preview')
def preview(b: Draft, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """Number of recipients, invalid / duplicate numbers removed, SMS units, wallet balance after sending."""
    channels = [c for c in b.wanted() if c != 'IN_APP']
    if not channels:
        raise HTTPException(422, 'Choisissez au moins un canal : SMS, e-mail ou notification push')
    cap = _authorize(actor, b, channels)
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        _check_channels(_settings(c, actor.school_id), channels, channel_status(services.settings))
        try:
            recipients = resolve_audience(c, actor, actor.school_id, b.audience_type, b.audience_ref, cap)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        except PermissionError as e:
            raise HTTPException(403, str(e)) from e
        return compute_preview(c, actor.school_id, recipients, channels, b.body)


@router.post('/send')
def send(b: Draft, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    channels = [c for c in b.wanted() if c != 'IN_APP']
    cap = _authorize(actor, b, channels)
    if not channels:
        raise HTTPException(422, 'Choisissez au moins un canal : SMS, e-mail ou notification push')
    try:
        with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
            _check_channels(_settings(c, actor.school_id), channels, channel_status(services.settings))
            try:
                recipients = resolve_audience(c, actor, actor.school_id, b.audience_type, b.audience_ref, cap)
            except ValueError as e:
                raise HTTPException(422, str(e)) from e
            except PermissionError as e:
                raise HTTPException(403, str(e)) from e
            if not recipients:
                raise HTTPException(409, 'Aucun destinataire dans cette audience')
            figures = compute_preview(c, actor.school_id, recipients, channels, b.body)
            if 'SMS' in channels:
                if figures['too_long']:
                    raise HTTPException(422, f'SMS limité à {MAX_SMS_CHARS} caractères')
                # Confirmation is bound to the previewed audience, text and cost (never trusted from the client).
                if b.confirm_fingerprint != figures['fingerprint']:
                    raise HTTPException(409, 'L’aperçu a changé : vérifiez de nouveau les destinataires et le coût avant de confirmer')
                if not figures['sufficient']:
                    raise HTTPException(409, f"Crédit SMS insuffisant : {figures['sms_units']} nécessaires, {figures['wallet_available']} disponibles")
            out = request_message(c, school_id=actor.school_id, kind=b.kind, channels=channels, body=b.body, recipients=recipients,
                                  idempotency_key=b.idempotency_key, created_by=actor.user_id, subject=b.subject,
                                  audience_type=b.audience_type, audience_ref=b.audience_ref)
            if not out['replayed']:
                _audit(c, actor, 'COMMUNICATION_SMS_BULK_REQUESTED' if 'SMS' in channels and b.audience_type != 'INDIVIDUAL' else 'COMMUNICATION_REQUESTED',
                       'CommunicationMessage', out['id'], {'channels': channels, 'audience': b.audience_type, 'recipients': out['recipients'],
                                                           'sms_units_reserved': out['sms_units_reserved']})
    except DBAPIError as e:
        if 'SMS_INSUFFICIENT_CREDIT' in str(e.orig):
            raise HTTPException(409, 'Crédit SMS insuffisant') from e
        raise
    return {'id': out['id'], 'status': 'QUEUED', 'channels': channels, 'recipients': out['recipients'],
            'sms_units_reserved': out['sms_units_reserved'], 'replayed': out['replayed'],
            'estimated_segments': sms_units(b.body) if 'SMS' in channels else None}


# ------------------------------------------------------------------------------------------------ history
@router.get('/history')
def history(limit: int = 50, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    need(actor, 'communications.history.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        rows = c.execute(text("""SELECT m.id, m.kind, m.subject, m.audience_type, m.channels, m.recipient_count, m.sms_segments_reserved,
                m.created_at, m.dispatched_at, u.full_name AS author,
                coalesce(jsonb_object_agg(x.channel || ':' || x.status, x.n) FILTER (WHERE x.channel IS NOT NULL), '{}'::jsonb) AS counts,
                coalesce(sum(x.billed),0)::int AS sms_units_billed,
                (array_agg(x.err) FILTER (WHERE x.err IS NOT NULL))[1:3] AS errors
            FROM communication_messages m
            LEFT JOIN users u ON u.id=m.created_by
            LEFT JOIN LATERAL (SELECT d.channel, d.status, count(*) n, sum(d.segments_billed) billed,
                    max(d.last_error_code) FILTER (WHERE d.status IN ('FAILED_PERMANENT','FAILED_RETRYABLE')) err
                FROM communication_deliveries d WHERE d.message_id=m.id AND d.school_id=m.school_id GROUP BY d.channel, d.status) x ON true
            WHERE m.school_id=:sid GROUP BY m.id, u.full_name ORDER BY m.created_at DESC LIMIT :n"""),
            {'sid': str(actor.school_id), 'n': max(1, min(limit, 200))}).mappings().all()
    return {'items': [dict(r) for r in rows]}


@router.get('/history/{message_id}/deliveries')
def deliveries(message_id: UUID, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    need(actor, 'communications.history.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        rows = c.execute(text("""SELECT d.id, d.channel, d.status, d.attempts, d.last_error_code, d.estimated_segments, d.segments_billed,
                d.sent_at, d.delivered_at, d.failed_at, d.cancelled_at, r.display_name,
                CASE WHEN d.channel='PUSH' THEN 'appareil' ELSE d.destination END AS destination
            FROM communication_deliveries d
            JOIN communication_messages m ON m.id=d.message_id AND m.school_id=d.school_id
            LEFT JOIN communication_recipients r ON r.id=d.recipient_id AND r.school_id=d.school_id AND r.message_id=d.message_id
            WHERE d.message_id=:m AND d.school_id=:s ORDER BY r.display_name NULLS LAST, d.channel LIMIT 2000"""),
            {'m': str(message_id), 's': str(actor.school_id)}).mappings().all()
    return {'items': [{**dict(r), 'destination': None if str(r['destination'] or '').startswith('skip:') else r['destination']} for r in rows]}


@router.post('/deliveries/{delivery_id}/retry')
def retry_delivery(delivery_id: UUID, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """Manual retry of a terminal failure. Idempotent: a delivery already queued/sent/delivered is left unchanged.
    An SMS retry reserves its credits again (no negative balance)."""
    need(actor, 'communications.delivery.retry')
    try:
        with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
            cur = c.execute(text('SELECT status, channel, estimated_segments, attempts FROM communication_deliveries WHERE id=:id AND school_id=:sid FOR UPDATE'),
                            {'id': str(delivery_id), 'sid': str(actor.school_id)}).mappings().first()
            if cur is None:
                raise HTTPException(404, 'Envoi introuvable')
            if cur['status'] != 'FAILED_PERMANENT':
                return {'status': cur['status'], 'requeued': False}
            if cur['channel'] == 'SMS' and cur['estimated_segments']:
                n = c.execute(text("SELECT count(*) FROM audit_events WHERE entity_id=:id AND action='COMMUNICATION_DELIVERY_RETRIED'"), {'id': str(delivery_id)}).scalar_one()
                wallet_apply(c, school_id=actor.school_id, movement='RESERVATION', quantity=cur['estimated_segments'],
                             key=f'reserve-retry:{delivery_id}:{n + 1}', actor=actor.user_id, source_type='communication_delivery',
                             source_id=delivery_id, reason='Nouvel essai manuel')
            c.execute(text("""UPDATE communication_deliveries SET status='QUEUED', attempts=0, next_attempt_at=NULL, last_error_code=NULL, failed_at=NULL,
                wallet_state=CASE WHEN channel='SMS' AND estimated_segments IS NOT NULL THEN 'RESERVED' ELSE wallet_state END
                WHERE id=:id AND school_id=:sid AND status='FAILED_PERMANENT'"""), {'id': str(delivery_id), 'sid': str(actor.school_id)})
            _audit(c, actor, 'COMMUNICATION_DELIVERY_RETRIED', 'CommunicationDelivery', delivery_id)
    except DBAPIError as e:
        if 'SMS_INSUFFICIENT_CREDIT' in str(e.orig):
            raise HTTPException(409, 'Crédit SMS insuffisant pour relancer cet envoi') from e
        raise
    return {'status': 'QUEUED', 'requeued': True}


# --- Templates (local closure 2026-10) ------------------------------------------------------------------------------
class TemplateBody(BaseModel):
    code: str = Field(min_length=2, max_length=96, pattern=r'^[A-Z0-9_]+$')
    label: str = Field(min_length=2, max_length=180)
    channel: str = Field(default='SMS', pattern='^(SMS|IN_APP|EMAIL|PUSH)$')
    body: str = Field(min_length=1, max_length=1000)


@router.get('/templates')
def list_templates(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    need(actor, 'communications.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        rows = c.execute(text('SELECT id,code,label,channel,body,enabled,version,updated_at FROM communication_templates WHERE school_id=:sid ORDER BY label'),
                         {'sid': str(actor.school_id)}).mappings().all()
    return {'items': [dict(r) for r in rows], 'variables': sorted(TEMPLATE_VARIABLES)}


@router.post('/templates', status_code=201)
def save_template(b: TemplateBody, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    need(actor, 'communications.templates.manage')
    try:
        validate_template(b.body)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        row = c.execute(text('''INSERT INTO communication_templates(school_id,code,label,channel,body) VALUES(:sid,:code,:label,:ch,:body)
            ON CONFLICT(school_id,code,channel) DO UPDATE SET label=EXCLUDED.label,body=EXCLUDED.body,updated_at=now(),version=communication_templates.version+1 RETURNING id,version'''),
            {'sid': str(actor.school_id), 'code': b.code, 'label': b.label, 'ch': b.channel, 'body': b.body}).mappings().one()
        _audit(c, actor, 'COMMUNICATION_TEMPLATE_SAVED', 'CommunicationTemplate', row['id'], {'code': b.code, 'version': row['version']})
    return {'id': str(row['id']), 'version': row['version']}


class PreviewBody(BaseModel):
    body: str = Field(min_length=1, max_length=1000)
    values: dict[str, str] = Field(default_factory=dict)


@router.post('/templates/preview')
def preview_template(b: PreviewBody, actor: ActorContext = Depends(require_school_actor)):
    need(actor, 'communications.compose')
    try:
        text_ = render_template(b.body, b.values)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {'text': text_, 'estimated_segments': sms_segments(text_), 'sms_units': sms_units(text_)}
