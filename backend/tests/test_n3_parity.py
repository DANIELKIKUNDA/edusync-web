"""N3 — Desktop → Web parity contracts (golden master: EduSync École Offline 0.11.0-rc.1). Live: certification/n3-20261015/."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(p: str) -> str:
    return (ROOT / p).read_text(encoding="utf-8")


def test_n3b_reversal_is_append_only_and_follows_desktop():
    repo = read("backend/src/edusync/adapters/postgres_cash_integrity.py")
    for message in ("Type de contre-opération invalide", "Le motif est obligatoire et doit être explicite",
                    "Ce paiement a déjà fait l'objet d'une contre-opération", "Catégorie et motif de dépense obligatoires",
                    "Montant ou devise invalide", "Un motif explicite est obligatoire pour rouvrir la caisse", "La caisse du jour n'est pas clôturée"):
        assert message in repo, message
    assert "UPDATE finance_payments" not in repo and "DELETE FROM finance_payments" not in repo
    sql = read("backend/migrations/0069_n3b_cash_integrity.sql")
    assert "REVOKE UPDATE, DELETE ON finance_payment_reversals, finance_cash_day_snapshots FROM edusync_tenant" in sql
    assert "NOT EXISTS (SELECT 1 FROM finance_payment_reversals rv WHERE rv.payment_id = a.payment_id)" in sql  # capacity guard


def test_n3b_authority_split_own_vs_supervisor():
    router = read("backend/src/edusync/modules/finance_cash/api/router.py")
    assert "can_own='finance.payments.reverse' in actor.permissions" in router
    assert "can_sup='finance.payments.reverse.supervisor' in actor.permissions" in router
    assert "need(actor,'finance.cash.day.close')" in router and "need(actor,'finance.cash.reopen')" in router
    assert "need(actor,'finance.cash.expense.create')" in router
    repo = read("backend/src/edusync/adapters/postgres_cash_integrity.py")
    assert "p[\"session_status\"] == \"OPEN\"" in repo and "SupervisorRequired" in repo
    assert "Clôturez d'abord les caisses individuelles" in repo


def test_n3b_closed_day_blocks_every_cash_entry_path():
    checkout = read("backend/src/edusync/adapters/postgres_finance_checkout.py")
    assert checkout.count("self._require_day_open(school_id,session)") == 3   # collect, family collect, product sale
    assert "co._require_day_open(school_id, session)" in read("backend/src/edusync/adapters/postgres_anticipation.py")
    assert "ci.require_day_open(actor.school_id,ci.today())" in read("backend/src/edusync/modules/finance_cash/api/router.py")


def test_n3b_documents_copy_desktop_layout():
    docs = read("backend/src/edusync/modules/finance_cash/application/documents.py")
    assert "JOURNAL DE CAISSE — " in docs and "RAPPORT FINANCIER JOURNALIER — " in docs
    assert "Les devises ne sont jamais additionnées entre elles" in docs


def test_n3b_mobile_ui_present():
    ui = read("frontend/src/cash_controls.tsx")
    for text in ("Dépense de caisse", "Contre-opération", "Clôturer la journée", "Rouvrir la journée", "Journal de caisse (PDF)", "Rapport journalier (PDF)"):
        assert text in ui, text
    assert "createPortal" in ui


def test_n3c_decisions_copy_desktop_rules():
    from decimal import Decimal
    from edusync.adapters.postgres_financial_decisions import FULL, KINDS, SCOPES, PostgresFinancialDecisionsRepository
    assert KINDS == {"DISCOUNT", "EXEMPTION", "INDIVIDUAL_FREE", "COLLECTIVE_EXEMPTION", "DIRECTION_EXCEPTION", "THIRD_PARTY_COVERAGE"}
    assert SCOPES == {"ALL_FEES", "FEE_CODE", "FEE_CATEGORY", "CHARGE"} and FULL == {"EXEMPTION", "INDIVIDUAL_FREE", "COLLECTIVE_EXEMPTION"}
    m = PostgresFinancialDecisionsRepository._matches
    ch = {"id": "c1", "fee_code": "SCOLARITE", "fee_category": "SCOLAIRE"}
    assert m({"scope_type": "ALL_FEES"}, ch) and m({"scope_type": "FEE_CODE", "scope_ref": "scolarite"}, ch)
    assert m({"scope_type": "CHARGE", "charge_id": "c1"}, ch) and not m({"scope_type": "CHARGE", "charge_id": "c2"}, ch)
    repo = read("backend/src/edusync/adapters/postgres_financial_decisions.py")
    for message in ("Portée ou nature de décision financière invalide", "La valeur doit être un pourcentage ou un montant fixe",
                    "Valeur de décision financière invalide", "Le motif de la décision financière est obligatoire",
                    "La cible de la décision financière est obligatoire", "Décision financière active introuvable",
                    "Le motif d'annulation est obligatoire", "La responsabilité prévue ne peut pas dépasser le restant réel de ce frais"):
        assert message in repo, message
    assert "if non_cumulative_applied and not d[\"cumulative\"]" in repo


def test_n3c_one_definition_of_decided_amount():
    sql = read("backend/migrations/0070_n3c_financial_decisions.sql")
    assert "CREATE OR REPLACE FUNCTION finance_charge_decision_amount" in sql and "CREATE OR REPLACE VIEW finance_charge_effective" in sql
    assert "v_obligation := v_net - finance_charge_decision_amount(NEW.charge_id)" in sql
    for f in ("backend/src/edusync/adapters/postgres_finance_checkout.py", "backend/src/edusync/modules/migration_import/api/router.py"):
        src = read(f)
        assert "finance_charge_decision_amount(" in src and "sum(d.amount) FROM finance_decisions" not in src, f
    assert "recalculate(school_id, enrollment_id)" in read("backend/src/edusync/adapters/postgres_fee_schedules.py")
