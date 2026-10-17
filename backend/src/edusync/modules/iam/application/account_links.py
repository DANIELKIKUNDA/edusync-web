"""Single-use account links sent by e-mail: invitation (48 h) and password recovery (30 min) —
EMAIL_TRANSACTIONAL_INTEGRATION.md.

* The token is 256 random bits (secrets.token_urlsafe(32)); only its SHA-256 is stored (account_tokens.token_hash).
* It travels in the URL fragment (#invitation=... / #reset=...), never sent to the server in a request line, logs
  or Referer; the page posts it once, then forgets it.
* Single use: consumed under row lock; a new link revokes the previous open link of the same purpose; a password
  change revokes every open recovery link. Expired / used / revoked links are refused with one neutral message.
* The link itself is encrypted at rest on the recipient row until the e-mail is sent, then wiped by the worker.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import text

from edusync.modules.communications.application.messaging import Recipient, request_message
from edusync.shared.messaging.factory import channel_status
from edusync.shared.messaging.sealing import DELIVERY_SECRET, cipher

INVITATION = "INVITATION"
PASSWORD_RESET = "PASSWORD_RESET"
NEUTRAL_REFUSAL = "Lien invalide ou expiré : demandez-en un nouveau."


def email_available(cfg) -> bool:
    return channel_status(cfg)["email"]["state"] in ("CONFIGURED", "SIMULATED")


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _ttl(cfg, purpose: str) -> timedelta:
    return timedelta(hours=cfg.invitation_ttl_hours) if purpose == INVITATION else timedelta(minutes=cfg.password_reset_ttl_minutes)


def link(cfg, purpose: str, raw: str) -> str:
    anchor = "invitation" if purpose == INVITATION else "reset"
    return f"{cfg.public_app_url.rstrip('/')}/#{anchor}={raw}"


def issue(conn, cfg, *, user_id: UUID, purpose: str, school_id: UUID | None = None, membership_id: UUID | None = None,
          created_by: UUID | None = None) -> str:
    """New single-use token (returned once, never stored in clear); previous open links of this purpose are revoked."""
    conn.execute(text("""UPDATE account_tokens SET revoked_at=now(), revoked_reason='SUPERSEDED'
        WHERE user_id=:u AND purpose=:p AND used_at IS NULL AND revoked_at IS NULL"""), {"u": str(user_id), "p": purpose})
    raw = secrets.token_urlsafe(32)
    conn.execute(text("""INSERT INTO account_tokens(user_id, purpose, token_hash, school_id, membership_id, created_by, expires_at)
        VALUES (:u, :p, :h, :s, :m, :by, :exp)"""),
        {"u": str(user_id), "p": purpose, "h": _hash(raw), "s": str(school_id) if school_id else None,
         "m": str(membership_id) if membership_id else None, "by": str(created_by) if created_by else None,
         "exp": datetime.now(timezone.utc) + _ttl(cfg, purpose)})
    return raw


def peek(conn, purpose: str, raw: str) -> dict | None:
    if not raw or len(raw) > 200:
        return None
    row = conn.execute(text("""SELECT t.id, t.user_id, t.school_id, t.membership_id, u.full_name, u.email, u.active, s.name AS school_name
        FROM account_tokens t JOIN users u ON u.id=t.user_id LEFT JOIN schools s ON s.id=t.school_id
        WHERE t.token_hash=:h AND t.purpose=:p AND t.used_at IS NULL AND t.revoked_at IS NULL AND t.expires_at>now()"""),
        {"h": _hash(raw), "p": purpose}).mappings().first()
    return dict(row) if row and row["active"] else None


def consume(conn, purpose: str, raw: str) -> dict | None:
    """Marks the token used under row lock and returns it, or None (expired, used, revoked, unknown): replay-proof."""
    if not raw or len(raw) > 200:
        return None
    row = conn.execute(text("""SELECT t.id, t.user_id, t.school_id, t.membership_id FROM account_tokens t JOIN users u ON u.id=t.user_id
        WHERE t.token_hash=:h AND t.purpose=:p AND t.used_at IS NULL AND t.revoked_at IS NULL AND t.expires_at>now() AND u.active
        FOR UPDATE OF t"""), {"h": _hash(raw), "p": purpose}).mappings().first()
    if not row:
        return None
    conn.execute(text("UPDATE account_tokens SET used_at=now() WHERE id=:id"), {"id": str(row["id"])})
    return dict(row)


def revoke_open(conn, user_id: UUID, purpose: str, reason: str) -> int:
    return conn.execute(text("""UPDATE account_tokens SET revoked_at=now(), revoked_reason=:r
        WHERE user_id=:u AND purpose=:p AND used_at IS NULL AND revoked_at IS NULL"""), {"u": str(user_id), "p": purpose, "r": reason}).rowcount


def send_link_email(conn, cfg, *, user_id: UUID, email: str, full_name: str | None, purpose: str, raw: str,
                    school_id: UUID | None = None, created_by: UUID | None = None) -> str:
    """Queues the e-mail through the transactional outbox (sent by the worker after commit)."""
    template = "ACCOUNT_INVITATION" if purpose == INVITATION else "ACCOUNT_PASSWORD_RESET"
    seal = cipher(cfg, DELIVERY_SECRET)
    out = request_message(conn, school_id=None, kind="ACCOUNT", channels=["EMAIL"], body=template, template_code=template,
                          recipients=[Recipient("USER", user_id, full_name, email=email, user_id=user_id, target_school_id=school_id)],
                          idempotency_key=f"account-link:{_hash(raw)[:40]}", created_by=created_by,
                          secret_by_ref={user_id: link(cfg, purpose, raw)}, sealer=lambda owner, plain: seal.encrypt(plain, owner=owner))
    return out["id"]


def security_alert(conn, cfg, *, user_id: UUID, text_: str, subject: str = "Alerte de sécurité EduSync") -> str | None:
    """Security e-mail (password changed...) when e-mail is available and the account has an address. Never blocks."""
    if not email_available(cfg):
        return None
    user = conn.execute(text("SELECT email, full_name FROM users WHERE id=:u AND active"), {"u": str(user_id)}).mappings().first()
    if not user or not user["email"]:
        return None
    out = request_message(conn, school_id=None, kind="ACCOUNT", channels=["EMAIL"], body=text_, subject=subject,
                          template_code="ACCOUNT_SECURITY_ALERT",
                          recipients=[Recipient("USER", user_id, user["full_name"], email=user["email"], user_id=user_id)],
                          idempotency_key=f"security-alert:{user_id}:{secrets.token_hex(8)}", created_by=user_id)
    return out["id"]
