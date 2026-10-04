from decimal import Decimal
from edusync.modules.finance_recovery.domain.monthly import monthly_total

def test_total_does_not_sum_people_and_recalculates_rate():
 r=[{'expected':'100','cash_collected':'60','outside_cash':'10'},{'expected':'200','cash_collected':'100','outside_cash':'20'}];t=monthly_total(r);assert t['debtors'] is None and t['in_order'] is None and t['not_in_order'] is None;assert t['expected']==Decimal('300.00');assert t['regularized_total']==Decimal('190.00');assert t['remaining']==Decimal('110.00');assert t['recovery_rate']==Decimal('63.3')
def test_total_empty_safe():
 t=monthly_total([]);assert t['expected']==0 and t['recovery_rate']==0

def test_frontend_has_per_tab_exports_and_modern_labels():
 s=open('../frontend/src/recovery.tsx',encoding='utf8').read();assert 'Suivi mensuel' in s and 'Synthèse par classe' in s and "exp('pdf')" in s and "exp('xlsx')" in s
