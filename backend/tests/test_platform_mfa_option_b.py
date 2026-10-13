"""Second factor of platform accounts — MFA_PROPOSAL.md option B (owner decision 2026-10-13).

Unit level: RFC 6238 vectors, replay and drift window, encryption at rest bound to its owner, recovery codes,
configuration guards. Contract level: no session before the second factor, no self-disable route, platform tokens
require a verified session, MFA tables out of reach of the tenant role. Live behaviour: certification/n0-n1-20261007/mfa_probe.py.
"""
import ast
import base64
from pathlib import Path

import pytest

from edusync.bootstrap.settings import Settings
from edusync.shared.infrastructure import mfa

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "backend/src/edusync"
RFC_SECRET = base64.b32encode(b"12345678901234567890").decode().rstrip("=")


@pytest.mark.parametrize("t,expected", [(59, "94287082"), (1111111109, "07081804"), (1111111111, "14050471"),
                                         (1234567890, "89005924"), (2000000000, "69279037"), (20000000000, "65353130")])
def test_totp_matches_rfc6238_sha1_vectors(t, expected):
    assert mfa.totp_code(RFC_SECRET, t // 30) == expected[-6:]


def test_code_accepted_once_then_replay_refused():
    secret, now = mfa.new_totp_secret(), 1_800_000_000.0
    step = mfa.current_step(now)
    code = mfa.totp_code(secret, step)
    assert mfa.match_totp(secret, code, last_used_step=0, now=now) == step
    assert mfa.match_totp(secret, code, last_used_step=step, now=now) is None


def test_drift_tolerance_is_one_step_each_way():
    secret, now = mfa.new_totp_secret(), 1_800_000_000.0
    step = mfa.current_step(now)
    assert mfa.match_totp(secret, mfa.totp_code(secret, step - 1), last_used_step=0, now=now) == step - 1
    assert mfa.match_totp(secret, mfa.totp_code(secret, step + 1), last_used_step=0, now=now) == step + 1
    assert mfa.match_totp(secret, mfa.totp_code(secret, step - 2), last_used_step=0, now=now) is None
    assert mfa.match_totp(secret, mfa.totp_code(secret, step + 2), last_used_step=0, now=now) is None


@pytest.mark.parametrize("bad", ["", "12345", "1234567", "12a456", "      "])
def test_malformed_codes_refused(bad):
    assert mfa.match_totp(mfa.new_totp_secret(), bad, last_used_step=0) is None


def test_code_with_spaces_accepted():
    secret, now = mfa.new_totp_secret(), 1_800_000_000.0
    code = mfa.totp_code(secret, mfa.current_step(now))
    assert mfa.match_totp(secret, f"{code[:3]} {code[3:]}", last_used_step=0, now=now) is not None


def test_secret_is_160_bits_and_random():
    a, b = mfa.new_totp_secret(), mfa.new_totp_secret()
    assert a != b and len(base64.b32decode(a + "=" * (-len(a) % 8))) == 20


def test_secret_encrypted_at_rest_and_bound_to_its_owner():
    cipher = mfa.MfaCipher(bytes(range(32)))
    secret = mfa.new_totp_secret()
    sealed = cipher.encrypt(secret, owner="user-a")
    assert secret not in sealed and sealed.startswith("v1:")
    assert cipher.decrypt(sealed, owner="user-a") == secret
    assert cipher.encrypt(secret, owner="user-a") != sealed  # random nonce
    with pytest.raises(Exception):
        cipher.decrypt(sealed, owner="user-b")
    with pytest.raises(Exception):
        mfa.MfaCipher(bytes(32)).decrypt(sealed, owner="user-a")


def test_key_is_mandatory_outside_development_and_must_be_32_bytes():
    with pytest.raises(RuntimeError):
        mfa.load_mfa_key("", jwt_secret="x" * 40, env="production")
    with pytest.raises(RuntimeError):
        mfa.load_mfa_key(base64.urlsafe_b64encode(b"short").decode(), jwt_secret="x" * 40, env="dev")
    key = base64.urlsafe_b64encode(bytes(range(32))).decode().rstrip("=")
    assert mfa.load_mfa_key(key, jwt_secret="x" * 40, env="production") == bytes(range(32))
    derived = mfa.load_mfa_key("", jwt_secret="y" * 40, env="dev")
    assert len(derived) == 32 and derived != ("y" * 40).encode()[:32]


def test_production_refuses_to_disable_platform_mfa_or_run_without_key():
    prod = dict(_env_file=None, env="production", jwt_secret="p" * 48, cors_origins="https://app.example.cd",
                trusted_hosts="app.example.cd", tenant_database_url="postgresql+psycopg://edusync_tenant:Str0ng@db/edusync",
                platform_database_url="postgresql+psycopg://edusync_platform:Str0ng@db/edusync")
    with pytest.raises(RuntimeError):
        Settings(**prod, mfa_platform_required=False, mfa_encryption_key=base64.b64encode(bytes(32)).decode()).assert_runtime_safe()
    with pytest.raises(RuntimeError):
        Settings(**prod).assert_runtime_safe()
    Settings(**prod, mfa_encryption_key=base64.b64encode(bytes(range(32))).decode()).assert_runtime_safe()


def test_policy_on_by_default():
    cfg = Settings(_env_file=None)
    assert cfg.mfa_platform_required is True and cfg.mfa_max_attempts == 5 and cfg.mfa_lock_seconds == 900 and cfg.mfa_challenge_seconds == 300


def test_recovery_codes_single_format_hashed_and_tolerant():
    codes = mfa.new_recovery_codes()
    assert len(codes) == 10 and len(set(codes)) == 10 and all(len(c) == 11 and c[5] == "-" for c in codes)
    assert not any(ch in "".join(codes) for ch in "01OIL")
    encoded = mfa.hash_recovery_code(codes[0])
    assert encoded.startswith("$argon2") and codes[0] not in encoded
    assert mfa.verify_recovery_code(codes[0].lower().replace("-", " "), encoded)
    assert not mfa.verify_recovery_code(codes[1], encoded)
    assert not mfa.verify_recovery_code("", encoded)


def test_provisioning_uri_and_local_qr_code():
    uri = mfa.provisioning_uri("JBSWY3DPEHPK3PXP", "manager@example.cd")
    assert uri.startswith("otpauth://totp/EduSync%20Atelier%20Pro:manager@example.cd?secret=JBSWY3DPEHPK3PXP")
    assert "issuer=EduSync%20Atelier%20Pro" in uri and "digits=6" in uri and "period=30" in uri
    svg = mfa.qr_svg(uri)
    # Rendered by the client as <img src="data:image/svg+xml,…">: an SVG image needs its namespace to display.
    assert svg.lstrip().startswith("<svg") and 'xmlns="http://www.w3.org/2000/svg"' in svg and "<script" not in svg
    assert 'viewBox="0 0 ' in svg


def test_challenge_token_is_opaque_and_only_its_hash_is_stored():
    raw, digest = mfa.new_challenge_token()
    assert raw != digest and mfa.hash_challenge_token(raw) == digest and len(digest) == 64


# ---------------------------------------------------------------- contracts

def _source(rel: str) -> str:
    return (SRC / rel).read_text(encoding="utf-8")


def test_platform_login_returns_a_step_token_before_any_session():
    s = _source("modules/iam/api/router.py")
    login = s[s.index("def login("):s.index("@router.get(\"/me\")")]
    platform = login[login.index('if body.scope == "PLATFORM"'):login.index("code = (body.school_code")]
    assert platform.index("platform_mfa.mfa_needed") < platform.index("_issue_platform_session")
    assert '"mfa_token": step_token' in platform and "create_access_token" not in platform


def test_no_route_lets_a_platform_account_disable_its_own_factor():
    tree = ast.parse(_source("modules/iam/api/router.py"))
    paths = [d.args[0].value for n in tree.body if isinstance(n, ast.FunctionDef) for d in n.decorator_list
             if isinstance(d, ast.Call) and d.args and isinstance(d.args[0], ast.Constant)]
    mfa_paths = sorted(p for p in paths if "mfa" in p)
    assert mfa_paths == ["/mfa/enroll/confirm", "/mfa/enroll/start", "/mfa/verify", "/platform/mfa", "/platform/mfa/recovery-codes"]
    assert '"self_disable_allowed": False' in _source("modules/iam/api/router.py")


def test_platform_actor_requires_a_session_that_passed_the_second_factor():
    deps = _source("bootstrap/dependencies.py")
    assert "require_mfa=mfa_needed(conn, services.settings, user_id)" in deps
    assert "SELECT mfa_verified_at FROM user_device_sessions" in deps
    refresh = _source("modules/iam/api/router.py")
    assert "row['mfa_verified_at'] is None and platform_mfa.mfa_needed(conn,cfg,row['user_id'])" in refresh


def test_failures_are_committed_before_the_refusal_is_answered():
    s = _source("modules/iam/api/router.py")
    for fn in ("def mfa_verify(", "def mfa_enroll_confirm("):
        body = s[s.index(fn):]
        body = body[:body.index("\n@router.")]
        assert "record_failed_attempt" in body and "_raise_mfa_outcome(outcome)" in body
        assert body.rindex("_raise_mfa_outcome(outcome)") > body.index("with services.platform_db.platform_transaction()")
        assert "raise HTTPException(status_code=400" not in body  # never raised inside the transaction


def test_team_reset_is_governed_reasoned_idempotent_and_never_self_service():
    s = _source("modules/platform_team/api/router.py")
    fn = s[s.index("def team_reset_mfa("):]
    for marker in ("actor.require(TEAM_CAP)", "_key(idempotency_key)", "_guard_target(c, actor, user_id)",
                   "platform_mfa.reset(", "_revoke_platform_sessions(c, user_id, \"MFA_RESET\")", "PLATFORM_USER_MFA_RESET", "reason=body.reason"):
        assert marker in fn, marker


def test_mfa_tables_reachable_by_the_platform_role_only_and_never_erased():
    sql = (ROOT / "backend/migrations/0056_platform_mfa_totp.sql").read_text(encoding="utf-8")
    for table in ("user_mfa_factors", "user_mfa_recovery_codes", "mfa_challenges"):
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in sql
    assert "REVOKE ALL ON user_mfa_factors, user_mfa_recovery_codes, mfa_challenges FROM edusync_tenant" in sql
    assert "REVOKE DELETE, TRUNCATE ON user_mfa_factors, user_mfa_recovery_codes, mfa_challenges FROM edusync_platform" in sql
    assert "ux_mfa_factor_one_active" in sql and "legacy_prototype_" in sql
    prov = (ROOT / "backend/scripts/provision_database.py").read_text(encoding="utf-8")
    assert '("0056_platform_mfa_totp", "0056_platform_mfa_totp.sql")' in prov


def test_audit_never_receives_codes_or_secrets():
    s = _source("modules/iam/application/platform_mfa.py") + _source("modules/iam/api/router.py")
    for call in [line for line in s.splitlines() if "security_audit(" in line and "def security_audit" not in line]:
        assert "secret" not in call.split("detail=", 1)[-1] and "body.code" not in call and "recovery_code=" not in call


def test_frontend_challenge_and_enrolment_screens_exist():
    login = (ROOT / "frontend/src/login.tsx").read_text(encoding="utf-8")
    for marker in ("MfaChallenge", "MfaEnrollment", 'autoComplete="one-time-code"', 'inputMode="numeric"', "Utiliser un code de secours", "isMfaStep("):
        assert marker in login, marker
    account = (ROOT / "frontend/src/platform/account.tsx").read_text(encoding="utf-8")
    assert "regenerateRecoveryCodes" in account and "platformMfaStatus" in account
    team = (ROOT / "frontend/src/platform/team.tsx").read_text(encoding="utf-8")
    assert "teamResetMfa" in team
