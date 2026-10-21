"""Change of space without signing out (lot 2026-10): contracts. Switches in every direction, forged / unknown /
suspended / withdrawn targets, no pile of sessions, the old token dead at once, 1 / 2 / 10 spaces and the absence of
permission leaks are proven against the real local stack by tools/local/switch_probe.py."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IAM = (ROOT / "backend/src/edusync/modules/iam/api/router.py").read_text(encoding="utf-8")
DEPS = (ROOT / "backend/src/edusync/bootstrap/dependencies.py").read_text(encoding="utf-8")
SPACES = (ROOT / "frontend/src/platform/spaces.tsx").read_text(encoding="utf-8")
APP = (ROOT / "frontend/src/App.tsx").read_text(encoding="utf-8")
LOGIN = (ROOT / "frontend/src/login.tsx").read_text(encoding="utf-8")
CONN = (ROOT / "frontend/src/platform/connectivity.ts").read_text(encoding="utf-8")
SWITCH = IAM.split('@router.post("/switch")', 1)[1]


def test_switch_is_server_checked_and_same_origin():
    assert '@router.get("/contexts")' in IAM and '@router.post("/switch")' in IAM
    assert "_assert_same_origin(request, services)" in SWITCH.split("def _switch_to", 1)[0]
    # the target is checked again like at sign-in: platform role and status, or active school and active membership
    assert "allowed = _platform_access_ok(conn, user.id)" in SWITCH
    assert "school.status == SchoolStatus.ACTIVE and membership and membership.active" in SWITCH
    assert 'scope: Literal["PLATFORM", "SCHOOL"]' in IAM


def test_refusal_is_audited_outside_the_rolled_back_transaction():
    head = SWITCH.split("def _switch_to", 1)[0]
    assert head.index('action="CONTEXT_SWITCH_REFUSED"') > head.index("# the refusal is written in its own transaction")
    assert 'raise HTTPException(403, "Cet espace ne vous est pas (ou plus) ouvert.")' in head


def test_session_is_replaced_and_second_factor_carried_never_step_up():
    body = SWITCH.split("def _switch_to", 1)[1]
    assert "revoked_reason='CONTEXT_SWITCH'" in body and 'action="CONTEXT_SWITCHED"' in body
    assert 'carried = row["mfa_verified_at"] if needs_mfa else None' in body
    assert "CASE WHEN CAST(:mva AS timestamptz) IS NULL AND CAST(:mfa AS text) IS NOT NULL THEN now() END" in IAM  # step-up not carried
    assert "def _retire_browser_session(" in IAM and IAM.count("_retire_browser_session(conn, request, services, user.id)") == 2


def test_withdrawn_space_is_signalled_to_the_client():
    assert 'SPACE_WITHDRAWN = {"X-EduSync-Space": "WITHDRAWN"}' in DEPS
    for d in ("Appartenance école révoquée", "École inactive ou inaccessible", "Accès à la plateforme EduSync suspendu"):
        assert f'detail="{d}", headers=SPACE_WITHDRAWN' in DEPS
    assert "r.headers.get('X-EduSync-Space')==='WITHDRAWN'" in CONN and "edusync:space-check" in CONN


def test_frontend_switcher_contract():
    for x in ("Changer d’espace", "Rechercher un espace", "Espace actuel", "Modifications non enregistrées", "hasUnsavedForms()",
              "Hors connexion — lecture seule", "Accès à cet espace retiré", "un rôle plateforme n’ouvre aucune école"):
        assert x in SPACES, x
    assert "const many=(state?.contexts.length||0)>6;" in SPACES
    # the previous space is unmounted entirely; each space keeps its own page and filters
    assert "key={`school:${schoolSession.school.id}`}" in APP and "sessionStorage.setItem(`edusync.url.${activeKey}`" in APP
    assert "spaces&&spaces.contexts.length>1?()=>setSwitching(true):undefined" in APP
    assert "Choisissez votre espace de travail" in LOGIN and "Dernier espace utilisé" in LOGIN
    assert "Atelier Pro" not in LOGIN
