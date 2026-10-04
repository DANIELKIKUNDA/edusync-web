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
