"""Second factor for platform accounts (MFA_PROPOSAL.md, option B): TOTP (RFC 6238) + single-use recovery codes.

* The TOTP secret is encrypted at rest with AES-256-GCM under EDUSYNC_MFA_ENCRYPTION_KEY, a key distinct from the JWT
  secret; the ciphertext is bound to its owner (associated data = user id), so a row copied to another account fails.
* A code is accepted in a window of +/- 1 step of 30 s (clock drift) and only for a step strictly greater than the
  last one used: a code can never be replayed, even inside its own window.
* Recovery codes are random, shown once, stored as Argon2 hashes; each one is consumed once.
Nothing here logs or returns a secret except the enrolment response, which shows it once to its owner.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

from argon2 import PasswordHasher

from edusync.bootstrap.settings import is_protected_env
from argon2.exceptions import VerificationError, VerifyMismatchError, InvalidHashError

STEP_SECONDS = 30
DIGITS = 6
DRIFT_STEPS = 1
RECOVERY_CODE_COUNT = 10
ISSUER = "EduSync Atelier Pro"
# Unambiguous alphabet for recovery codes (no 0/O, 1/I/L): read aloud or copied by hand without mistakes.
_RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_recovery_hasher = PasswordHasher()


# ---------------------------------------------------------------- TOTP (RFC 6238, HMAC-SHA1, 6 digits, 30 s)

def new_totp_secret() -> str:
    """160 random bits, base32 without padding (what authenticator apps expect)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _secret_bytes(secret_b32: str) -> bytes:
    clean = secret_b32.strip().replace(" ", "").upper()
    return base64.b32decode(clean + "=" * (-len(clean) % 8))


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP_SECONDS)


def totp_code(secret_b32: str, step: int) -> str:
    digest = hmac.new(_secret_bytes(secret_b32), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10 ** DIGITS)).zfill(DIGITS)


def normalize_totp(code: str) -> str | None:
    digits = "".join(ch for ch in (code or "") if not ch.isspace())
    return digits if len(digits) == DIGITS and digits.isdigit() else None


def match_totp(secret_b32: str, code: str, *, last_used_step: int, now: float | None = None) -> int | None:
    """The step the code belongs to, or None. Steps at or before last_used_step are refused (no replay)."""
    clean = normalize_totp(code)
    if clean is None:
        return None
    base = current_step(now)
    matched = None
    for step in range(base - DRIFT_STEPS, base + DRIFT_STEPS + 1):
        # Compare every candidate in constant time; never stop early on a match.
        if hmac.compare_digest(totp_code(secret_b32, step), clean) and step > last_used_step:
            matched = step
    return matched


def provisioning_uri(secret_b32: str, account: str) -> str:
    label = quote(f"{ISSUER}:{account}", safe="@:")
    return (f"otpauth://totp/{label}?secret={secret_b32}&issuer={quote(ISSUER)}"
            f"&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}")


def qr_svg(uri: str) -> str:
    """QR code of the provisioning URI as a standalone SVG (no external service ever sees the secret). The SVG
    namespace is kept: the client shows it as an <img> (data URI), which never executes anything it contains."""
    import io
    import segno
    out = io.BytesIO()
    segno.make(uri, error="m").save(out, kind="svg", xmldecl=False, svgns=True, nl=False, scale=5, border=2, dark="#0f172a", light="#ffffff")
    svg = out.getvalue().decode("utf-8")
    # A viewBox lets the image scale to whatever size the screen gives it (phone or desktop).
    import re
    size = re.search(r'width="(\d+)" height="(\d+)"', svg)
    return svg.replace("<svg ", f'<svg viewBox="0 0 {size.group(1)} {size.group(2)}" ', 1) if size else svg


# ---------------------------------------------------------------- secret encryption at rest

class MfaCipher:
    """AES-256-GCM with a random 96-bit nonce; the user id is authenticated as associated data."""
    VERSION = "v1"

    def __init__(self, key: bytes):
        if len(key) != 32:
            raise ValueError("La clé MFA doit faire 32 octets")
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        self._aead = AESGCM(key)

    def encrypt(self, plaintext: str, *, owner: str) -> str:
        nonce = secrets.token_bytes(12)
        sealed = self._aead.encrypt(nonce, plaintext.encode("utf-8"), owner.encode("utf-8"))
        return f"{self.VERSION}:" + base64.urlsafe_b64encode(nonce + sealed).decode("ascii")

    def decrypt(self, token: str, *, owner: str) -> str:
        version, _, body = token.partition(":")
        if version != self.VERSION:
            raise ValueError("Format de secret MFA inconnu")
        raw = base64.urlsafe_b64decode(body.encode("ascii"))
        return self._aead.decrypt(raw[:12], raw[12:], owner.encode("utf-8")).decode("utf-8")


def load_mfa_key(configured: str, *, jwt_secret: str, env: str) -> bytes:
    """EDUSYNC_MFA_ENCRYPTION_KEY: 32 bytes, base64/base64url. Mandatory outside development; in development only,
    an absent key is derived from the JWT secret with a dedicated label so local runs work out of the box."""
    value = (configured or "").strip()
    if value:
        try:
            key = base64.urlsafe_b64decode(value.replace("+", "-").replace("/", "_") + "=" * (-len(value) % 4))
        except Exception as exc:  # pragma: no cover - message only
            raise RuntimeError("EDUSYNC_MFA_ENCRYPTION_KEY illisible (base64 de 32 octets attendu)") from exc
        if len(key) != 32:
            raise RuntimeError("EDUSYNC_MFA_ENCRYPTION_KEY doit encoder exactement 32 octets")
        return key
    if is_protected_env(env):
        raise RuntimeError("EDUSYNC_MFA_ENCRYPTION_KEY obligatoire : le second facteur plateforme est actif")
    return hmac.new(jwt_secret.encode("utf-8"), b"edusync:mfa:dev-derived-key:v1", hashlib.sha256).digest()


# ---------------------------------------------------------------- recovery codes

def new_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    def one() -> str:
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
        return f"{raw[:5]}-{raw[5:]}"
    return [one() for _ in range(count)]


def normalize_recovery_code(code: str) -> str:
    return "".join(ch for ch in (code or "").upper() if ch in _RECOVERY_ALPHABET)


def hash_recovery_code(code: str) -> str:
    return _recovery_hasher.hash(normalize_recovery_code(code))


def verify_recovery_code(code: str, encoded: str) -> bool:
    try:
        return _recovery_hasher.verify(encoded, normalize_recovery_code(code))
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# ---------------------------------------------------------------- intermediate challenge token

def new_challenge_token() -> tuple[str, str]:
    """Opaque token handed back after the password step; only its SHA-256 is stored, it is never an access token."""
    raw = secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode("ascii")).hexdigest()


def hash_challenge_token(raw: str) -> str:
    return hashlib.sha256((raw or "").encode("ascii", "ignore")).hexdigest()
