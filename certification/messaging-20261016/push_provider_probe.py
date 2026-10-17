"""REAL Firebase Cloud Messaging probe (PUSH_FCM_INTEGRATION.md). Requires (never printed): EDUSYNC_PUSH_PROVIDER=fcm, the
service account (EDUSYNC_FCM_SERVICE_ACCOUNT_FILE or _JSON), and a registration token of the operator's own test device
EDUSYNC_PROBE_PUSH_TOKEN (obtained by "Activer les notifications" on that device, read from the server only by the
operator). Checks: service account accepted, one real push accepted (message id), an invalid token classified
INVALID_TOKEN. Display in foreground / background, click and revocation are confirmed by a human on the device."""
import asyncio
import os

from provider_probe_common import check, finish, settings

cfg = settings()
checks: list[dict] = []
missing = [k for k, v in (("EDUSYNC_PUSH_PROVIDER=fcm", cfg.push_provider == "fcm"),
                          ("EDUSYNC_FCM_SERVICE_ACCOUNT_FILE|_JSON", cfg.fcm_service_account_file or cfg.fcm_service_account_json),
                          ("EDUSYNC_FCM_WEB_CONFIG_JSON", cfg.fcm_web_config_json), ("EDUSYNC_FCM_VAPID_PUBLIC_KEY", cfg.fcm_vapid_public_key),
                          ("EDUSYNC_PROBE_PUSH_TOKEN", os.environ.get("EDUSYNC_PROBE_PUSH_TOKEN"))) if not v]
if missing:
    check(checks, "Compte de service Firebase, configuration web et jeton d'appareil de test fournis", "EXTERNAL_REQUIRED", ", ".join(missing))
    finish("push_provider_probe", "EXTERNAL_REQUIRED", checks)

from edusync.shared.messaging.push_fcm import FcmPushProvider  # noqa: E402

try:
    p = FcmPushProvider(service_account_file=cfg.fcm_service_account_file, service_account_json=cfg.fcm_service_account_json)
    check(checks, "Compte de service Firebase accepté", "REAL_ACCEPTED")
except Exception as exc:  # noqa: BLE001
    check(checks, "Compte de service Firebase accepté", "REAL_FAILED", type(exc).__name__)
    finish("push_provider_probe", "REAL_FAILED", checks)
r = asyncio.run(p.send_push(token=os.environ["EDUSYNC_PROBE_PUSH_TOKEN"].strip(), title="Test EduSync", body="Notification réelle de certification.",
                            link="/", data={"message_id": "certification"}))
check(checks, "Push réel accepté par FCM (identifiant de message)", "REAL_ACCEPTED" if r.outcome == "SENT" else "REAL_FAILED", r.provider_message_id or r.error_code)
bad = asyncio.run(p.send_push(token="certification-invalid-token", title="x", body="x", link="/", data={}))
check(checks, "Jeton invalide classé INVALID_TOKEN (appareil désactivé)", "REAL_ACCEPTED" if bad.outcome == "INVALID_TOKEN" else "REAL_FAILED", bad.outcome)
for item in ("Android Chrome / PWA installée : notification au premier plan", "PWA fermée / arrière-plan : notification affichée",
             "Clic : ouverture de la route EduSync", "Révocation d'un appareil : plus de notification sur lui, les autres continuent",
             "Utilisateur déconnecté : plus de notification", "Changement d'école : aucune notification de l'école A sur l'espace B",
             "iOS / Safari : à tester séparément sur iPhone réel avant toute déclaration de support"):
    check(checks, item, "HUMAN_CONFIRMATION_REQUIRED", "Appareil physique")
finish("push_provider_probe", "REAL_ACCEPTED" if r.outcome == "SENT" else "REAL_FAILED", checks)
