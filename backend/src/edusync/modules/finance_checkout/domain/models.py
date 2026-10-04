from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable
from uuid import UUID

MONTH_ORDER={"SEPTEMBRE":1,"OCTOBRE":2,"NOVEMBRE":3,"DECEMBRE":4,"JANVIER":5,"FEVRIER":6,"FÉVRIER":6,"MARS":7,"AVRIL":8,"MAI":9,"JUIN":10,"JUILLET":11,"AOUT":12,"AOÛT":12}

@dataclass(frozen=True,slots=True)
class DueCharge:
    id:UUID; label:str; currency:str; net:Decimal; paid:Decimal=Decimal('0'); periodicity:str='ONE_OFF'; period_label:str|None=None; period_order:int|None=None; sequence_group:str|None=None; sequence_order:int|None=None
    @property
    def remaining(self)->Decimal:return max(Decimal('0'),self.net-self.paid)
    @property
    def settled(self)->bool:return self.remaining==0
    @property
    def chain(self)->str|None:
        if self.sequence_group:return self.sequence_group
        if self.periodicity=='MONTHLY':return 'MONTHLY'
        if self.periodicity in {'INSTALLMENT','PERIODIC'}:return self.label.split(' · ')[0]
        return None
    @property
    def order(self)->int:
        if self.sequence_order is not None:return self.sequence_order
        if self.period_order is not None:return self.period_order
        return MONTH_ORDER.get((self.period_label or '').upper(),999)

def sequential_eligibility(charges:Iterable[DueCharge])->dict[UUID,tuple[bool,str|None]]:
    rows=list(charges); result={c.id:(not c.settled,None if not c.settled else 'Déjà soldé') for c in rows}
    groups:dict[str,list[DueCharge]]={}
    for c in rows:
        if c.chain:groups.setdefault(c.chain,[]).append(c)
    for chain,items in groups.items():
        ordered=sorted(items,key=lambda c:(c.order,str(c.id)))
        first_due=next((c for c in ordered if not c.settled),None)
        for c in ordered:
            if c.settled:result[c.id]=(False,'Déjà soldé')
            elif first_due and c.id!=first_due.id:result[c.id]=(False,f"{first_due.period_label or first_due.label} doit être soldé d’abord")
            else:result[c.id]=(True,None)
    return result

def next_sequential_charge(charges:Iterable[DueCharge])->DueCharge|None:
    rows=list(charges); elig=sequential_eligibility(rows)
    seq=sorted((c for c in rows if c.chain),key=lambda c:(c.chain or '',c.order,str(c.id)))
    return next((c for c in seq if elig[c.id][0]),None)

def next_monthly_charge(charges:Iterable[DueCharge])->DueCharge|None:
    rows=[c for c in charges if c.periodicity=='MONTHLY']; elig=sequential_eligibility(rows)
    return next((c for c in sorted(rows,key=lambda c:(c.order,str(c.id))) if elig[c.id][0]),None)

def validate_selection(charges:Iterable[DueCharge],selected:Iterable[UUID])->Decimal:
    rows=list(charges); by={c.id:c for c in rows}; elig=sequential_eligibility(rows); ids=list(selected)
    if not ids:raise ValueError('Sélectionnez au moins un frais à encaisser')
    if any(i not in by for i in ids):raise ValueError('Frais inconnu')
    currencies={by[i].currency for i in ids}
    if len(currencies)!=1:raise ValueError('CDF et USD restent séparés : aucune conversion implicite')
    for i in ids:
        ok,reason=elig[i]
        if not ok:raise ValueError(reason or 'Frais non encaissable')
    return sum((by[i].remaining for i in ids),Decimal('0'))

def split_payment(amount:Decimal,current_due:Decimal,advance_enabled:bool)->tuple[Decimal,Decimal]:
    if amount<=0:raise ValueError('Montant invalide')
    normal=min(amount,current_due)
    advance=amount-normal
    if advance>0 and not advance_enabled:raise ValueError('Le surplus exige un plan anticipé disponible et la confirmation du parent')
    return normal,advance
