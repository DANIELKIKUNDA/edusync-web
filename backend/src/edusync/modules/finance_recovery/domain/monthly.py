from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

MONEY=Decimal('0.01')
def D(v): return Decimal(str(v or 0)).quantize(MONEY)
def pct(num:Decimal,den:Decimal)->Decimal:
    return (num*Decimal(100)/den).quantize(Decimal('0.1'),rounding=ROUND_HALF_UP) if den>0 else Decimal(0)

def monthly_total(rows:Iterable[dict])->dict:
    rows=list(rows); expected=sum((D(r['expected']) for r in rows),Decimal(0)); cash=sum((D(r['cash_collected']) for r in rows),Decimal(0)); outside=sum((D(r['outside_cash']) for r in rows),Decimal(0)); noncash=sum((D(r.get('noncash',0)) for r in rows),Decimal(0)); regularized=cash+noncash+outside; remaining=max(Decimal(0),expected-regularized)
    # Debtor / in-order counts are intentionally NOT summed across months: the same learner may occur repeatedly.
    return {'month':'TOTAL','month_label':'TOTAL GÉNÉRAL','debtors':None,'in_order':None,'not_in_order':None,'expected':D(expected),'cash_collected':D(cash),'noncash':D(noncash),'outside_cash':D(outside),'regularized_total':D(regularized),'remaining':D(remaining),'recovery_rate':pct(regularized,expected),'cash_recovery_rate':pct(cash,expected)}
