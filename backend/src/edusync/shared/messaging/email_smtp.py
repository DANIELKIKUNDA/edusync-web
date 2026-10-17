"""Transactional e-mail over standard SMTP (aiosmtplib) — EMAIL_TRANSACTIONAL_INTEGRATION.md.

Any professional relay (Brevo SMTP, Mailjet, Amazon SES SMTP, a corporate relay...) works without changing IAM.
SMTP acceptance is the only proof available: the delivery becomes SENT when the server accepts the message
(provider_message_id = our Message-ID), never DELIVERED. Bounce / delivery webhooks belong to a future specialised
adapter behind the same port. Credentials never appear in logs or error codes.
"""
from __future__ import annotations

import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

import aiosmtplib

from edusync.shared.messaging.ports import (INVALID_DESTINATION, PERMANENT, RETRYABLE, SENT, EmailContent, SendResult,
                                            safe_error)


class SmtpConfigurationError(RuntimeError):
    pass


class SmtpEmailProvider:
    code = "smtp"

    def __init__(self, *, host: str, port: int, username: str, password: str, from_email: str, from_name: str = "EduSync",
                 security: str = "starttls", timeout_seconds: float = 20.0, allow_plaintext: bool = False):
        if not (host and from_email and "@" in from_email):
            raise SmtpConfigurationError("SMTP : hôte et adresse d'expédition obligatoires")
        security = (security or "starttls").lower()
        if security not in {"starttls", "tls", "none"} or (security == "none" and not allow_plaintext):
            raise SmtpConfigurationError("SMTP : chiffrement starttls ou tls obligatoire")
        self.host, self.port, self.username, self._password = host, int(port), username, password
        self.from_email, self.from_name, self.security, self.timeout = from_email, from_name, security, timeout_seconds

    def build(self, *, to: str, content: EmailContent) -> EmailMessage:
        msg = EmailMessage()
        msg["From"] = formataddr((self.from_name, self.from_email))
        msg["To"] = to
        msg["Subject"] = content.subject
        msg["Date"] = formatdate(localtime=False)
        msg["Message-ID"] = make_msgid(domain=self.from_email.split("@", 1)[1])
        msg["Auto-Submitted"] = "auto-generated"
        for k, v in content.headers.items():
            msg[k] = v
        msg.set_content(content.text)
        if content.html:
            msg.add_alternative(content.html, subtype="html")
        return msg

    async def send_email(self, *, to: str, content: EmailContent) -> SendResult:
        if "@" not in to or len(to) > 320 or any(ch in to for ch in "\r\n,;<>"):
            return SendResult(INVALID_DESTINATION, error_code="INVALID_DESTINATION")
        msg = self.build(to=to, content=content)
        try:
            await aiosmtplib.send(msg, hostname=self.host, port=self.port, username=self.username or None,
                                  password=self._password or None, use_tls=self.security == "tls",
                                  start_tls=True if self.security == "starttls" else False if self.security == "none" else None,
                                  tls_context=ssl.create_default_context(), timeout=self.timeout)
        except aiosmtplib.SMTPRecipientsRefused:
            return SendResult(INVALID_DESTINATION, error_code="SMTP_RECIPIENT_REFUSED")
        except aiosmtplib.SMTPAuthenticationError:
            return SendResult(RETRYABLE, error_code="SMTP_AUTHENTICATION", retry_after_seconds=600)
        except aiosmtplib.SMTPResponseException as exc:
            code = int(getattr(exc, "code", 0) or 0)
            return SendResult(PERMANENT if 500 <= code < 600 else RETRYABLE, error_code=safe_error(f"SMTP_{code}"))
        except (aiosmtplib.SMTPConnectError, aiosmtplib.SMTPServerDisconnected, aiosmtplib.SMTPTimeoutError, OSError):
            return SendResult(RETRYABLE, error_code="SMTP_UNAVAILABLE")
        except aiosmtplib.SMTPException:
            return SendResult(RETRYABLE, error_code="SMTP_ERROR")
        return SendResult(SENT, provider_message_id=str(msg["Message-ID"]).strip("<>")[:180])
