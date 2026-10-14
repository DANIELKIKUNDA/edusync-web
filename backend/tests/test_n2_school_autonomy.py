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
    assert "async function changeStatus(c:SchoolClass" in app and "await confirmAction(ask)" in app  # state changes are confirmed
    assert "settingsBack" in app and "edusyncSettingsDetail" in app  # phone: list of sections → section screen


def test_amounts_are_formatted_from_strings_never_through_floats():
    fmt = (ROOT / "frontend/src/platform/format.ts").read_text(encoding="utf-8")
    body = fmt[fmt.index("export function formatMoney("):fmt.index("export function formatDate(")]
    assert "Number(" not in body and "parseFloat" not in body
    app = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
    tariffs = (ROOT / "frontend/src/settings_tariffs.tsx").read_text(encoding="utf-8")
    assert "formatMoney(t.amount, t.currency)" in tariffs and "formatMoney(x.unit_price,x.currency)" in app


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


def test_first_school_admin_created_by_the_platform_must_choose_his_password():
    uc = (ROOT / "backend/src/edusync/modules/platform/application/use_cases.py").read_text(encoding="utf-8")
    body = uc[uc.index("class BootstrapSchoolAdmin:"):]
    new_user = body[body.index("else:"):body.index("membership = self.memberships.get_for_user_school")]
    assert 'self.users.require_password_change(user.id, set_by="PLATFORM")' in new_user  # only a NEW account
    assert "require_password_change" not in body[:body.index("else:")]  # an attached existing account keeps its password
    repo = (ROOT / "backend/src/edusync/adapters/postgres_repositories.py").read_text(encoding="utf-8")
    assert "UPDATE users SET must_change_password=true,password_set_by=:by" in repo


def test_class_states_copy_the_desktop_golden_master():
    sql = (ROOT / "backend/migrations/0059_class_status_desktop_parity.sql").read_text(encoding="utf-8")
    assert "CHECK (status IN ('ACTIVE', 'INACTIVE', 'ARCHIVED'))" in sql and "CHECK (enabled = (status = 'ACTIVE'))" in sql
    repo = (ROOT / "backend/src/edusync/adapters/postgres_settings.py").read_text(encoding="utf-8")
    start = repo.index("def set_class_status(")
    st = repo[start:repo.index("\n    def ", start + 10)]
    assert "Une classe contenant des inscriptions actives ne peut pas être archivée" in st and "status='VALIDATED'" in st
    assert "Une classe archivée ne change plus de statut" in st
    assert "if cls['year_status'] in ('CLOSED','ARCHIVED')" in repo  # Desktop _ensure_configuration_year_editable
    eff = (ROOT / "backend/src/edusync/adapters/postgres_effectifs.py").read_text(encoding="utf-8")
    assert "sc.status<>'ARCHIVED'" in eff and "AND sc.enabled AND" not in eff  # a paused class never leaves the headcounts
    sch = (ROOT / "backend/src/edusync/adapters/postgres_schooling.py").read_text(encoding="utf-8")
    assert "Classe cible inactive ou hors année active" in sch  # not a normal class-change destination


def test_class_state_and_rename_use_separate_capabilities():
    router = (ROOT / "backend/src/edusync/modules/settings/api/router.py").read_text(encoding="utf-8")
    upd = router[router.index("def update_class("):router.index("def change_class_status(")]
    assert "_need(actor,'settings.classes.rename')" in upd and "settings.classes.activate" not in upd
    assert "pas par un renommage" in upd  # a direct API call with enabled cannot reopen a class
    chg = router[router.index("def change_class_status("):]
    assert "_need(actor,'settings.classes.activate')" in chg.split("\n@router.")[0] and "SCHOOL_CLASS_STATUS_CHANGED" in chg


