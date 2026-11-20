"""Owner, 2026-11-19: a weekly / monthly report that speaks like a real person, built only from real figures."""
from datetime import date

from pypdf import PdfReader
from io import BytesIO

from edusync.modules.finance_recovery.domain.digest import Digest, greeting, month_of, paragraphs, title, week_of
from edusync.modules.finance_recovery.application.digest_document import digest_pdf


def school_week():
    return Digest(kind="WEEK", start=date(2026, 11, 16), end=date(2026, 11, 21), school_name="C.S. ABBE P.N.",
                  cash={"total": 4250000, "previous": 3800000, "best_day": (date(2026, 11, 17), 1340000),
                        "entries": 4300000, "outflows": 50000, "net": 4250000,
                        "movements": [{"d": date(2026, 11, 17), "at": "2026-11-17T09:10:00", "direction": "ENTREE",
                                       "operation": "Paiement élève", "party": "Kikunda Élève", "reference": "REC-001",
                                       "reason": None, "amount": 4300000},
                                      {"d": date(2026, 11, 18), "at": "2026-11-18T11:00:00", "direction": "SORTIE",
                                       "operation": "Dépense", "party": "Fournitures", "reference": "DEP-001",
                                       "reason": "Craies", "amount": 50000}]},
                  recovery={"expected": 143275000, "regularized": 88975000, "remaining": 54300000, "rate": 62.1},
                  weakest_class={"label": "4e CG", "rate": 41}, pupils={"active": 558, "abandons": ["3e MA", "1re primaire"], "transfers": []},
                  attention={"reversals": 3, "open_sessions": 0})


def test_school_week_reads_like_a_letter():
    text = " ".join(t for _, t in paragraphs(school_week()))
    assert "L’école a encaissé 4 250 000 FC cette semaine, soit 12 % de plus que la période précédente." in text
    assert "Le meilleur jour a été mardi (1 340 000 FC)." in text
    assert "62,1 % de ce qui était attendu est rentré" in text and "La classe la plus en retard est la 4e CG (41 %)" in text
    assert "2 abandons cette semaine (3e MA, 1re primaire)." in text
    assert "3 reçus annulés" in text


def test_week_is_monday_to_saturday_and_titles():
    assert week_of(date(2026, 11, 19)) == (date(2026, 11, 16), date(2026, 11, 21))
    assert month_of(date(2026, 2, 10)) == (date(2026, 2, 1), date(2026, 2, 28))
    assert title(school_week()) == "Votre semaine à C.S. ABBE P.N. — du 16 novembre au 21 novembre 2026"


def test_greeting_uses_civility_and_title_with_elision():
    assert greeting("M", "Promoteur") == "Bonjour Monsieur le Promoteur,"
    assert greeting("MME", "Gestionnaire") == "Bonjour Madame la Gestionnaire,"
    assert greeting("M", "Assistant du promoteur") == "Bonjour Monsieur l’assistant du promoteur,"
    assert greeting(None, "Promoteur") == "Bonjour,"


def test_section_reader_has_no_money_part_and_nothing_invented():
    d = Digest(kind="MONTH", start=date(2026, 11, 1), end=date(2026, 11, 30), school_name="APN", scope_label="la section Secondaire",
               cash=None, recovery={"expected": 100, "regularized": 60, "remaining": 40, "rate": 60}, weakest_class=None,
               pupils={"active": 395, "abandons": [], "transfers": []})
    parts = dict(paragraphs(d))
    assert "L’argent" not in parts and "À surveiller" not in parts
    assert "dans votre section" in parts["Le recouvrement"] and "Aucun abandon ni transfert ce mois-ci." in parts["Les élèves"]
    assert "la section Secondaire" in paragraphs(d)[0][1]


def test_pdf_contains_the_letter_and_the_classes():
    pdf = PdfReader(BytesIO(digest_pdf(digest=school_week(), greeting="Bonjour Monsieur le Promoteur,", signature="EduSync — pour C.S. ABBE P.N.",
                                       classes=[{"class_label": "4e CG", "debtors": 23, "expected": 1000, "regularized_total": 410, "remaining": 590, "recovery_rate": 41}])))
    text = " ".join(" ".join(p.extract_text().split()) for p in pdf.pages)
    assert "Bonjour Monsieur le Promoteur," in text and "Recouvrement par classe" in text and "4e CG" in text
    assert "Justification des mouvements de caisse" in text
    assert "Total des entrées" in text and "Total des sorties" in text and "Solde net" in text
    assert "Paiement élève" in text and "REC-001" in text and "Dépense" in text and "DEP-001" in text


def test_pdf_justifies_fc_and_usd_separately():
    """Certification PR #109 (2026-11-20): USD movements were absent from the FC letter's ledger."""
    d = school_week()
    d.cash = {**d.cash, "entries": 4250000, "outflows": 0, "net": 4250000,
              "movements": [{"d": date(2026, 11, 17), "direction": "ENTREE", "operation": "Paiement élève", "party": "KABILA Jean", "reference": "REC-1", "amount": 85000}]}
    d.other_cash = {"USD": {"entries": 50, "outflows": 10, "net": 40, "movements": [
        {"d": date(2026, 11, 18), "direction": "ENTREE", "operation": "Paiement élève", "party": "MUTOMBO Paul", "reference": "REC-2", "amount": 50},
        {"d": date(2026, 11, 19), "direction": "SORTIE", "operation": "Annulation", "party": None, "reference": "REC-2", "reason": "erreur", "amount": 10}]}}
    pdf = PdfReader(BytesIO(digest_pdf(digest=d, greeting="Bonjour,", signature="EduSync", classes=[])))
    text = " ".join(" ".join(p.extract_text().split()) for p in pdf.pages)
    assert "Justification des mouvements de caisse" in text and "Justification des mouvements de caisse — USD" in text
    assert "KABILA Jean" in text and "MUTOMBO Paul" in text
    usd = text.split("— USD", 1)[1]
    assert "40 USD" in usd and "50 USD" in usd and "10 USD" in usd and "85 000 FC" not in usd
