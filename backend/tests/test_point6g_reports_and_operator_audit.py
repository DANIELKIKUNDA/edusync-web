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
  "operations":[{"created_at":"2026-10-26T09:10:00","source":"PAIEMENT_ELEVE","reference":"REC-001","amount":"120000","currency":"CDF","user_name":"Caissier Test"}],
 }
 data=daily_report_pdf(school_name="École Test",report=report)
 assert data.startswith(b"%PDF") and len(data)>1500
 text="\n".join((p.extract_text() or "") for p in PdfReader(BytesIO(data)).pages)
 for expected in ("RAPPORT FINANCIER JOURNALIER","Synthèse par devise","Ventilation par origine","Opérations de la journée","Caissier Test","26/10/2026"):
  assert expected in text
 route=(ROOT/'backend/src/edusync/modules/finance_cash/api/router.py').read_text(encoding='utf-8')
 assert "preview:bool=Query(False)" in route
 assert "if not preview:" in route
 assert "'X-EduSync-Preview':'1' if preview else '0'" in route