def test_tariff_rules_copy_the_desktop_resolution():
    repo = (ROOT / "backend/src/edusync/adapters/postgres_settings.py").read_text(encoding="utf-8")
    assert 'TARIFF_PRIORITY = {"CLASS": 600, "ACADEMIC_CLASS": 500, "OPTION_GROUP": 350, "SECTION": 200, "SCHOOL": 100}' in repo
    assert 'TARIFF_GROUPS = {"GENERAL": "Humanités générales", "TECHNICAL": "Humanités techniques", "OTHER": "Autre groupe"}' in repo
    assert "Un tarif actif doit avoir un montant" in repo and "La date d'effet doit appartenir à l'année scolaire" in repo
    assert "'PENDING_OFFICIAL' if m['status']=='ACTIVE' else m['status']" in repo  # copied year: amounts to confirm
    sql = (ROOT / "backend/migrations/0060_tariff_rules_desktop_parity.sql").read_text(encoding="utf-8")
    assert "DROP INDEX IF EXISTS uq_tariffs_active_exact_scope" in sql and "uq_tariffs_rule" in sql
    router = (ROOT / "backend/src/edusync/modules/settings/api/router.py").read_text(encoding="utf-8")
    put = router[router.index("def put_tariff_rule("):router.index("def resolve_tariff(")]
    assert "_need(actor,'settings.tariffs.manage')" in put and "_need(actor,'settings.tariff_groups.manage')" in put
    assert "_need(actor,'settings.billing_months.manage')" in router and "_need(actor,'settings.option_tariff_group.manage')" in router


def test_fee_schedules_and_due_charges_copy_the_desktop():
    repo = (ROOT / "backend/src/edusync/adapters/postgres_fee_schedules.py").read_text(encoding="utf-8")
    assert 'TERMS = (("T1", "1re tranche", 9), ("T2", "2e tranche", 1), ("T3", "3e tranche", 4))' in repo
    assert 'if rule["status"] != "ACTIVE" or rule["amount"] is None:' in repo and 'out["pending_skipped"] += 1' in repo
    assert "cette échéance contient déjà un paiement" in repo and "Impossible de réduire ce barème sous le montant déjà payé" in repo
    assert 'if fee["periodicity"] == "OPTIONAL":' in repo  # Web-only optional fees are never generated automatically
    sql = (ROOT / "backend/migrations/0061_fee_schedules_charge_generation.sql").read_text(encoding="utf-8")
    assert "uq_finance_charges_schedule" in sql and "GRANT UPDATE (label, currency, net_amount" in sql and "paid_amount" not in sql.split("GRANT UPDATE")[1]
    sch = (ROOT / "backend/src/edusync/adapters/postgres_schooling.py").read_text(encoding="utf-8")
    assert "La politique de transfert financier doit être décidée explicitement avant ce cas." in sch
    router = (ROOT / "backend/src/edusync/modules/settings/api/router.py").read_text(encoding="utf-8")
    assert "_need(actor,'settings.tariffs.apply')" in router


def test_benefit_policies_copy_the_desktop():
    uc = (ROOT / "backend/src/edusync/modules/schooling/application/use_cases.py").read_text(encoding="utf-8")
    for message in ("Un même élève ne peut pas cumuler deux réductions financières sans politique explicite",
                    "La politique Famille nombreuse n'est pas activée", "La politique Enfants du personnel n'est pas activée",
                    "Cette famille ne peut avoir que", "Cet agent ne peut avoir que"):
        assert message in uc, message
    assert 'return Decimal("100")' in uc and ">= 5" not in uc  # free = 100 %; no hard-coded threshold any more
    fees = (ROOT / "backend/src/edusync/adapters/postgres_fee_schedules.py").read_text(encoding="utf-8")
    assert 'fee_code.startswith(f"{applies}_")' in fees and "ORDER BY kind LIMIT 1" in fees
    router = (ROOT / "backend/src/edusync/modules/settings/api/router.py").read_text(encoding="utf-8")
    assert "_need(actor,'settings.benefits.manage')" in router
    wizard = (ROOT / "frontend/src/schooling.tsx").read_text(encoding="utf-8")
    assert "large_family_beneficiary" in wizard and "staff_beneficiary" in wizard and "enrollmentBenefits(token)" in wizard
