"""Role-by-role pass (owner, 2026-11-08): menus and homes follow what each standard role actually does."""
import json
from pathlib import Path

from edusync.modules.access.application import projection as P

ROOT = Path(__file__).resolve().parents[2]
ROLES = json.loads((ROOT / "contracts/CAPABILITY_REGISTRY.json").read_text(encoding="utf-8"))["standard_roles"]


def caps(role):
    return set(ROLES[role]["capabilities"])


def nav(role):
    return [n["label"] for n in P.navigation(caps(role))]


def test_settings_come_last_and_daily_work_first():
    for role, v in ROLES.items():
        if v.get("level") != "SCHOOL":
            continue
        labels = nav(role)
        assert labels[0] == "Accueil"
        if "Paramètres" in labels:
            assert labels[-1] == "Paramètres", (role, labels)


def test_who_reads_the_journal_without_managing_access_sees_an_audit_journal():
    for role in ("PROMOTEUR", "GESTIONNAIRE", "RESPONSABLE_FINANCE"):
        assert "Journal d’audit" in nav(role) and "Accès & rôles" not in nav(role), role
    assert "Accès & rôles" in nav("ADMIN_SYSTEME_ECOLE")


def test_menu_names_say_what_the_member_does():
    assert "Élèves & inscriptions" in nav("CAISSIER") and "Centre financier" in nav("CAISSIER")
    for role in ("PROMOTEUR", "PREFET_ETUDES", "SECRETARIAT"):
        assert "Élèves" in nav(role) and "Élèves & inscriptions" not in nav(role), role


def test_the_search_bar_is_for_those_who_handle_pupils_files():
    def has_search(role):
        return any(a["id"] == "students.search" for a in P.actions(caps(role)))
    for role in ("PROMOTEUR", "GESTIONNAIRE", "RESPONSABLE_FINANCE"):
        assert not has_search(role), role
    for role in ("CAISSIER", "SECRETARIAT", "PREFET_ETUDES", "DIRECTION_SECTION", "DIRECTEUR_DISCIPLINE", "DIRECTEUR_ETUDES"):
        assert has_search(role), role


def test_money_card_for_executives_and_for_section_leaders_given_the_finances():
    def ids(role):
        return [w["id"] for w in P.widgets(caps(role))]
    for role in ("PROMOTEUR", "GESTIONNAIRE", "RESPONSABLE_FINANCE", "PREFET_ETUDES", "DIRECTION_SECTION"):
        assert ids(role)[0] == "finance.pilotage" or "finance.pilotage" in ids(role), role
    for role in ("CAISSIER", "SECRETARIAT", "INTENDANT", "DIRECTEUR_ETUDES"):
        assert "finance.pilotage" not in ids(role), role
    assert "audit.recent" not in ids("PROMOTEUR") and "audit.recent" in ids("ADMIN_SYSTEME_ECOLE")


def test_section_leaders_see_their_section_money_never_the_school_cash():
    src = (ROOT / "backend/src/edusync/modules/finance_recovery/api/router.py").read_text(encoding="utf-8")
    block = src.split("def pilotage(", 1)[1]
    assert "sees_cash='finance.cash.other.read' in actor.permissions" in block and "cash=None" in block
    assert "scopes=actor.scopes_for('finance.recovery.monthly.read')" in block


def test_the_promoteur_reads_reports_but_does_not_produce_official_ones():
    """Owner, 2026-11-08: no « Générer le rapport officiel » for the promoteur (nor his assistant, a clone of the role)."""
    def producer(role):
        c = caps(role)
        supervises_only = "finance.cash.other.read" in c and not ({"finance.decisions.create", "finance.receipts.print", "finance.checkout.collect"} & c)
        return not supervises_only
    assert not producer("PROMOTEUR")
    for role in ("GESTIONNAIRE", "RESPONSABLE_FINANCE", "CAISSIER", "PREFET_ETUDES", "DIRECTION_SECTION"):
        assert producer(role), role
    hub = (ROOT / "frontend/src/reports_hub.tsx").read_text(encoding="utf-8")
    assert "can('finance.cash.other.read') && !can('finance.decisions.create') && !can('finance.receipts.print') && !can('finance.checkout.collect')" in hub
    assert "{official && <button" in hub


def test_the_cashier_sees_the_family_financial_situation_like_the_promoteur():
    router = (ROOT / "backend/src/edusync/modules/finance_fee_tracking/api/router.py").read_text(encoding="utf-8")
    assert "('finance.analysis.by_fee.read','finance.checkout.balance.read')" in router
    assert "finance.checkout.balance.read" in caps("CAISSIER")
    assert "(can('finance.analysis.by_fee.read')||can('finance.checkout.balance.read'))" in (ROOT / "frontend/src/schooling.tsx").read_text(encoding="utf-8")


def test_one_family_list_at_a_time():
    ui = (ROOT / "frontend/src/schooling.tsx").read_text(encoding="utf-8")
    assert "onMetricChange={setFamilyMetric}" in ui and "tab==='families'&&!familyMetric&&<FamilyDirectory" in ui
