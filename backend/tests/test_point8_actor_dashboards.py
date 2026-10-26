from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HOME=(ROOT/'frontend/src/home.tsx').read_text(encoding='utf-8')
APP=(ROOT/'frontend/src/App.tsx').read_text(encoding='utf-8')
REC=(ROOT/'backend/src/edusync/adapters/postgres_finance_recovery.py').read_text(encoding='utf-8')
ROUTER=(ROOT/'backend/src/edusync/modules/finance_recovery/api/router.py').read_text(encoding='utf-8')

def test_home_is_real_and_default():
    assert "useState('home')" in APP
    assert '<HomePage' in APP
    assert 'Tableau de bord général à porter dans un lot suivant' not in APP

PROJ=(ROOT/'backend/src/edusync/modules/access/application/projection.py').read_text(encoding='utf-8')


def test_actor_dashboards_are_capability_driven_not_job_title_hardcoded():
    # Owner decision 9 (2026-10-23): no profile guessed in the browser — each widget declares its capabilities server-side.
    assert "modelOf" not in HOME and "GOVERNANCE" not in HOME and "permissions:string[]" not in HOME
    assert "me:AccessMe" in HOME and "me.widgets" in HOME
    for wid, cap in (("cash.today", "finance.cash.open"), ("cash.supervision", "finance.cash.other.read"), ("checkout.quick", "finance.checkout.collect"), ("headcounts.summary", "headcounts.read"),
                     ("finance.recovery", "finance.recovery.monthly.read"), ("inventory.stock", "inventory.stock.read"), ("access.members", "access.users.read")):
        assert f'"id": "{wid}"' in PROJ and f'"{cap}"' in PROJ


def test_school_direction_sees_headcounts_and_its_scoped_recovery():
    assert '"id": "headcounts.summary"' in PROJ and '"id": "headcounts.movements"' in PROJ and '"id": "finance.recovery"' in PROJ


def test_cashier_keeps_cash_first():
    assert "Ma caisse du jour" in PROJ and "Encaisser rapidement" in PROJ and "Solde théorique CDF" in HOME


def test_recovery_monthly_is_scope_aware_for_prefet_and_secondary_directors():
    assert "scopes=()" in REC
    assert "upper(ss.code)=ANY(%s)" in REC
    assert "upper(sc.code)=ANY(%s)" in REC
    assert "actor.scopes_for('finance.recovery.monthly.read')" in ROUTER

def test_intendance_does_not_invent_point9_metrics():
    # Stewardship cards show real stock alerts / counts only; an empty state says so instead of inventing figures.
    assert "Aucun stock sous son seuil d’alerte." in HOME and "Aucun inventaire en cours." in HOME


def test_governance_dashboard_has_supervision_not_operator_cash():
    # Governance sees the school's cash situation; only an operator with cash.open sees « Ma caisse du jour ».
    assert '"id": "cash.supervision"' in PROJ
    assert '"all": ("finance.cash.other.read",)' in PROJ
    assert "Situation des caisses" in PROJ
    assert "Vue d’ensemble" in HOME
    assert "Les indicateurs essentiels de l’établissement, sans actions opérationnelles." in HOME
