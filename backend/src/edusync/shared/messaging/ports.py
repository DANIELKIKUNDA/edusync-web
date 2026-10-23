"""Provider-independent ports of the external messaging channels (EXTERNAL_MESSAGING_ARCHITECTURE.md).

Business use cases never import a provider: they record a message + recipients and an outbox event in their own
transaction. The communications worker applies the notification policy and calls these ports after commit.
Adapters (Orange, SMTP, Firebase) implement them; fakes exist for development and tests only.

Every adapter classifies its outcome so the worker can decide without knowing the provider:
  SENT                 provider accepted the message and returned a proof (an id) -> delivery SENT
  RETRYABLE            temporary failure (timeout, 429/503, network): retried with backoff + jitter, bounded
  PERMANENT            the provider refused the request; retrying the same request cannot succeed
  INVALID_DESTINATION  the recipient address / number is invalid (permanent)
  INVALID_TOKEN        the push registration token is no longer valid: the device is deactivated (permanent)
DELIVERED is never an outcome of a send: it only comes from a provider delivery receipt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

SENT = "SENT"
RETRYABLE = "RETRYABLE"
PERMANENT = "PERMANENT"
INVALID_DESTINATION = "INVALID_DESTINATION"
INVALID_TOKEN = "INVALID_TOKEN"
OUTCOMES = frozenset({SENT, RETRYABLE, PERMANENT, INVALID_DESTINATION, INVALID_TOKEN})


@dataclass(frozen=True)
class SendResult:
    outcome: str
    provider_message_id: str | None = None
    error_code: str | None = None
    retry_after_seconds: int | None = None
    error_detail: str | None = None          # sanitized provider reason (HTTP status, google status / reason) — never a secret

    def __post_init__(self):
        if self.outcome not in OUTCOMES:
            raise ValueError(f"unknown outcome {self.outcome}")
        if self.outcome == SENT and not self.provider_message_id:
            raise ValueError("SENT requires a provider proof (message id)")


@dataclass(frozen=True)
class DeliveryReceipt:
    """Final state reported by a provider for an accepted message (webhook or polling)."""
    provider_message_id: str
    status: str                    # DELIVERED | FAILED | PENDING (intermediate, no final state yet)
    provider_status: str = ""
    error_code: str | None = None


@dataclass(frozen=True)
class EmailContent:
    subject: str
    text: str
    html: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


class SmsProviderPort(Protocol):
    code: str

    async def send_sms(self, *, to_e164: str, body: str) -> SendResult: ...


class EmailProviderPort(Protocol):
    code: str

    async def send_email(self, *, to: str, content: EmailContent) -> SendResult: ...


class PushProviderPort(Protocol):
    code: str

    async def send_push(self, *, token: str, title: str, body: str, link: str | None, data: dict[str, str]) -> SendResult: ...


def safe_error(code: str) -> str:
    """Error codes stored and shown are short identifiers: never a provider body, a token or a credential."""
    cleaned = "".join(ch for ch in (code or "PROVIDER_ERROR").upper() if ch.isalnum() or ch == "_")
    return cleaned[:64] or "PROVIDER_ERROR"
