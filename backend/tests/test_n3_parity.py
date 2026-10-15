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


def test_n3d_advance_funds_copy_desktop_and_stay_separate_from_plans():
    repo = read("backend/src/edusync/adapters/postgres_advance_funds.py")
    for message in ("Les fonds anticipés sont désactivés dans la configuration de l'école", "Ce fonds anticipé n'a plus de solde disponible",
                    "Montant d'allocation invalide", "Aucune charge exigible n'est disponible pour cette allocation",
                    "Un fonds déjà alloué ne peut pas être annulé/remboursé globalement sans correction détaillée", "Ce fonds n'est plus actif",
                    "Cette décision a produit un crédit déjà utilisé; une régularisation explicite est requise"):
        assert message in repo, message
    for plan_table in ("anticipation_plans", "anticipation_memberships", "anticipation_payment_links", "finance_advance_allocations "):
        assert plan_table not in repo, plan_table          # Plan anticipé ≠ fonds anticipé
    sql = read("backend/migrations/0071_n3d_advance_funds.sql")
    assert "REVOKE UPDATE, DELETE ON finance_advance_funds, finance_advance_fund_allocations, finance_advance_fund_closures FROM edusync_tenant" in sql
    assert "CREATE OR REPLACE VIEW finance_advance_fund_state" in sql and "trg_advance_fund_allocation_capacity" in sql
    router = read("backend/src/edusync/modules/finance_checkout/api/router.py")
    for cap in ("finance.advance_funds.receive", "finance.advance_funds.read", "finance.advance_funds.allocate", "finance.advance_funds.refund",
                "finance.advance_funds.receipt.print"):
        assert f"need(actor,'{cap}')" in router, cap
    decisions = read("backend/src/edusync/adapters/postgres_financial_decisions.py")
    assert "ensure_decision_credit" in decisions and "close_decision_credits" in decisions


def test_n3e_sequence_scope_and_consecutive_periods():
    from decimal import Decimal
    from uuid import uuid4
    import pytest
    from edusync.modules.finance_checkout.domain.models import DueCharge, NON_SEQUENTIAL, validate_selection
    sep, oct_, nov = (DueCharge(uuid4(), "Frais scolaires", "CDF", Decimal("20000"), periodicity="MONTHLY", period_label=m, period_order=i,
                                sequence_group="MONTHLY:SCOLARITE", sequence_order=i) for i, m in enumerate(("Septembre", "Octobre", "Novembre"), 1))
    with pytest.raises(ValueError, match="ne peut pas être encaissée avant"):
        validate_selection([sep, oct_, nov], [oct_.id])
    assert validate_selection([sep, oct_, nov], [sep.id, oct_.id]) == Decimal("40000")     # consecutive periods, one receipt
    bus = DueCharge(uuid4(), "Transport", "CDF", Decimal("5000"), periodicity="MONTHLY", period_label="Novembre", period_order=3, sequence_group=NON_SEQUENTIAL)
    assert bus.chain is None and validate_selection([sep, bus], [bus.id]) == Decimal("5000")
    sql = read("backend/migrations/0072_n3e_checkout_sequence.sql")
    assert "'MONTHLY:SCOLARITE'" in sql and "'NONE'" in sql
    assert '"MONTHLY:SCOLARITE" if scolarite else "NONE"' in read("backend/src/edusync/adapters/postgres_fee_schedules.py")


def test_n3e_guidance_copies_desktop():
    repo = read("backend/src/edusync/adapters/postgres_finance_checkout.py")
    assert "Aucune échéance actuellement exigible. Le prochain frais est futur." in repo
    assert "Le montant dépasse les frais sélectionnés ou actuellement exigibles" in repo
    router = read("backend/src/edusync/modules/finance_checkout/api/router.py")
    assert "codes:str=Query('JOURNAL_CLASSE,ECUSSON'" in router
    ui = read("frontend/src/finance.tsx")
    assert "Action conseillée" in ui and "Journal + écusson" in ui and "c.requires" in ui


def test_n3f_payroll_deduction_is_noncash():
    repo = read("backend/src/edusync/adapters/postgres_staff_finance.py")
    for message in ("Activez d'abord le mode « retenue à la source » pour cet enfant", "Une ligne choisie n'est plus due",
                    "Montant de retenue supérieur au reste dû", "Le motif d'annulation est obligatoire", "Cette régularisation n'est plus active",
                    "Inscription ou lien agent-enfant introuvable"):
        assert message in repo, message
    for forbidden in ("INSERT INTO finance_payments", "next_receipt_number", "finance_cash_sessions"):
        assert forbidden not in repo, forbidden
    sql = read("backend/migrations/0073_n3f_payroll_deductions.sql")
    assert "REVOKE UPDATE, DELETE ON finance_noncash_settlements, finance_noncash_cancellations FROM edusync_tenant" in sql
    assert "trg_noncash_settlement_capacity" in sql
    ui = read("frontend/src/staff_finance_ui.tsx")
    assert "Confirmer une retenue" in ui and "Aucune entrée de caisse ni reçu n’est créé" in ui
