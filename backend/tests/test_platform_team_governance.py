"""Équipe plateforme (lot 2026-10): governance contracts. The live behaviour (RBAC over HTTP, same user_id, races,
last Manager under real concurrency, expiry, audit) is proven by tools/local/team_probe.py against a real database."""
from pathlib import Path

from edusync.modules.platform_team.api.router import GrantInput, MemberAdd, UserCreate

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "backend/src/edusync"
ROUTER = (SRC / "modules/platform_team/api/router.py").read_text(encoding="utf-8")
DEPS = (SRC / "bootstrap/dependencies.py").read_text(encoding="utf-8")
MIG = (ROOT / "backend/migrations/0080_platform_capability_grants.sql").read_text(encoding="utf-8")
TEAM = (ROOT / "frontend/src/platform/team.tsx").read_text(encoding="utf-8")
TEAM_API = (ROOT / "frontend/src/platform/team_api.ts").read_text(encoding="utf-8")


def fn(name: str) -> str:
    start = ROUTER.index(f"def {name}(")
    nxt = ROUTER.find("\n@router", start)
    return ROUTER[start:nxt if nxt > 0 else len(ROUTER)]


def test_effective_capabilities_are_a_deterministic_union_recomputed_each_request():
    body = DEPS[DEPS.index("def platform_permissions("):DEPS.index("def platform_account_suspended(")]
    assert "frozenset({code for role in roles for code in role.capability_codes} | set(grants))" in body
    assert "if not roles:\n        return frozenset()" in body                     # a grant never works without a role
    assert "valid_until IS NULL OR valid_until>now()" in body                      # a temporary grant ends by itself
    assert "cache" not in body.lower().replace("no cache", "")


def test_migration_guards_grants_in_the_database():
    assert "0080_platform_capability_grants.sql" in (ROOT / "backend/scripts/provision_database.py").read_text(encoding="utf-8")
    for x in ("ux_platform_capability_grants_active", "WHERE active", "platform_reserved_capabilities", "scope_types ? 'PLATFORM'",
              "FORCE ROW LEVEL SECURITY", "CHECK (valid_until IS NULL OR valid_until > valid_from)", "end_kind IN ('REVOKED','EXPIRED','ACCESS_REMOVED')"):
        assert x in MIG, x
    assert "DELETE" not in MIG.split("GRANT", 1)[1].split(";", 1)[0]               # grants are ended, never deleted
    naming = MIG.split("-- Naming", 1)[1]
    assert naming.count("SET description = '") == 2 and naming.count("Plateforme EduSync") == 2 and "kind = 'PLATFORM_STANDARD'" in naming


def test_nobody_types_someone_elses_password():
    assert "password" not in UserCreate.model_fields and UserCreate.model_fields["delivery"].default == "INVITATION"
    create = fn("team_create_user")
    assert "new_temporary_password()" in create and 'issued.get("temporary_password")' in create and "no-store" in create
    assert '"temporary_password"' not in create.split("_audit(", 1)[1].split(")", 1)[0]
    assert "account_links.issue(" in create and "must_change_password" in create
    assert "IntegrityError" in create                                              # concurrent creation of one address


def test_existing_identity_keeps_the_same_user_id_and_school_access():
    add = fn("team_add_existing")
    assert "INSERT INTO users" not in add and "_is_member(c, user_id)" in add and "school_memberships_kept" in add
    assert set(MemberAdd.model_fields) == {"role_codes", "reason"}
    remove = fn("team_remove_access")
    assert "school_memberships" in remove and "DELETE" not in remove and "UPDATE school_memberships" not in remove
    assert "a.school_id IS NULL" in remove and "_end_grants(c, user_id, actor, \"ACCESS_REMOVED\"" in remove


