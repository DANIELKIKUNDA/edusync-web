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

def test_actor_models_are_permission_driven_not_job_title_hardcoded():
    for model in ('GOVERNANCE','SCHOOL_DIRECTION','FINANCE','CASHIER','SECRETARIAT','INTENDANCE'):
        assert model in HOME
    assert "permissions:string[]" in HOME
    assert "finance.checkout.collect" in HOME and "inventory.stock.issue" in HOME

def test_secondary_school_direction_stays_schooling_first():
    assert "Effectifs de mon périmètre" in HOME
    assert "Lecture scolaire prioritaire; la finance reste secondaire." in HOME
    assert "Recouvrement de mon périmètre" in HOME

def test_cashier_knows_school_headcount_but_keeps_cash_first():
    assert "Poste de caisse" in HOME
    assert "Élèves actifs" in HOME
    assert "Encaisser rapidement" in HOME
    assert "Solde théorique CDF" in HOME

def test_recovery_monthly_is_scope_aware_for_prefet_and_secondary_directors():
    assert "scopes=()" in REC
    assert "upper(ss.code)=ANY(%s)" in REC
    assert "upper(sc.code)=ANY(%s)" in REC
    assert "actor.scopes_for('finance.recovery.monthly.read')" in ROUTER

def test_intendance_does_not_invent_point9_metrics():
    # Wording rewritten for end users (2026-10 certification); intent unchanged: no invented stewardship data.
    assert "Aucune donnée d’intendance n’est encore enregistrée" in HOME
