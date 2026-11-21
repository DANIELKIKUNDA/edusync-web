"""Owner, 2026-11-21: « oui tu peux faire ça pour modifier » — a member's e-mail (sign-in and report address) can be corrected."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_route_is_guarded_audited_and_ends_sessions():
    src = (ROOT / 'backend/src/edusync/modules/access/api/router.py').read_text(encoding='utf-8')
    body = src.split("def change_member_email(", 1)[1].split("\n# ----", 1)[0]
    assert '_need(actor, "access.users.update")' in body and "Idempotency-Key obligatoire" in body
    assert "_target(conn, actor, membership_id)" in body and "_account_shared(" in body
    assert "lower(email::text)=:e AND id<>:u" in body
    assert body.count("account_links.security_alert(") == 2          # old address, then the new one
    assert "user_device_sessions SET revoked_at" in body and "ACCESS_MEMBER_EMAIL_CHANGED" in body


def test_member_sheet_offers_the_change_with_a_reason():
    ui = (ROOT / 'frontend/src/access.tsx').read_text(encoding='utf-8')
    assert "members/${member.membership_id}/email" in ui and "Modifier l’adresse e-mail" in ui
    assert "disabled={member.shared_account||locked||busy} onClick={()=>void changeEmail()}" in ui


def test_ci_runs_the_postgres_integration():
    ci = (ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8')
    assert "tools/ci/member_email_postgres_integration.py" in ci
