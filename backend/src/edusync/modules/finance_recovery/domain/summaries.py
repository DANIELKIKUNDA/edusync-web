from decimal import Decimal

def total_row(rows,label='TOTAL GÉNÉRAL',sum_counts=True):
    def d(k): return sum((Decimal(str(r.get(k) or 0)) for r in rows),Decimal('0'))
    expected=d('expected'); regularized=d('regularized_total')
    out={'label':label,'expected':expected,'cash_collected':d('cash_collected'),'outside_cash':d('outside_cash'),'regularized_total':regularized,'remaining':d('remaining'),'recovery_rate':Decimal('0') if expected<=0 else (regularized*100/expected).quantize(Decimal('0.1'))}
    for k in ('debtors','in_order','not_in_order'): out[k]=sum(int(r.get(k) or 0) for r in rows) if sum_counts else None
    return out

def register_footer(students,columns):
    debtors=in_order=0; expected=regularized=Decimal('0')
    for st in students:
        se=sr=Decimal('0')
        for col in columns:
            cell=st.get('cells',{}).get(col['key'])
            if not cell or cell.get('status_label'): continue
            se+=Decimal(str(cell.get('net') or 0)); sr+=min(Decimal(str(cell.get('paid') or 0))+Decimal(str(cell.get('advance') or 0)),Decimal(str(cell.get('net') or 0)))
        if se>0:
            debtors+=1
            if sr>=se: in_order+=1
        expected+=se; regularized+=sr
    remaining=max(expected-regularized,Decimal('0')); rate=Decimal('0') if expected<=0 else (regularized*100/expected).quantize(Decimal('0.1'))
    return {'debtors':debtors,'expected':expected,'regularized':regularized,'remaining':remaining,'in_order':in_order,'not_in_order':max(debtors-in_order,0),'recovery_rate':rate}
