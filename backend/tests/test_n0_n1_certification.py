"""N0/N1 certification contracts (2026-10): persistent sessions, exact money, worker role, sign-in without school code."""
from decimal import Decimal
from pathlib import Path

import pytest

from edusync.bootstrap.settings import Settings, worker_url

ROOT = Path(__file__).resolve().parents[2]
FRONT = ROOT / "frontend"


def test_no_periodic_reauthentication_by_default():
    cfg = Settings(_env_file=None)
    assert cfg.session_absolute_days == 0 and cfg.session_idle_days == 0
    assert cfg.session_rotation_grace_seconds > 0


def test_workers_refuse_owner_or_missing_database_url():
    with pytest.raises(RuntimeError):
        worker_url(Settings(_env_file=None, worker_database_url=""))
    with pytest.raises(RuntimeError):
        worker_url(Settings(_env_file=None, worker_database_url="postgresql+psycopg://edusync_owner:x@db/edusync"))
    assert worker_url(Settings(_env_file=None, worker_database_url="postgresql+psycopg://edusync_worker:x@db/edusync")).endswith("/edusync")


def test_workers_use_worker_url_never_owner():
    for rel in ("modules/sync/outbox_worker.py", "modules/communications/worker.py"):
        s = (ROOT / "backend/src/edusync" / rel).read_text(encoding="utf-8")
        assert "worker_url(cfg)" in s and "owner_database_url" not in s


def test_money_leaves_the_api_as_exact_decimal_string():
    from fastapi.encoders import jsonable_encoder
    from edusync.bootstrap.app import _exact_decimal_json
    _exact_decimal_json()
    assert jsonable_encoder({"a": Decimal("50000.00"), "b": Decimal("0.10"), "c": Decimal("1500000.05")}) == {"a": "50000.00", "b": "0.10", "c": "1500000.05"}


def test_finance_controls_credit_remaining_is_decimal():
    from edusync.modules.finance_controls.domain.models import credit_remaining
    assert credit_remaining("0.30", "0.10") == Decimal("0.20")
    assert credit_remaining(10, 25) == Decimal("0")


def test_sign_in_has_no_school_code_and_offers_context_choice():
    s = (FRONT / "src/login.tsx").read_text(encoding="utf-8")
    assert "Code établissement" not in s and "schoolCode" not in s
    assert "loginAuto" in s and "choice_required" in s and "ContextChooser" in s
    api = (FRONT / "src/api.ts").read_text(encoding="utf-8")
    assert "scope:'AUTO'" in api


def test_login_background_is_a_local_licensed_asset():
    css = (FRONT / "src/login.css").read_text(encoding="utf-8")
    assert "url(/brand/login-campus.webp)" in css and "http" not in css.split("image-set", 1)[1].split(";", 1)[0]
    for name in ("login-campus.webp", "login-campus.jpg", "login-campus-1000.webp"):
        assert (FRONT / "public/brand" / name).stat().st_size < 400_000


def test_boot_screen_is_styled_inline_and_dismissed_after_session_check():
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    assert "<style>" in html and ".staticBoot{" in html and "/icons/edusync-mark.svg" in html
    app = (FRONT / "src/App.tsx").read_text(encoding="utf-8")
    assert "if(!restoring)dismissBoot()" in app


def test_platform_custom_roles_are_governed_in_database_and_registered():
    sql = (ROOT / "backend/migrations/0052_platform_governance.sql").read_text(encoding="utf-8")
    assert "PLATFORM_CUSTOM" in sql and "rbac_platform_role_capability_guard" in sql and "platform_reserved_capabilities" in sql
    assert "platform_account_status" in sql and "FORCE ROW LEVEL SECURITY" in sql
    prov = (ROOT / "backend/scripts/provision_database.py").read_text(encoding="utf-8")
    assert '"0052_platform_governance.sql"' in prov and '"platform_account_status"' in prov


def test_platform_actor_counts_only_active_platform_roles_and_checks_suspension():
    s = (ROOT / "backend/src/edusync/bootstrap/dependencies.py").read_text(encoding="utf-8")
    assert 'role.level.value == "PLATFORM" and role.status.value == "ACTIVE"' in s
    assert "platform_account_suspended(conn, user_id)" in s


def test_every_team_mutation_requires_the_reserved_team_capability_and_an_idempotency_key():
    import ast
    path = ROOT / "backend/src/edusync/modules/platform_team/api/router.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        verbs = [d.func.attr for d in node.decorator_list if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)]
        body = ast.get_source_segment(source, node) or ""
        if any(v in {"post", "put", "patch", "delete"} for v in verbs):
            assert "actor.require(TEAM_CAP)" in body and "_key(idempotency_key)" in body, node.name
    assert 'TEAM_CAP = "platform.collaborators.manage"' in source
    assert "_guard_target(c, actor, user_id)" in source and "_active_managers" in source


def test_school_suspension_has_real_effects_everywhere():
    platform = (ROOT / "backend/src/edusync/modules/platform/api/router.py").read_text(encoding="utf-8")
    assert "revoked_reason=coalesce(revoked_reason,'SCHOOL_SUSPENDED')" in platform
    iam = (ROOT / "backend/src/edusync/modules/iam/api/router.py").read_text(encoding="utf-8")
    assert "SELECT status FROM schools WHERE id=:sid" in iam
    docs = (ROOT / "backend/src/edusync/modules/documents/api/router.py").read_text(encoding="utf-8")
    assert "m.active AND s.status='ACTIVE'" in docs
    worker = (ROOT / "backend/src/edusync/modules/communications/worker.py").read_text(encoding="utf-8")
    assert "sc.status='ACTIVE'" in worker
    prov = (ROOT / "backend/scripts/provision_database.py").read_text(encoding="utf-8")
    assert 'GRANT SELECT (id, status) ON schools TO {WORKER_ROLE}' in prov and '"0053_school_suspension_effects.sql"' in prov


def test_notifications_are_unique_per_recipient_with_safe_links_and_no_real_push():
    sql = (ROOT / "backend/migrations/0055_notifications_center.sql").read_text(encoding="utf-8")
    assert "uq_notifications_campaign_recipient" in sql and "notifications_link_path_ck" in sql and "push_subscriptions" in sql
    push = (ROOT / "backend/src/edusync/shared/infrastructure/push.py").read_text(encoding="utf-8")
    assert "class DisabledPushProvider" in push and "class MockPushProvider" in push and '"body"' not in push
    from edusync.bootstrap.settings import Settings
    assert Settings(_env_file=None).push_provider == "disabled"
    router = (ROOT / "backend/src/edusync/modules/notifications_center/api/router.py").read_text(encoding="utf-8")
    assert "ON CONFLICT DO NOTHING" in router and "hashlib.sha256(body.endpoint" in router and "actor.require(SEND_CAP)" in router
