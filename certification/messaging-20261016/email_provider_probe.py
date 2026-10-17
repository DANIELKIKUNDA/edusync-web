"""REAL SMTP e-mail probe (EMAIL_TRANSACTIONAL_INTEGRATION.md). Requires (never printed): EDUSYNC_EMAIL_PROVIDER=smtp,
EDUSYNC_SMTP_HOST / PORT / USERNAME / PASSWORD / FROM_EMAIL / SECURITY and the operator's own mailbox
EDUSYNC_PROBE_EMAIL_TO. Checks: TLS session and authentication, one real e-mail accepted (SENT = accepted by the SMTP
server, never DELIVERED), refused recipient classified. Reception in the inbox (and spam folder) is confirmed by a human."""
import asyncio
import os

from provider_probe_common import check, finish, settings

cfg = settings()
checks: list[dict] = []
missing = [k for k, v in (("EDUSYNC_EMAIL_PROVIDER=smtp", cfg.email_provider == "smtp"), ("EDUSYNC_SMTP_HOST", cfg.smtp_host),
                          ("EDUSYNC_SMTP_FROM_EMAIL", cfg.smtp_from_email), ("EDUSYNC_PROBE_EMAIL_TO", os.environ.get("EDUSYNC_PROBE_EMAIL_TO"))) if not v]
if missing:
    check(checks, "Paramètres SMTP et boîte de test fournis", "EXTERNAL_REQUIRED", ", ".join(missing))
    finish("email_provider_probe", "EXTERNAL_REQUIRED", checks)

from edusync.modules.communications.domain.email_templates import render  # noqa: E402
from edusync.shared.messaging.email_smtp import SmtpEmailProvider  # noqa: E402

p = SmtpEmailProvider(host=cfg.smtp_host, port=cfg.smtp_port, username=cfg.smtp_username, password=cfg.smtp_password, from_email=cfg.smtp_from_email,
                      from_name=cfg.smtp_from_name, security=cfg.smtp_security, timeout_seconds=cfg.smtp_timeout_seconds)
to = os.environ["EDUSYNC_PROBE_EMAIL_TO"].strip()
content = render("ACCOUNT_SECURITY_ALERT", recipient_name="Recette EduSync", school_name=None, subject="Test EduSync — e-mail transactionnel",
                 body="Ceci est un e-mail réel de certification EduSync. Aucune action n’est requise.", link=None)
r = asyncio.run(p.send_email(to=to, content=content))
check(checks, f"E-mail réel accepté par le serveur SMTP ({cfg.smtp_security})", "REAL_ACCEPTED" if r.outcome == "SENT" else "REAL_FAILED", r.error_code or "SENT")
check(checks, "Statut enregistré : SENT (accepté), jamais DELIVERED sans preuve", "REAL_ACCEPTED")
check(checks, "Réception dans la boîte (et hors indésirables), en-têtes SPF/DKIM du domaine", "HUMAN_CONFIRMATION_REQUIRED", "À constater dans la boîte de test")
finish("email_provider_probe", "REAL_ACCEPTED" if r.outcome == "SENT" else "REAL_FAILED", checks)
