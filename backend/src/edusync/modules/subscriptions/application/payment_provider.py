from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from decimal import Decimal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class PaymentProviderUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Initiation:
    provider_reference: str
    status: str
    raw_sha256: str


def sign_payload(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_signature(secret: str, body: bytes, supplied: str | None) -> bool:
    if not secret or not supplied:
        return False
    clean = supplied.removeprefix("sha256=").strip().lower()
    return hmac.compare_digest(sign_payload(secret, body), clean)


def initiate_mobile_money(settings, *, payment_reference: str, phone: str, amount: Decimal,
                          currency: str) -> Initiation:
    mode = (settings.mobile_money_mode or "disabled").lower()
    if mode == "disabled":
        raise PaymentProviderUnavailable("Le paiement Mobile Money n’est pas encore activé pour cette installation")
    payload = json.dumps({"reference": payment_reference, "phone": phone, "amount": format(amount, "f"),
                          "currency": currency, "callback_url": settings.mobile_money_callback_url},
                         separators=(",", ":")).encode()
    if mode == "sandbox":
        reference = f"SANDBOX-{hashlib.sha256(payload).hexdigest()[:20].upper()}"
        return Initiation(reference, "PENDING", hashlib.sha256(payload).hexdigest())
    if not settings.mobile_money_api_base.startswith("https://") or not settings.mobile_money_api_key:
        raise PaymentProviderUnavailable("Configuration du fournisseur Mobile Money incomplète")
    request = Request(settings.mobile_money_api_base.rstrip("/") + "/payments", data=payload, method="POST",
                      headers={"Authorization": f"Bearer {settings.mobile_money_api_key}",
                               "Content-Type": "application/json", "Idempotency-Key": payment_reference})
    try:
        with urlopen(request, timeout=settings.mobile_money_timeout_seconds) as response:  # noqa: S310 — HTTPS checked
            raw = response.read(131072)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise PaymentProviderUnavailable("Le fournisseur Mobile Money est momentanément indisponible") from exc
    try:
        result = json.loads(raw)
        provider_reference = str(result["provider_reference"])
        status = str(result.get("status", "PENDING")).upper()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PaymentProviderUnavailable("Réponse invalide du fournisseur Mobile Money") from exc
    if status not in {"CREATED", "PENDING", "SUCCEEDED", "FAILED"}:
        status = "PENDING"
    return Initiation(provider_reference, status, hashlib.sha256(raw).hexdigest())
