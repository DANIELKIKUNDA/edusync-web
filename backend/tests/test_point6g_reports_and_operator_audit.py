from datetime import date
from edusync.modules.finance_reports.domain.models import period_bounds,validate_sections,SYSTEM_TEMPLATES

def test_periods():
 d=date(2026,9,13);assert period_bounds('TODAY',d)==(d,d);assert period_bounds('WEEK',d)[0]==date(2026,9,7);assert period_bounds('MONTH',d)[0]==date(2026,9,1)
def test_sections_fail_closed():
 assert validate_sections(['cash_summary','movements'])==['cash_summary','movements']
 try:validate_sections(['magic'])
 except ValueError:pass
 else:assert False
def test_system_reports_are_generic_not_school_specific():
 codes={x['code'] for x in SYSTEM_TEMPLATES};assert {'DAILY_CASH','CASH_JOURNAL','COLLECTIONS','CONSOLIDATED_CASH'}<=codes

def test_operator_tracking_domains_remain_distinct():
 # Decisions/exemptions, responsibility and residual credits are financially material;
 # they must not be deleted merely because "Suivi opérateur" is removed as a UI bucket.
 import pathlib
 reg=(pathlib.Path(__file__).parents[2]/'contracts'/'CAPABILITY_REGISTRY.json').read_text()
 for cap in ('finance.decisions.create','finance.responsibility.read','finance.credits.read'):assert cap in reg


def test_daily_financial_report_is_management_grade_and_preview_is_not_archived():
 from io import BytesIO
 from pypdf import PdfReader
 from edusync.modules.finance_cash.application.documents import daily_report_pdf
 report={
  "day":"2026-10-26","closed":False,"sessions":3,"open_sessions":1,"closed_at":None,
  "totals":[{"currency":"CDF","entries":"120000","outflows":"20000","net":"100000"},{"currency":"USD","entries":"10","outflows":"0","net":"10"}],
  "details":[{"source":"PAIEMENT_ELEVE","direction":"ENTREE","currency":"CDF","amount":"120000"}],
  "operations":[{"created_at":"2026-10-26T09:10:00","direction":"ENTREE","source":"PAIEMENT_ELEVE","party":"Élève Test","reference":"REC-001","amount":"120000","currency":"CDF","user_name":"Caissier Test"},
                {"created_at":"2026-10-26T11:10:00","direction":"SORTIE","source":"DEPENSE_JOURNALIERE","party":"Fournitures","reason":"Craies","reference":"DEP-001","amount":"20000","currency":"CDF","user_name":"Caissier Test"}],
 }
 data=daily_report_pdf(school_name="École Test",report=report)
 assert data.startswith(b"%PDF") and len(data)>1500
 text="\n".join((p.extract_text() or "") for p in PdfReader(BytesIO(data)).pages)
 for expected in ("RAPPORT FINANCIER JOURNALIER","Synthèse par devise","Ventilation par origine","Détail des entrées","TOTAL DÉTAIL DES ENTRÉES","Détail des sorties","TOTAL DÉTAIL DES SORTIES","Élève Test","Craies","Caissier Test","26/10/2026"):
  assert expected in text
 import pathlib
 route=(pathlib.Path(__file__).parents[2]/'backend/src/edusync/modules/finance_cash/api/router.py').read_text(encoding='utf-8')
 assert "preview:bool=Query(False)" in route
 assert "if not preview:" in route
 assert "'X-EduSync-Preview':'1' if preview else '0'" in route


def test_daily_report_writes_the_whole_justification_and_french_amounts():
    """Owner, 2026-11-21: « on n'écrit pas toute la justification que la caissière a écrite »."""
    from pathlib import Path
    from io import BytesIO
    from pypdf import PdfReader
    from edusync.modules.finance_cash.application.documents import daily_report_pdf
    long_reason = "achat produit hygiénique pour les toilettes des élèves de la maternelle et du primaire (savon, papier, désinfectant)"
    report = {"day": "2026-11-21", "closed": False, "sessions": 1, "open_sessions": 1, "closed_at": None,
              "totals": [{"currency": "CDF", "entries": "1110000", "outflows": "50000", "net": "1060000"}],
              "details": [], "operations": [{"created_at": "2026-11-21T04:25:00", "direction": "SORTIE", "source": "DEPENSE_JOURNALIERE",
                                             "party": "fourniture", "reason": long_reason, "reference": "fourniture", "amount": "50000",
                                             "currency": "CDF", "user_name": "Caissière"}]}
    text = " ".join(" ".join((p.extract_text() or "").split()) for p in PdfReader(BytesIO(daily_report_pdf(school_name="APN", report=report, prepared_by="Mwadi Fany"))).pages)
    text = text.replace(" ", " ")
    assert "désinfectant)" in text and "toilettes des élèves" in text
    assert "1 110 000 FC" in text and "1 060 000 FC" in text and "1110000.00" not in text
    assert "Journée non clôturée" in text and "Visa de la direction" in text
    assert "Établi par" in text and "Mwadi Fany, le" in text and "Caissier(s) de la journée : Caissière" in text
    route = (Path(__file__).resolve().parents[1] / 'src/edusync/modules/finance_cash/api/router.py').read_text(encoding='utf-8')
    assert 'daily_report_pdf(school_name=name,report=r,prepared_by=me)' in route
