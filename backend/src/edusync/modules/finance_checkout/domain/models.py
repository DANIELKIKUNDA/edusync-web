from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable
from uuid import UUID

NON_SEQUENTIAL='NONE'
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
        # N3-E / G-FIN-1 (Desktop _validate_allocations): only the monthly tuition (SCOLARITE family) and the tranches are
        # sequential; another monthly fee is marked NON_SEQUENTIAL and may be paid in any order.
        if self.sequence_group==NON_SEQUENTIAL:return None
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

def predecessors(charges:Iterable[DueCharge])->dict[UUID,list[UUID]]:
    """Unsettled earlier periods of the same sequential chain, per charge."""
    rows=list(charges); out={c.id:[] for c in rows}; groups:dict[str,list[DueCharge]]={}
    for c in rows:
        if c.chain:groups.setdefault(c.chain,[]).append(c)
    for items in groups.values():
        ordered=sorted(items,key=lambda c:(c.order,str(c.id)))
        for pos,c in enumerate(ordered):out[c.id]=[p.id for p in ordered[:pos] if not p.settled]
    return out

def validate_selection(charges:Iterable[DueCharge],selected:Iterable[UUID],*,exempt_predecessors:Iterable[UUID]=())->Decimal:
    """Desktop _validate_allocations: several consecutive periods may be settled on one receipt, but no later period while
    an earlier one stays open — every unsettled predecessor must be selected too (allocation runs in chain order, so a later
    period only receives money once the earlier ones are fully covered)."""
    rows=list(charges); by={c.id:c for c in rows}; ids=list(selected)
    if not ids:raise ValueError('Sélectionnez au moins un frais à encaisser')
    if any(i not in by for i in ids):raise ValueError('Frais inconnu')
    currencies={by[i].currency for i in ids}
    if len(currencies)!=1:raise ValueError('CDF et USD restent séparés : aucune conversion implicite')
    chosen=set(ids); preds=predecessors(rows); exempt=set(exempt_predecessors)
    for i in ids:
        if by[i].settled:raise ValueError('Déjà soldé')
        missing=[p for p in preds[i] if p not in chosen] if i not in exempt else []
        if missing:
            first=by[missing[0]];target=by[i];kind='La tranche' if (target.chain or '').startswith('TERM:') else 'La mensualité'
            raise ValueError(f"{kind} {target.period_label or target.label} ne peut pas être encaissée avant {first.period_label or first.label}. Réglez d'abord la période antérieure.")
    return sum((by[i].remaining for i in ids),Decimal('0'))

def split_payment(amount:Decimal,current_due:Decimal,advance_enabled:bool)->tuple[Decimal,Decimal]:
    if amount<=0:raise ValueError('Montant invalide')
    normal=min(amount,current_due)
    advance=amount-normal
    if advance>0 and not advance_enabled:raise ValueError('Le surplus exige un plan anticipé disponible et la confirmation du parent')
    return normal,advance
