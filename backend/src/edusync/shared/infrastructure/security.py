from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
import secrets

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    value = password or ""
    if len(value) < 10:
        raise ValueError("Le mot de passe doit contenir au moins 10 caractères")
    return _hasher.hash(value)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return _hasher.verify(encoded, password)
    except (VerifyMismatchError, Exception):
        return False


def create_access_token(*, subject: str, secret: str, issuer: str, audience: str,
                        minutes: int, claims: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iss": issuer,
        "aud": audience,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
        "jti": str(uuid4()),
        "typ": "access",
    }
    payload.update(claims or {})
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_access_token(token: str, *, secret: str, issuer: str, audience: str) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        issuer=issuer,
        audience=audience,
        options={"require": ["sub", "iss", "aud", "iat", "nbf", "exp", "jti", "typ"]},
    )
    if payload.get("typ") != "access":
        raise jwt.InvalidTokenError("Type de jeton invalide")
    return payload


_TEMP_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"


def new_temporary_password() -> str:
    """Temporary password handed over by an administrator (read aloud or copied): 3 groups of 4 unambiguous characters
    (about 69 bits). It must be replaced at the first sign-in."""
    return "-".join("".join(secrets.choice(_TEMP_ALPHABET) for _ in range(4)) for _ in range(3))