def test_individual_grants_follow_the_delegation_rules():
    grant = fn("team_grant_capability")
    for x in ("actor.require(TEAM_CAP)", "require_recent_mfa(", "_guard_target(c, actor, user_id)", "_check_capabilities(c, actor, [code])",
              "_active_role_codes(c, user_id)", "effective_before", "effective_after"):
        assert x in grant, x
    check = ROUTER[ROUTER.index("def _check_capabilities("):ROUTER.index("def _role(")]
    assert "reserved" in check and "x not in actor.permissions" in check           # non-delegable + no delegation beyond one's rights
    assert "allow_self" in ROUTER and "Action impossible sur votre propre compte" in ROUTER   # no self-elevation
    assert set(GrantInput.model_fields) == {"capability_code", "reason", "valid_until"}


def test_last_manager_lock_is_taken_first_everywhere():
    lock = "pg_advisory_xact_lock(hashtext('edusync:platform:managers'))"
    for name in ("team_revoke_role", "team_remove_access", "_set_status"):
        body = fn(name)
        assert lock in body, name
        assert body.index(lock) < body.index("FOR UPDATE"), f"{name}: the Manager lock must precede any row lock (no deadlock)"
        assert "_active_managers(c, exclude_user=user_id) == 0" in body, name


def test_governance_mutations_are_idempotent():
    for name, action in (("team_create_user", "PLATFORM_USER_CREATED"), ("team_add_existing", "PLATFORM_MEMBER_ADDED"),
                         ("team_remove_access", "PLATFORM_ACCESS_REVOKED"), ("team_grant_capability", "PLATFORM_CAPABILITY_GRANTED"),
                         ("team_revoke_capability", "PLATFORM_CAPABILITY_REVOKED"), ("team_assign_role", "PLATFORM_ROLE_ASSIGNED"),
                         ("team_revoke_role", "PLATFORM_ROLE_REVOKED"), ("team_resend_invitation", "PLATFORM_INVITATION_RESENT"),
                         ("team_reset_password", "PLATFORM_USER_PASSWORD_RESET")):
        assert f'_replayed(c, actor, key, "{action}")' in fn(name), name


def test_expiry_is_audited_once_and_grants_never_revive():
    sweep = ROUTER[ROUTER.index("def _sweep_expired_grants("):ROUTER.index("def _end_grants(")]
    assert "PLATFORM_CAPABILITY_GRANT_EXPIRED" in sweep and "WHERE active AND valid_until IS NOT NULL AND valid_until<=now()" in sweep
    assert "_end_grants(c, user_id, actor, \"ACCESS_REMOVED\"" in fn("team_revoke_role")
    assert "_end_grants(c, uid, actor, \"ACCESS_REMOVED\"" in ROUTER[ROUTER.index("def _set_role_status("):]


def test_custom_role_edit_is_explained_and_audited():
    upd = fn("team_update_role")
    assert "members_affected" in upd and '"added"' in upd and '"removed"' in upd and "Motif obligatoire" in upd
    assert 'role["kind"] != "PLATFORM_CUSTOM"' in upd                               # standard roles are immutable


def test_no_atelier_pro_remainder_in_the_module():
    for text in (ROUTER, TEAM, TEAM_API):
        assert "Atelier Pro" not in text
    for msg in ("Jeton Atelier Pro", "Accès Atelier Pro", "rôle Atelier Pro"):
        assert msg not in DEPS


def test_frontend_two_paths_preview_and_read_only_directory():
    for x in ("Nouvelle identité", "Utilisateur existant", "Vérifier avant validation", "Capacités héritées du rôle", "Capacités supplémentaires",
              "Total effectif", "Capacités critiques non délégables", "Attribution individuelle", "Avant", "Après",
              "Retirer l’accès plateforme", "Suspension temporaire", "Retrait définitif", "Renvoyer l’invitation", "Activation en attente",
              "Je confirme la promotion au rôle Manager Système.", "Cette modification affectera", "Standard · non modifiable", "Cloner"):
        assert x in TEAM or x in TEAM_API, x
    assert "useRef(newKey())" in TEAM and "'Idempotency-Key': key" in TEAM_API          # one key per user action
    assert "Rechercher</button>" not in TEAM and "window.setTimeout(() => set({q: qInput}), 300)" in TEAM
    identities = (ROOT / "frontend/src/platform/identities.tsx").read_text(encoding="utf-8")
    assert "platformGrantCollaborator" not in identities and "onOpenTeam({openMember" in identities
