"""REAL Orange SMS probe (SMS_ORANGE_INTEGRATION.md). Requires, in the environment / secret store (never printed):
EDUSYNC_SMS_PROVIDER=orange, EDUSYNC_ORANGE_SMS_CLIENT_ID, EDUSYNC_ORANGE_SMS_CLIENT_SECRET, EDUSYNC_ORANGE_SMS_SENDER_ADDRESS
(+ optional EDUSYNC_ORANGE_SMS_SENDER_NAME) and the operator's own test number EDUSYNC_PROBE_SMS_TO (E.164).
Checks: OAuth v3 token, contract / balance (GET /sms/admin/v1/contracts), one real SMS (201 + message id), invalid
number classified permanent. Reception on the handset and the delivery receipt are confirmed by a human."""
import asyncio
import os

import httpx

from provider_probe_common import check, finish, settings

cfg = settings()
checks: list[dict] = []
missing = [k for k, v in (("EDUSYNC_SMS_PROVIDER=orange", cfg.sms_provider == "orange"), ("EDUSYNC_ORANGE_SMS_CLIENT_ID", cfg.orange_sms_client_id),
                          ("EDUSYNC_ORANGE_SMS_CLIENT_SECRET", cfg.orange_sms_client_secret), ("EDUSYNC_ORANGE_SMS_SENDER_ADDRESS", cfg.orange_sms_sender_address),
                          ("EDUSYNC_PROBE_SMS_TO", os.environ.get("EDUSYNC_PROBE_SMS_TO"))) if not v]
if missing:
    check(checks, "Secrets Orange et numéro de test fournis", "EXTERNAL_REQUIRED", ", ".join(missing))
    finish("sms_provider_probe", "EXTERNAL_REQUIRED", checks)

from edusync.shared.messaging.sms_orange import OrangeSmsProvider  # noqa: E402

p = OrangeSmsProvider(client_id=cfg.orange_sms_client_id, client_secret=cfg.orange_sms_client_secret, sender_address=cfg.orange_sms_sender_address,
                      sender_name=cfg.orange_sms_sender_name, api_base=cfg.orange_sms_api_base, redis_url=None)


async def contracts():
    async with httpx.AsyncClient(timeout=20) as c:
        token = await p._token(c, force=True)
        r = await c.get(f"{cfg.orange_sms_api_base.rstrip('/')}/sms/admin/v1/contracts", headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
        return r.status_code, (r.json() if r.content else None)


try:
    status, data = asyncio.run(contracts())
    check(checks, "OAuth v3 client credentials : jeton obtenu", "REAL_ACCEPTED")
    rows = data if isinstance(data, list) else (data or {}).get("contracts", []) if isinstance(data, dict) else []
    units = [(x.get("country"), x.get("availableUnits"), x.get("status"), x.get("expirationDate")) for x in rows if isinstance(x, dict)]
    check(checks, "Contrat Orange : pays, unités disponibles, statut, expiration", "REAL_ACCEPTED" if status == 200 else "REAL_FAILED", units or status)
except Exception as exc:  # noqa: BLE001
    check(checks, "OAuth v3 client credentials : jeton obtenu", "REAL_FAILED", type(exc).__name__)
    finish("sms_provider_probe", "REAL_FAILED", checks)

to = os.environ["EDUSYNC_PROBE_SMS_TO"].strip()
r = asyncio.run(p.send_sms(to_e164=to, body="Test EduSync : SMS reel de certification. Merci de confirmer la reception."))
check(checks, "SMS réel accepté par Orange (201, identifiant de message)", "REAL_ACCEPTED" if r.outcome == "SENT" else "REAL_FAILED",
      r.provider_message_id or r.error_code)
bad = asyncio.run(p.send_sms(to_e164="+0", body="x"))
check(checks, "Numéro invalide refusé sans appel facturé", "REAL_ACCEPTED" if bad.outcome == "INVALID_DESTINATION" else "REAL_FAILED", bad.outcome)
check(checks, "Réception sur le téléphone et accusé de livraison (DeliveredToTerminal)", "HUMAN_CONFIRMATION_REQUIRED",
      "À constater sur le téléphone de test ; l'accusé arrive sur le callback déclaré à Orange")
finish("sms_provider_probe", "REAL_ACCEPTED" if r.outcome == "SENT" else "REAL_FAILED", checks)
