"""Platform second factor (option B): persistence and rules, independent of HTTP.

Every function takes a connection of the platform/IAM role (the only role that can read the MFA tables) and runs
inside the caller's transaction. Callers record failures in a transaction that commits before they answer, so an
attempt counter or an audit row is never rolled back by the refusal itself.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

from edusync.shared.infrastructure.mfa import (
    MfaCipher, hash_recovery_code, load_mfa_key, match_totp, new_challenge_token, new_recovery_codes,
    new_totp_secret, hash_challenge_token, provisioning_uri, qr_svg, verify_recovery_code,
)


@dataclass(frozen=True)
class Challenge:
    id: str
    user_id: UUID
    purpose: str
    attempts: int


def cipher_for(settings) -> MfaCipher:
    return MfaCipher(load_mfa_key(settings.mfa_encryption_key, jwt_secret=settings.jwt_secret, env=settings.env))


def security_audit(conn, *, user_id, action: str, actor_user_id=None, detail: dict | None = None, reason: str | None = None,
                   rejected: bool = False) -> None:
    """Security events of an account; never contains a code, a secret or a token."""
    conn.execute(text("""INSERT INTO audit_events(school_id,actor_user_id,action,entity_type,entity_id,source,result,reason,new_json)
        VALUES(NULL,:actor,:a,'UserSecurity',:uid,'WEB',:res,:reason,CAST(:d AS jsonb))"""),
        {"actor": str(actor_user_id or user_id), "uid": str(user_id), "a": action, "res": "REJECTED" if rejected else "SUCCESS",
         "reason": reason, "d": json.dumps(detail or {})})


def active_factor(conn, user_id, *, lock: bool = False):
    sql = "SELECT id, secret_ciphertext, last_used_step, confirmed_at FROM user_mfa_factors WHERE user_id=:u AND status='ACTIVE'"
    return conn.execute(text(sql + (" FOR UPDATE" if lock else "")), {"u": str(user_id)}).mappings().first()


def mfa_needed(conn, settings, user_id) -> bool:
    """Platform console: required by policy, or by the account itself once it has a confirmed factor."""
    return bool(settings.mfa_platform_required) or active_factor(conn, user_id) is not None


# ---------------------------------------------------------------- intermediate challenge

def create_challenge(conn, settings, *, user_id, user_version: int, purpose: str) -> str:
    raw, digest = new_challenge_token()
    # One live challenge per account and purpose: a new password step supersedes the previous one.
    conn.execute(text("UPDATE mfa_challenges SET consumed_at=now() WHERE user_id=:u AND consumed_at IS NULL"), {"u": str(user_id)})
    conn.execute(text("""INSERT INTO mfa_challenges(user_id,purpose,token_hash,user_version,expires_at)
        VALUES(:u,:p,:h,:v,now()+make_interval(secs=>:s))"""),
        {"u": str(user_id), "p": purpose, "h": digest, "v": int(user_version), "s": int(settings.mfa_challenge_seconds)})
    return raw


def load_challenge(conn, settings, raw: str, purpose: str) -> Challenge | None:
    """A usable challenge: right purpose, not consumed, not expired, attempts left, account unchanged and active."""
    row = conn.execute(text("""SELECT c.id, c.user_id, c.purpose, c.attempts FROM mfa_challenges c JOIN users u ON u.id=c.user_id
        WHERE c.token_hash=:h AND c.purpose=:p AND c.consumed_at IS NULL AND c.expires_at>now() AND c.attempts<:max
          AND u.active AND u.version=c.user_version FOR UPDATE OF c"""),
        {"h": hash_challenge_token(raw), "p": purpose, "max": int(settings.mfa_max_attempts)}).mappings().first()
    return Challenge(str(row["id"]), row["user_id"], row["purpose"], int(row["attempts"])) if row else None


def record_failed_attempt(conn, challenge: Challenge) -> int:
    return int(conn.execute(text("UPDATE mfa_challenges SET attempts=attempts+1 WHERE id=:id RETURNING attempts"), {"id": challenge.id}).scalar_one())


def consume_challenge(conn, challenge: Challenge) -> None:
    conn.execute(text("UPDATE mfa_challenges SET consumed_at=now() WHERE id=:id"), {"id": challenge.id})


# ---------------------------------------------------------------- enrolment

def start_enrollment(conn, cipher: MfaCipher, *, user_id, account: str) -> dict:
    """New pending secret (replaces an unconfirmed one). Returned once, to the account owner, during enrolment only."""
    if active_factor(conn, user_id) is not None:
        raise ValueError("ALREADY_ENROLLED")
    conn.execute(text("""UPDATE user_mfa_factors SET status='REVOKED', revoked_at=now(), revoked_reason='ENROLMENT_RESTARTED'
        WHERE user_id=:u AND status='PENDING'"""), {"u": str(user_id)})
    secret = new_totp_secret()
    conn.execute(text("INSERT INTO user_mfa_factors(user_id,status,secret_ciphertext) VALUES(:u,'PENDING',:c)"),
                 {"u": str(user_id), "c": cipher.encrypt(secret, owner=str(user_id))})
    uri = provisioning_uri(secret, account)
    return {"secret": secret, "otpauth_uri": uri, "qr_svg": qr_svg(uri)}


def _store_recovery_codes(conn, *, user_id, factor_id) -> list[str]:
    conn.execute(text("UPDATE user_mfa_recovery_codes SET revoked_at=now() WHERE user_id=:u AND used_at IS NULL AND revoked_at IS NULL"),
                 {"u": str(user_id)})
    codes = new_recovery_codes()
    for code in codes:
        conn.execute(text("INSERT INTO user_mfa_recovery_codes(user_id,factor_id,code_hash) VALUES(:u,:f,:h)"),
                     {"u": str(user_id), "f": str(factor_id), "h": hash_recovery_code(code)})
    return codes


def confirm_enrollment(conn, cipher: MfaCipher, *, user_id, code: str) -> list[str] | None:
    """Activates the pending factor when the first code is valid; returns the recovery codes (shown once)."""
    pending = conn.execute(text("SELECT id, secret_ciphertext FROM user_mfa_factors WHERE user_id=:u AND status='PENDING' FOR UPDATE"),
                           {"u": str(user_id)}).mappings().first()
    if pending is None:
        return None
    step = match_totp(cipher.decrypt(pending["secret_ciphertext"], owner=str(user_id)), code, last_used_step=0)
    if step is None:
        return None
    conn.execute(text("""UPDATE user_mfa_factors SET status='ACTIVE', confirmed_at=now(), last_used_step=:s WHERE id=:id"""),
                 {"id": pending["id"], "s": step})
    return _store_recovery_codes(conn, user_id=user_id, factor_id=pending["id"])


# ---------------------------------------------------------------- verification

def verify_totp(conn, cipher: MfaCipher, *, user_id, code: str) -> bool:
    factor = active_factor(conn, user_id, lock=True)
    if factor is None:
        return False
    step = match_totp(cipher.decrypt(factor["secret_ciphertext"], owner=str(user_id)), code, last_used_step=int(factor["last_used_step"]))
    if step is None:
        return False
    # Compare-and-set: two concurrent requests with the same code cannot both succeed.
    return conn.execute(text("UPDATE user_mfa_factors SET last_used_step=:s WHERE id=:id AND last_used_step<:s"),
                        {"id": factor["id"], "s": step}).rowcount == 1


def use_recovery_code(conn, *, user_id, code: str) -> int | None:
    """Consumes a matching recovery code; returns how many remain, or None when no usable code matches."""
    if active_factor(conn, user_id) is None:
        return None
    rows = conn.execute(text("""SELECT id, code_hash FROM user_mfa_recovery_codes WHERE user_id=:u AND used_at IS NULL AND revoked_at IS NULL
        ORDER BY created_at FOR UPDATE"""), {"u": str(user_id)}).mappings().all()
    matched = None
    for row in rows:
        if verify_recovery_code(code, row["code_hash"]) and matched is None:
            matched = row["id"]
    if matched is None:
        return None
    if conn.execute(text("UPDATE user_mfa_recovery_codes SET used_at=now() WHERE id=:id AND used_at IS NULL"), {"id": matched}).rowcount != 1:
        return None
    return len(rows) - 1


def regenerate_recovery_codes(conn, *, user_id) -> list[str] | None:
    factor = active_factor(conn, user_id)
    return None if factor is None else _store_recovery_codes(conn, user_id=user_id, factor_id=factor["id"])


def status(conn, user_id) -> dict:
    factor = active_factor(conn, user_id)
    remaining = conn.execute(text("""SELECT count(*) FROM user_mfa_recovery_codes WHERE user_id=:u AND used_at IS NULL AND revoked_at IS NULL"""),
                             {"u": str(user_id)}).scalar_one() if factor else 0
    return {"enrolled": factor is not None, "method": "TOTP" if factor else None,
            "confirmed_at": factor["confirmed_at"] if factor else None, "recovery_codes_remaining": int(remaining)}


def reset(conn, *, user_id, reason: str) -> dict:
    """Removes the factor of an account (another Manager, audited by the caller): the next sign-in enrols again."""
    factors = conn.execute(text("""UPDATE user_mfa_factors SET status='REVOKED', revoked_at=now(), revoked_reason=:r
        WHERE user_id=:u AND status IN ('ACTIVE','PENDING')"""), {"u": str(user_id), "r": reason[:64]}).rowcount
    codes = conn.execute(text("UPDATE user_mfa_recovery_codes SET revoked_at=now() WHERE user_id=:u AND used_at IS NULL AND revoked_at IS NULL"),
                         {"u": str(user_id)}).rowcount
    conn.execute(text("UPDATE mfa_challenges SET consumed_at=now() WHERE user_id=:u AND consumed_at IS NULL"), {"u": str(user_id)})
    return {"factors_revoked": factors, "recovery_codes_revoked": codes}
