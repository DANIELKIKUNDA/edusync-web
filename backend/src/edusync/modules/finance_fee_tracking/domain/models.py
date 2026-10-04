from decimal import Decimal

def totals(rows):
    expected=sum((Decimal(str(r.get('net_expected') or 0)) for r in rows),Decimal('0'))
    regularized=sum((Decimal(str(r.get('regularized') or 0)) for r in rows),Decimal('0'))
    return {'net_expected':expected,'regularized':regularized,'remaining':max(expected-regularized,Decimal('0')),'rate':round(regularized*100/expected,1) if expected else Decimal('0')}
