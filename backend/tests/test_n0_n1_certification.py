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
