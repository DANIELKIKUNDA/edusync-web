"""Encryption at rest of messaging secrets, reusing the platform AES-256-GCM cipher (MfaCipher) with keys derived per
purpose from EDUSYNC_MFA_ENCRYPTION_KEY, so a push token can never be decrypted with the MFA key and vice versa:
  * push registration tokens (push_subscriptions.token_ciphertext, owner = subscription id);
  * one-shot secrets of a delivery, i.e. invitation / recovery links (communication_deliveries.secret_ciphertext,
    owner = delivery id), wiped once the delivery is final.
"""
from __future__ import annotations

import hashlib
import hmac

from edusync.shared.infrastructure.mfa import MfaCipher, load_mfa_key

PUSH_TOKEN = b"edusync:messaging:push-token:v1"
DELIVERY_SECRET = b"edusync:messaging:delivery-secret:v1"


def cipher(cfg, purpose: bytes) -> MfaCipher:
    root = load_mfa_key(cfg.mfa_encryption_key, jwt_secret=cfg.jwt_secret, env=cfg.env)
    return MfaCipher(hmac.new(root, purpose, hashlib.sha256).digest())


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
