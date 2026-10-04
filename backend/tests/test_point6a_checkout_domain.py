from decimal import Decimal
from uuid import uuid4
import pytest
from edusync.modules.finance_checkout.domain.models import DueCharge,sequential_eligibility,next_monthly_charge,validate_selection

def c(label,order,paid='0',net='100',currency='CDF',periodicity='MONTHLY'):
 return DueCharge(uuid4(),label,currency,Decimal(net),Decimal(paid),periodicity,label if periodicity=='MONTHLY' else None,order)
def test_months_are_strictly_sequential():
 feb=c('Février',6);mar=c('Mars',7);e=sequential_eligibility([feb,mar]);assert e[feb.id][0] is True;assert e[mar.id][0] is False;assert 'Février' in e[mar.id][1]
def test_next_month_advances_after_settlement():
 feb=c('Février',6,paid='100');mar=c('Mars',7);assert next_monthly_charge([feb,mar]).id==mar.id
def test_one_off_fee_remains_independently_payable():
 feb=c('Février',6);ad=c('Admission',None,periodicity='ONE_OFF');e=sequential_eligibility([feb,ad]);assert e[ad.id][0] is True
def test_cdf_usd_never_mix():
 a=c('Minerval',None,periodicity='ONE_OFF');b=c('Transport',None,currency='USD',periodicity='ONE_OFF')
 with pytest.raises(ValueError,match='CDF et USD'):validate_selection([a,b],[a.id,b.id])
def test_future_month_cannot_be_forced_through_api_domain():
 feb=c('Février',6);mar=c('Mars',7)
 with pytest.raises(ValueError,match='Février'):validate_selection([feb,mar],[mar.id])
def test_selected_total_is_remaining_not_nominal():
 a=c('Frais scolaire',None,paid='40',net='100',periodicity='ONE_OFF');assert validate_selection([a],[a.id])==Decimal('60')

def test_installments_are_strictly_sequential():
 a=DueCharge(uuid4(),'Retard · Tranche 1','CDF',Decimal('50'),periodicity='INSTALLMENT',period_label='Tranche 1',sequence_group='RETARD',sequence_order=1)
 b=DueCharge(uuid4(),'Retard · Tranche 2','CDF',Decimal('50'),periodicity='INSTALLMENT',period_label='Tranche 2',sequence_group='RETARD',sequence_order=2)
 e=sequential_eligibility([a,b]);assert e[a.id][0] is True;assert e[b.id][0] is False;assert 'Tranche 1' in e[b.id][1]

def test_distinct_sequence_groups_do_not_block_each_other():
 a=DueCharge(uuid4(),'Transport · Tranche 1','CDF',Decimal('50'),periodicity='INSTALLMENT',sequence_group='TRANSPORT',sequence_order=1)
 b=DueCharge(uuid4(),'Retard · Tranche 1','CDF',Decimal('50'),periodicity='INSTALLMENT',sequence_group='RETARD',sequence_order=1)
 e=sequential_eligibility([a,b]);assert e[a.id][0] and e[b.id][0]

def test_surplus_requires_available_anticipation():
 from edusync.modules.finance_checkout.domain.models import split_payment
 with pytest.raises(ValueError,match='plan anticipé disponible'):split_payment(Decimal('80'),Decimal('65'),False)
 assert split_payment(Decimal('80'),Decimal('65'),True)==(Decimal('65'),Decimal('15'))

def test_future_installment_cannot_be_forced_when_previous_is_in_full_context():
 a=DueCharge(uuid4(),'Retard · Tranche 1','CDF',Decimal('50'),periodicity='INSTALLMENT',period_label='Tranche 1',sequence_group='RETARD',sequence_order=1)
 b=DueCharge(uuid4(),'Retard · Tranche 2','CDF',Decimal('50'),periodicity='INSTALLMENT',period_label='Tranche 2',sequence_group='RETARD',sequence_order=2)
 with pytest.raises(ValueError,match='Tranche 1'):validate_selection([a,b],[b.id])
