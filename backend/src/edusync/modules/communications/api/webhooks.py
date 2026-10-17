"""Provider callbacks (SMS_ORANGE_INTEGRATION.md §Accusés de réception).

Orange delivers SMS delivery receipts to a callback URL declared through its web form; the only protection it
documents is its source IP address (no signature). EduSync therefore requires BOTH an unguessable path secret
(EDUSYNC_ORANGE_SMS_DR_SECRET, compared in constant time) and, when configured, the source IPs given by Orange
(EDUSYNC_ORANGE_SMS_DR_ALLOWED_IPS). The receipt is stored idempotently and applied by the communications worker:
replaying the same receipt changes nothing. Orange expects HTTP 200 to acknowledge.
"""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text

from edusync.bootstrap.dependencies import get_services
from edusync.bootstrap.services import AppServices
from edusync.shared.messaging.sms_orange import parse_delivery_receipt

router = APIRouter(tags=['provider-webhooks'])


@router.post('/orange/sms-dr/{secret}')
async def orange_delivery_receipt(secret: str, request: Request, services: AppServices = Depends(get_services)):
    cfg = services.settings
    expected = cfg.orange_sms_dr_secret or ''
    if len(expected) < 24 or not hmac.compare_digest(secret.encode(), expected.encode()):
        raise HTTPException(404, 'Not Found')
    allowed = {ip.strip() for ip in (cfg.orange_sms_dr_allowed_ips or '').split(',') if ip.strip()}
    client = request.client.host if request.client else ''
    if allowed and client not in allowed:
        raise HTTPException(403, 'Forbidden')
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(400, 'Invalid JSON') from exc
    receipt = parse_delivery_receipt(payload if isinstance(payload, dict) else {})
    if receipt is None:
        raise HTTPException(400, 'Invalid delivery receipt')
    with services.platform_db.platform_transaction() as c:
        c.execute(text("""INSERT INTO provider_receipts(provider_code, provider_message_id, provider_status, status)
            VALUES ('sms', :m, :ps, :st) ON CONFLICT (provider_code, provider_message_id, provider_status) DO NOTHING"""),
                  {'m': receipt.provider_message_id, 'ps': receipt.provider_status[:64], 'st': receipt.status})
    return {'status': 'accepted'}
