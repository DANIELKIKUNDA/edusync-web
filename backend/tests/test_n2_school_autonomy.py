"""N2 — a school administrates its own users (owner decisions 2026-10-14). Live behaviour: certification/n2-20261014/n2_probe.py."""
import ast
from pathlib import Path

from edusync.shared.infrastructure.security import new_temporary_password

ROOT = Path(__file__).resolve().parents[2]
ACCESS = (ROOT / "backend/src/edusync/modules/access/api/router.py").read_text(encoding="utf-8")
IAM = (ROOT / "backend/src/edusync/modules/iam/api/router.py").read_text(encoding="utf-8")


def _fn(source: str, name: str) -> str:
    body = source[source.index(f"def {name}("):]
    return body[:body.index("\n@router.") if "\n@router." in body else len(body)]


def test_member_routes_exist_and_use_the_owner_approved_capabilities():
    tree = ast.parse(ACCESS)
    paths = {d.args[0].value for n in tree.body if isinstance(n, ast.FunctionDef) for d in n.decorator_list
             if isinstance(d, ast.Call) and d.args and isinstance(d.args[0], ast.Constant)}
    for path in ("/members", "/members/{membership_id}", "/members/{membership_id}/deactivate", "/members/{membership_id}/activate",
                 "/members/{membership_id}/credentials-reset"):
        assert path in paths, path
    assert '_need(actor, "access.users.create")' in _fn(ACCESS, "create_member")
    assert '_need(actor, "access.users.update")' in _fn(ACCESS, "update_member")
    assert '_need(actor, "access.users.activate")' in _fn(ACCESS, "_set_member_active")
    assert '_need(actor, "access.users.credentials.reset")' in _fn(ACCESS, "reset_member_credentials")


def test_temporary_password_shown_once_never_stored_nor_replayed():
    create = _fn(ACCESS, "create_member")
    assert 'issued["temporary_password"] = temporary' in create and "return 201, out" in create
    assert '"temporary_password": temporary' not in create.split("issued[")[0]  # not in the registered response
    reset = _fn(ACCESS, "reset_member_credentials")
    assert "_idempotent" not in reset  # a lost response is answered by a new reset, never by an old password
    assert "must_change_password=true" in reset and "must_change_password,password_set_by" in create


def test_shared_accounts_are_never_reset_nor_renamed_by_a_school():
    assert "def _account_shared(" in ACCESS
    for fn in ("update_member", "reset_member_credentials"):
        assert "_account_shared(conn, m[\"user_id\"], actor.school_id)" in _fn(ACCESS, fn), fn


def test_targets_are_scoped_to_the_school_never_self_never_more_governance():
    target = _fn(ACCESS, "_target")
    assert "m.school_id=:s" in target and "str(actor.membership_id)" in target and "_governance(_member_caps(" in target


def test_anti_escalation_on_governance_capabilities():
    assert 'GOVERNANCE_PREFIX = "access."' in ACCESS
    for fn in ("create_role", "update_role", "assign", "create_member"):
        assert "_assert_can_delegate(actor," in _fn(ACCESS, fn), fn


def test_deactivation_keeps_an_access_manager_and_ends_sessions_of_this_school():
    body = _fn(ACCESS, "_set_member_active")
    assert "_assert_managers_remain(conn, actor.school_id)" in body and "_revoke_member_sessions(" in body and "version=version+1" in body


def test_first_sign_in_replaces_the_temporary_password_before_any_session():
    login = IAM[IAM.index("def login("):]
    assert login.index("must_change_password") < login.index('if body.scope == "AUTO"')
    first = _fn(IAM, "first_password_change")
    assert 'load_challenge(conn, services.settings, body.change_token, "PASSWORD")' in first
    assert "must_change_password=false" in first and "verify_password(body.new_password, user.password_hash)" in first
    assert "_issue_" not in first  # no session here: the client signs in again
    sql = (ROOT / "backend/migrations/0058_school_user_management.sql").read_text(encoding="utf-8")
    assert "must_change_password boolean NOT NULL DEFAULT false" in sql and "'PASSWORD'" in sql


