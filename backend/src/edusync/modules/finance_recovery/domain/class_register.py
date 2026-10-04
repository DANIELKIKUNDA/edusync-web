from __future__ import annotations
from decimal import Decimal

TERMINAL_LABELS={'ABANDON':'Abandon','TRANSFER':'Transféré'}

def terminal_label(event_type:str|None)->str|None:
    return TERMINAL_LABELS.get(event_type or '')

def cell_value(*,paid,advance,net,status_label=None):
    if status_label:return status_label
    p=Decimal(str(paid or 0))+Decimal(str(advance or 0)); n=Decimal(str(net or 0))
    if p<=0:return ''
    return str(min(p,n) if n>0 else p)

def recovery_rate(expected,regularized):
    e=Decimal(str(expected or 0));r=Decimal(str(regularized or 0))
    return Decimal('0') if e<=0 else (r*Decimal('100')/e).quantize(Decimal('0.1'))