def test_temporary_password_shape():
    pw = new_temporary_password()
    assert len(pw) == 14 and pw.count("-") == 2 and not any(c in pw for c in "0O1lI")
    assert len({new_temporary_password() for _ in range(50)}) == 50


def test_frontend_offers_member_management_and_first_sign_in_screen():
    access = (ROOT / "frontend/src/access.tsx").read_text(encoding="utf-8")
    for marker in ("AddMemberDialog", "MemberSheet", "SecretDialog", "credentials-reset", "Ajouter un membre", "Compte partagé"):
        assert marker in access, marker
    login = (ROOT / "frontend/src/login.tsx").read_text(encoding="utf-8")
    assert "PasswordChangeScreen" in login and "isPasswordChangeStep(r)" in login


def test_settings_centre_confirms_year_transitions_and_uploads_a_verified_logo():
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    years = app[app.index("function Years("):app.index("function Structure(")]
    assert "await confirmAction(confirmText[action](y))" in years and "Préparer une nouvelle année" in years
    assert "URL du logo" not in app and "<LogoField token={token}" in app and "uploadSchoolLogo(token,f)" in app
    assert "await confirmAction(off?" in app  # class deactivation is confirmed, never a silent toggle
    assert "settingsBack" in app and "edusyncSettingsDetail" in app  # phone: list of sections → section screen


def test_amounts_are_formatted_from_strings_never_through_floats():
    fmt = (ROOT / "frontend/src/platform/format.ts").read_text(encoding="utf-8")
    body = fmt[fmt.index("export function formatMoney("):fmt.index("export function formatDate(")]
    assert "Number(" not in body and "parseFloat" not in body
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    assert "formatMoney(t.amount,t.currency)" in app and "formatMoney(x.unit_price,x.currency)" in app


def test_sidebar_collapse_is_an_icon_button_with_rail_overlay_and_pin():
    shell = (ROOT / "frontend/src/platform/shell.tsx").read_text(encoding="utf-8")
    assert '<span className="es-nav-label">Réduire le menu</span>' not in shell  # no full-width "Réduire le menu" line
    assert "aria-label={collapseLabel}" in shell and "'Épingler le menu'" in shell
    assert "(hover:hover) and (pointer:fine)" in shell and "schedulePeek(true, 280)" in shell  # mouse only, after a delay
    assert ":focus-visible" in shell and "e.key === 'Escape' && peek" in shell  # keyboard opens it, Esc closes it
    assert "if (mq.matches) setDrawer(false)" in shell  # the phone drawer closes when the layout becomes desktop


def test_enrollment_rules_screen_matches_what_the_schooling_module_enforces():
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    uc = (ROOT / "backend/src/edusync/modules/schooling/application/use_cases.py").read_text(encoding="utf-8")
    for field in ("birth_date", "birth_place", "nationality", "address", "previous_school"):
        assert f"'{field}'" in app and f'"{field}"' in uc, field  # only fields the server accepts as extra requirements
    assert "guardian_required_at_enrollment:guardian" in app and "guardian_phone_required:phone" in app
    assert "can('settings.enrollment_policy.manage')" in app and "expected_version:policy?.version??null" in app


def test_readiness_is_a_guided_path_to_the_sections_that_settle_each_item():
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    assert "const READINESS_TARGET:Record<string,TabKey>={IDENTITY:'identity',ACADEMIC_YEAR:'years',STRUCTURE:'structure',FEE_TYPES:'fees',TARIFFS:'tariffs'}" in app
    assert "Prochaine étape" in app and "onOpen(READINESS_TARGET[next.code])" in app


def test_section_options_are_managed_without_deletion():
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    api = (ROOT / "frontend/src/api.ts").read_text(encoding="utf-8")
    assert "export async function putOption(" in api and "settings/options/${encodeURIComponent(input.code)}" in api
    assert "can('settings.options.manage')" in app and "expected_version:o.version" in app
    assert "Désactiver l’option" in app and "option_id:optionId||null" in app
